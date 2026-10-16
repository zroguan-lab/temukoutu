"""Optional official Codex app-server bridge, isolated from existing account caches.

Uses public JSON-RPC and imageGeneration events. No private token or image API
endpoint is read. Live login/generation requires the user; contract tests are fake.
"""
import base64
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from extractor_core.io import MAX_BYTES, save_png
from extractor_core.providers import ProviderSpec
from .images import transparent_png
from .generated import GeneratedImage
from .base import PROMPT, ProviderError
from backend.app.settings import user_config_path, secure_windows_directory


def find_codex():
    configured = os.environ.get("PRINT_EXTRACTOR_CODEX_BIN")
    candidates = [configured, shutil.which("codex.exe"), shutil.which("codex"),
                  "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"]
    for value in candidates:
        if value and Path(value).is_file() and Path(value).suffix.lower() not in {".cmd", ".bat"}:
            return str(Path(value).resolve())
    raise ProviderError("未找到官方 Codex CLI 可执行文件；请安装官方 CLI 或指定 PRINT_EXTRACTOR_CODEX_BIN")


def thread_configuration(work):
    return {
        "default_permissions": "print_extractor",
        "permissions": {"print_extractor": {"filesystem": {":root": "deny", str(work): "write"}}},
        "model_provider": "openai",
        "features": {
            "image_generation": True,
            **dict.fromkeys(("shell_tool", "apps", "browser_use", "computer_use", "multi_agent",
                            "plugins", "hooks", "skill_search", "unbounded_connection_retries"), False),
        },
    }


class CodexRPC:
    def __init__(self, binary, home, *, popen=subprocess.Popen, timeout=180):
        self.binary, self.home, self.timeout = binary, Path(home), timeout
        self._popen = popen
        self.messages = queue.Queue()
        self.pending = []
        self.counter = 0
        self.process = None

    def __enter__(self):
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "nt": secure_windows_directory(self.home)
        else: self.home.chmod(0o700)
        # Allow only OS/runtime basics. Never pass other providers' credentials.
        allowed = {"PATH", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"}
        env = {k:v for k,v in os.environ.items() if k in allowed}
        env["CODEX_HOME"] = str(self.home)
        self.process = self._popen([self.binary, "-c", 'cli_auth_credentials_store="file"',
                                   "-c", "analytics.enabled=false", "app-server", "--stdio"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", env=env, cwd=self.home)
        def reader():
            try:
                for line in self.process.stdout:
                    if len(line) > 40*1024*1024: break
                    self.messages.put(json.loads(line))
            except (ValueError, OSError):
                pass
            self.messages.put(None)
        threading.Thread(target=reader, daemon=True).start()
        try:
            self.request("initialize", {"clientInfo":{"name":"print-extractor-ai","version":"0.1.0"}, "capabilities":{}})
            self.send({"method":"initialized"})
        except BaseException:
            self.__exit__()
            raise
        return self

    def send(self, payload):
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False)+"\n")
        self.process.stdin.flush()

    def receive(self, deadline):
        try: message = self.messages.get(timeout=max(.01, deadline-time.monotonic()))
        except queue.Empty: raise ProviderError("Codex 请求超时，可能已消耗额度；不会自动重试") from None
        if message is None: raise ProviderError("官方 Codex 进程已退出；请检查 CLI 版本及登录状态")
        if "id" in message and "method" in message:
            # Never execute client-side tools or automatically grant agent approvals.
            self.send({"id":message["id"], "error":{"code":-32601,"message":"Client-side tool execution is disabled"}})
        return message

    def request(self, method, params):
        self.counter += 1
        request_id = self.counter
        self.send({"id":request_id,"method":method,"params":params})
        deadline=time.monotonic()+self.timeout
        while True:
            item=self.receive(deadline)
            if item.get("id")==request_id and "method" not in item:
                if "error" in item: raise ProviderError("官方 Codex 拒绝此操作；请核对版本、账号和工具可用性")
                return item.get("result",{})
            self.pending.append(item)

    def events(self):
        deadline=time.monotonic()+self.timeout
        while True:
            yield self.pending.pop(0) if self.pending else self.receive(deadline)

    def __exit__(self, *args):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired: self.process.kill();self.process.wait(timeout=5)
        self.process.stdin.close();self.process.stdout.close()


def _image_event_bytes(item, work, home):
    """Decode one completed official item; never infer pixels from status or text."""
    status = item.get("status")
    if item.get("failure") or (status is not None and status != "completed"):
        raise ProviderError("Codex 图像事件没有成功完成；可能已消耗额度，不会重试")
    saved = item.get("savedPath")
    if saved is not None and not isinstance(saved, str):
        raise ProviderError("Codex 图像保存路径格式无效；不会重试")
    if saved:
        path = Path(saved).resolve()
        roots = (Path(work).resolve(), (Path(home) / "generated_images").resolve())
        if path.suffix.lower() != ".png" or not any(path.is_relative_to(root) for root in roots):
            raise ProviderError("Codex 结果不在授权的 PNG 输出目录")
        try:
            with path.open("rb") as stream:
                output = stream.read(MAX_BYTES + 1)
        except OSError:
            raise ProviderError("Codex 保存的 PNG 结果不可读取；不会重试") from None
    else:
        result = item.get("result", "")
        if not isinstance(result, str):
            raise ProviderError("Codex 图像结果字段格式无效；不会重试")
        payload = result.removeprefix("data:image/png;base64,")
        if not payload:
            raise ProviderError("Codex 图像事件没有提供结果字节或保存路径；不会重试")
        try:
            output = base64.b64decode(payload, validate=True)
        except ValueError:
            raise ProviderError("Codex 没有返回可验证的 PNG 图像") from None
    if not output:
        raise ProviderError("Codex 图像事件没有提供结果字节或保存路径；不会重试")
    if len(output) > MAX_BYTES:
        raise ProviderError("Codex 图像结果超过 25MB；不会重试")
    return output


class CodexImageProvider:
    spec=ProviderSpec("codex-cli", "GPT · 官方 Codex 登录", "generated_image", True, False)

    def __init__(self, binary=None, home=None, *, allow_usage=False, rpc_factory=CodexRPC):
        self.binary=binary or find_codex()
        self.home=Path(home or user_config_path().parent/"codex").resolve()
        self.allow_usage=allow_usage
        self._rpc=rpc_factory

    def login(self, open_browser):
        with self._rpc(self.binary,self.home,timeout=300) as rpc:
            result=rpc.request("account/login/start",{"type":"chatgpt"})
            url=result.get("authUrl","")
            try:
                parts=urlsplit(url)
                valid=(parts.scheme=="https" and parts.hostname in {"chatgpt.com","auth.openai.com"}
                       and not parts.username and not parts.password and parts.port in {None,443})
            except (TypeError,ValueError):
                valid=False
            if not valid:
                raise ProviderError("官方登录页地址无效；未打开浏览器")
            open_browser(url)
            for event in rpc.events():
                if (event.get("method")=="account/login/completed"
                        and event.get("params",{}).get("loginId")==result.get("loginId")):
                    if not event.get("params",{}).get("success"): raise ProviderError("ChatGPT 登录未完成")
                    return {"authenticated":True,"auth":"chatgpt","credentials_managed_by":"official_codex"}

    def account_status(self):
        with self._rpc(self.binary, self.home, timeout=15) as rpc:
            account = rpc.request("account/read", {"refreshToken": False}).get("account") or {}
            return {"authenticated": account.get("type") == "chatgpt"}

    def edit(self, image, model="codex-default"):
        try: return transparent_png(self.generate(image, model).data)
        except ValueError as exc: raise ProviderError(str(exc)) from None

    def generate(self, image, model="codex-default"):
        if not self.allow_usage: raise ProviderError("请明确同意消耗 Codex 额度后再调用；不会自动改用 API Key")
        with tempfile.TemporaryDirectory(prefix="print-extractor-gpt-") as directory:
            work=Path(directory).resolve();source=work/"input.png";save_png(source,image)
            with self._rpc(self.binary,self.home) as rpc:
                account=rpc.request("account/read",{"refreshToken":False}).get("account") or {}
                if account.get("type")!="chatgpt": raise ProviderError("请先通过本项目隔离的官方登录流程登录 ChatGPT；不会复用其他账号缓存或切换 API 计费")
                started=rpc.request("thread/start",{"cwd":str(work),"ephemeral":True,"approvalPolicy":"never","config":thread_configuration(work)})
                if started.get("activePermissionProfile",{}).get("id")!="print_extractor" or started.get("modelProvider")!="openai":
                    raise ProviderError("CLI 没有应用本项目隔离权限或官方 provider；未提交图像任务")
                thread=started["thread"]["id"]
                prompt=PROMPT+f" 使用内建图像生成工具，仅生成一张，保存到 {work/'result.png'}。不要运行 shell、读取其他文件或调用其他服务。"
                turn=rpc.request("turn/start",{"threadId":thread,"input":[{"type":"text","text":prompt},{"type":"localImage","path":str(source)}]})["turn"]["id"]
                output=None
                for event in rpc.events():
                    params=event.get("params",{})
                    if params.get("threadId")!=thread:
                        continue
                    if event.get("method")=="item/completed" and params.get("item",{}).get("type")=="imageGeneration":
                        if params.get("turnId")!=turn:
                            continue
                        if output is not None:
                            raise ProviderError("Codex 返回多张图像；本次单张契约未通过，不会重试")
                        output = _image_event_bytes(params["item"], work, self.home)
                    if event.get("method")=="turn/completed" and params.get("turn",{}).get("id")==turn:
                        if params["turn"].get("status")!="completed":
                            raise ProviderError("Codex 图像任务没有正常完成；请核对用量，不会重试")
                        break
                if not output or len(output)>MAX_BYTES: raise ProviderError("Codex 未产生有效大小的图像；文本回复不算成功")
                try: return GeneratedImage.decode(output)
                except ValueError as exc: raise ProviderError(str(exc)) from None
