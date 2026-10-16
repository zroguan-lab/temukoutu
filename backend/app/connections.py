"""Public account state and asynchronous official login; credentials stay in CLI."""
import threading
import webbrowser

from fastapi import HTTPException
from backend.providers.base import ProviderError
from backend.providers.codex import CodexImageProvider, find_codex
from backend.providers.grok import GrokImageProvider, find_grok


class Connections:
    def __init__(self, config_path, adapters=None):
        self.config_path = config_path
        self.adapters = adapters or {}
        self.lock = threading.RLock()
        self.states = {}
        self.usage_locks = {key: threading.Lock() for key in ("gpt", "grok", "qwen")}

    def adapter(self, name):
        if name in self.adapters: return self.adapters[name]
        if name == "gpt":
            return CodexImageProvider(home=self.config_path.parent/"codex", allow_usage=True)
        if name == "grok": return GrokImageProvider(allow_usage=True)
        raise HTTPException(404, "未支持的登录方式")

    def public(self, name):
        if name not in {"gpt", "grok"}: raise HTTPException(404, "未支持的登录方式")
        with self.lock:
            try:
                if name not in self.adapters: (find_codex if name == "gpt" else find_grok)()
                installed = True
            except ProviderError:
                installed = False
            state = self.states.get(name, {"state": "unknown", "message": "点击检查登录，或连接本人账号"})
            return {"id": name, "installed": installed, "authenticated": state["state"] == "connected", **state}

    def check(self, name):
        with self.lock:
            if self.public(name)["state"] == "waiting": return self.public(name)
        usage = self.usage_locks.get(name)
        if usage is None: raise HTTPException(404, "未支持的登录方式")
        if not usage.acquire(blocking=False): raise HTTPException(409, "账号正在处理，请稍后检查")
        try:
            authenticated = self.adapter(name).account_status().get("authenticated", False)
            state = {"state": "connected" if authenticated else "signed_out",
                     "message": "已连接本人账号" if authenticated else "尚未登录或登录已失效"}
        except (ProviderError, OSError):
            state = {"state": "error", "message": "无法确认登录，请检查官方 CLI、网络或重新登录"}
        finally:
            usage.release()
        with self.lock: self.states[name] = state
        return self.public(name)

    def login(self, name):
        adapter = self.adapter(name)
        with self.lock:
            if self.public(name)["state"] == "waiting": return self.public(name)
            if not self.usage_locks[name].acquire(blocking=False):
                raise HTTPException(409, "账号正在生成，请完成后再登录")
            self.states[name] = {"state": "waiting", "message": "请在官方浏览器页面完成登录和授权"}
        def run():
            try:
                result = adapter.login(webbrowser.open)
                state = {"state": "connected" if result.get("authenticated") else "signed_out",
                         "message": "已连接本人账号" if result.get("authenticated") else "登录未完成"}
            except Exception:
                state = {"state": "error", "message": "登录未确认；完成官方授权后可点击检查登录"}
            finally:
                with self.lock: self.states[name] = state
                self.usage_locks[name].release()
        threading.Thread(target=run, daemon=True, name=f"login-{name}").start()
        return self.public(name)

    def expired(self, name):
        if name in {"gpt", "grok"}:
            with self.lock:
                self.states[name] = {"state": "unknown", "message": "本次生成失败，请重新检查登录和账号额度"}
