"""Official Grok Build login and native image_edit. Never extracts credentials."""
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from extractor_core.io import MAX_BYTES, save_png
from extractor_core.providers import ProviderSpec
from .base import PROMPT, ProviderError
from .codex import CodexRPC
from .generated import GeneratedImage


def find_grok():
    for value in (os.environ.get("PRINT_EXTRACTOR_GROK_BIN"), shutil.which("grok.exe"),
                  shutil.which("grok"), Path.home()/".grok"/"bin"/"grok", Path.home()/".grok"/"bin"/"grok.exe"):
        if value and Path(value).is_file() and Path(value).suffix.lower() not in {".cmd", ".bat"}:
            return str(Path(value).resolve())
    raise ProviderError("未找到官方 Grok Build CLI；请先安装官方 CLI")


def process_environment():
    allowed = {"PATH", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"}
    return {k: v for k, v in os.environ.items() if k in allowed}


class GrokACP(CodexRPC):
    """Only initialize/authenticate; never creates an agent session or model turn."""
    def __enter__(self):
        self.process = self._popen([self.binary, "--no-auto-update", "agent", "--no-leader", "stdio"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", env=process_environment(), cwd=self.home)
        def reader():
            try:
                for line in self.process.stdout:
                    if len(line) > 1024*1024: break
                    self.messages.put(json.loads(line))
            except (OSError, ValueError):
                pass
            self.messages.put(None)
        threading.Thread(target=reader, daemon=True).start()
        try:
            self.initial = self.request("initialize", {"protocolVersion": 1,
                "clientInfo": {"name": "print-extractor-ai", "version": "0.1.0"},
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}})
        except BaseException:
            self.__exit__()
            raise
        return self


def result_from_events(events, work, session_id, sessions_root):
    """Trust only the single matching completed native tool output, never prose."""
    calls = [e for e in events if e.get("type") == "tool_call"]
    if len(calls) != 1 or calls[0].get("toolName") != "image_edit":
        raise ProviderError("Grok 未完成约定的单次图像编辑；文本回复不算出图，不会重试")
    updates = [e for e in events if e.get("type") == "tool_call_update"
               and e.get("toolCallId") == calls[0].get("toolCallId") and e.get("status") in {"completed", "failed"}]
    if len(updates) != 1 or updates[0].get("status") != "completed":
        raise ProviderError("Grok 图像编辑未完成；请检查登录、账号权限与用量，不会重试")
    raw = updates[0].get("rawOutput") or {}
    if not isinstance(raw, dict) or raw.get("type") != "ImageEdit" or not isinstance(raw.get("path"), str):
        raise ProviderError("Grok 没有返回可验证的图像文件")
    # The tool writes <sessions>/<percent-encoded canonical cwd>/<explicit session UUID>/images/.
    root = (Path(sessions_root) / quote(str(Path(work).resolve()), safe="") / session_id / "images").resolve()
    path = Path(raw["path"]).resolve()
    if path.parent != root or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ProviderError("Grok 结果不在本次图像输出目录；未读取其他会话文件")
    try:
        with path.open("rb") as stream:
            return GeneratedImage.decode(stream.read(MAX_BYTES + 1))
    except OSError:
        raise ProviderError("Grok 返回的图像文件无法读取；不会重试") from None


class GrokImageProvider:
    spec = ProviderSpec("grok-cli", "Grok · 官方 Build 登录", "generated_image", True, False)

    def __init__(self, binary=None, *, allow_usage=False, rpc_factory=GrokACP, popen=subprocess.Popen):
        self.binary = binary or find_grok()
        self.allow_usage, self._rpc, self._popen = allow_usage, rpc_factory, popen

    def account_status(self):
        with tempfile.TemporaryDirectory(prefix="print-extractor-auth-") as directory:
            with self._rpc(self.binary, directory, timeout=15) as rpc:
                methods = rpc.initial.get("authMethods", [])
                if not any((m.get("id") if isinstance(m, dict) else m) == "cached_token" for m in methods):
                    return {"authenticated": False}
                rpc.request("authenticate", {"methodId": "cached_token", "_meta": {"headless": True}})
                return {"authenticated": True}

    def login(self, open_browser=None):
        # Official CLI opens its own OAuth page and owns every credential operation.
        try:
            with tempfile.TemporaryDirectory(prefix="print-extractor-login-") as directory:
                result = subprocess.run([self.binary, "--no-auto-update", "login", "--oauth"],
                    cwd=directory, env=process_environment(), stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
            if result.returncode != 0 or not self.account_status()["authenticated"]:
                raise ProviderError("Grok 登录未完成，请在官方页面完成授权后重新检查")
            return {"authenticated": True}
        except subprocess.TimeoutExpired:
            raise ProviderError("Grok 登录等待超时；可完成官方授权后点击检查登录") from None

    def generate(self, image, model="grok-native"):
        if not self.allow_usage:
            raise ProviderError("请先同意上传图片并使用 Grok 账号额度")
        if not self.account_status()["authenticated"]:
            raise ProviderError("Grok 登录已失效，请重新登录")
        with tempfile.TemporaryDirectory(prefix="print-extractor-grok-") as directory:
            work = Path(directory).resolve()
            source = work/"input.png"
            save_png(source, image)
            session_id = str(uuid.uuid4())
            prompt = (PROMPT + f" 仅调用一次原生 image_edit，image 数组必须为 [{json.dumps(str(source))}]。"
                      "仅生成一张；不要使用其他工具、搜索、读取其他文件或再次尝试。")
            args = [self.binary, "--no-auto-update", "--no-subagents", "--no-plan", "--disable-web-search",
                    "--tools", "image_edit", "--allow", "image_edit", "--permission-mode", "dontAsk",
                    "--max-turns", "1", "--output-format", "streaming-json", "--model", "grok-4.6",
                    "--session-id", session_id, "-p", prompt]
            process = self._popen(args, cwd=work, env=process_environment(), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
            messages = queue.Queue()
            def reader():
                try:
                    for line in process.stdout:
                        if len(line) > 2*1024*1024: break
                        event = json.loads(line)
                        if event.get("type") in {"tool_call", "tool_call_update"}:
                            messages.put(event)
                except (OSError, ValueError):
                    pass
                messages.put(None)
            threading.Thread(target=reader, daemon=True).start()
            events, deadline = [], time.monotonic()+180
            try:
                while True:
                    try: event = messages.get(timeout=max(.01, deadline-time.monotonic()))
                    except queue.Empty:
                        raise ProviderError("Grok 请求超时，可能已使用额度；不会自动重试") from None
                    if event is None: break
                    events.append(event)
                    if len(events) > 50: raise ProviderError("Grok 返回异常数量的工具事件；已停止")
                process.wait(timeout=max(.01, deadline-time.monotonic()))
                # A max-turns exit after a completed image tool is valid; prose/exit 0 alone is not.
                return result_from_events(events, work, session_id, Path.home()/".grok"/"sessions")
            except subprocess.TimeoutExpired:
                raise ProviderError("Grok 请求超时，可能已使用额度；不会自动重试") from None
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)
                process.stdout.close()

    def edit(self, image, model="grok-native"):
        return self.generate(image, model).image
