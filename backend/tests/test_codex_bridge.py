"""Fake app-server contracts only; no real login, model turn, or quota usage."""
import base64
import io
import json
import time

import pytest
from PIL import Image

from backend.providers.codex import CodexImageProvider, CodexRPC
from backend.providers.base import ProviderError
from extractor_core.io import png_bytes


def transparent_image():
    image = Image.new("RGBA", (12, 12))
    image.putpixel((6, 6), (0, 0, 0, 255))
    return image


class FakeRPC:
    def __init__(self, *, kind="image", account="chatgpt", url="https://chatgpt.com/auth", failure=False):
        self.kind, self.account, self.url, self.failure = kind, account, url, failure
        self.calls = []

    def __call__(self, binary, home, **kwargs):
        self.binary, self.home = binary, home
        return self

    def __enter__(self): return self
    def __exit__(self, *args): pass

    def request(self, method, params):
        self.calls.append((method, params))
        if method == "account/read": return {"account":{"type":self.account}}
        if method == "account/login/start": return {"authUrl":self.url, "loginId":"login-1"}
        if method == "thread/start":
            assert params["approvalPolicy"] == "never" and params["ephemeral"]
            config = params["config"]
            assert config["permissions"]["print_extractor"]["filesystem"][":root"] == "deny"
            assert config["features"]["multi_agent"] is False
            assert config["features"]["shell_tool"] is False
            assert "model_providers" not in config  # Never replace the built-in provider with an API endpoint.
            assert config["features"]["unbounded_connection_retries"] is False
            return {"thread":{"id":"thread-1"}, "modelProvider":"openai", "activePermissionProfile":{"id":"print_extractor"}}
        if method == "turn/start":
            image_path = params["input"][1]["path"]
            assert Image.open(image_path).size == (12, 12)
            return {"turn":{"id":"turn-1"}}
        raise AssertionError(method)

    def events(self):
        if self.calls[-1][0] == "account/login/start":
            yield {"method":"account/login/completed", "params":{"loginId":"unrelated", "success":False}}
            yield {"method":"account/login/completed", "params":{"loginId":"login-1", "success":not self.failure}}
            return
        image = transparent_image()
        if self.kind == "opaque": image.putalpha(255)
        item = {"type":"imageGeneration", "result":base64.b64encode(png_bytes(image)).decode()}
        if self.kind == "text": item = {"type":"agentMessage", "text":"Here is a transparent image"}
        if self.kind == "path": item["savedPath"] = "/unrelated/secret.png"
        if self.kind == "failure": item["failure"] = "upstream-private-details"
        if self.kind == "broken": item["result"] = "not base64!"
        payload = {"method":"item/completed", "params":{"threadId":"thread-1", "turnId":"turn-1", "item":item}}
        yield payload
        if self.kind == "multiple": yield payload
        yield {"method":"turn/completed", "params":{"threadId":"thread-1", "turn":{"id":"turn-1", "status":"completed"}}}


def provider(tmp_path, fake, **kwargs):
    return CodexImageProvider(binary="/official/codex", home=tmp_path/"owned-codex", rpc_factory=fake, **kwargs)


def test_quota_opt_in_before_any_process_or_upload(tmp_path):
    fake = FakeRPC()
    with pytest.raises(ProviderError, match="明确同意"):
        provider(tmp_path, fake).edit(transparent_image())
    assert not fake.calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize("account", [None, "apiKey", "amazonBedrock"])
def test_login_must_be_chatgpt_without_api_fallback(tmp_path, account):
    fake = FakeRPC(account=account)
    with pytest.raises(ProviderError, match="不会复用"):
        provider(tmp_path, fake, allow_usage=True).edit(transparent_image())
    assert [method for method, _ in fake.calls] == ["account/read"]


def test_image_event_and_actual_alpha_are_required(tmp_path):
    fake = FakeRPC()
    result = provider(tmp_path, fake, allow_usage=True).edit(transparent_image())
    assert result.getchannel("A").getextrema() == (0, 255)
    assert result.getpixel((6, 6)) == (0, 0, 0, 255)
    assert [method for method, _ in fake.calls].count("turn/start") == 1


@pytest.mark.parametrize("kind", ["text", "opaque", "path", "failure", "broken", "multiple"])
def test_reject_false_success_without_retry(tmp_path, kind):
    fake = FakeRPC(kind=kind)
    with pytest.raises(ProviderError) as error:
        provider(tmp_path, fake, allow_usage=True).edit(transparent_image())
    assert "upstream-private-details" not in str(error.value)
    assert [method for method, _ in fake.calls].count("turn/start") == 1


def test_official_browser_login_uses_managed_flow_and_matches_login_id(tmp_path):
    fake = FakeRPC(); opened = []
    assert provider(tmp_path, fake).login(opened.append)["authenticated"]
    assert opened == ["https://chatgpt.com/auth"]
    assert fake.calls == [("account/login/start", {"type":"chatgpt"})]


@pytest.mark.parametrize("url", ["http://chatgpt.com/auth", "https://chatgpt.com.evil.example/auth",
    "https://secret@chatgpt.com/auth", "https://chatgpt.com:8888/auth", "https://chatgpt.com:invalid/auth"])
def test_login_rejects_unofficial_urls_without_opening_browser(tmp_path, url):
    opened = []
    with pytest.raises(ProviderError): provider(tmp_path, FakeRPC(url=url)).login(opened.append)
    assert not opened


def test_old_cli_cannot_silently_ignore_permission_profile(tmp_path):
    class OldCLI(FakeRPC):
        def request(self, method, params):
            result = super().request(method, params)
            if method == "thread/start": result.pop("activePermissionProfile")
            return result
    fake = OldCLI()
    with pytest.raises(ProviderError, match="未提交图像任务"):
        provider(tmp_path, fake, allow_usage=True).edit(transparent_image())
    assert not any(method == "turn/start" for method, _ in fake.calls)


class FakeProcess:
    def __init__(self, error=False):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(json.dumps({"id":1, **({"error":{"message":"secret"}} if error else {"result":{}})})+"\n")
        self.terminated = False

    def poll(self): return 0 if self.terminated else None
    def terminate(self): self.terminated = True
    def wait(self, **kwargs): return 0


def test_stdio_uses_owned_home_and_filters_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-unrelated-key")
    monkeypatch.setenv("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", "fake-other-key")
    monkeypatch.setenv("CODEX_HOME", "/unrelated/account-cache")
    process = FakeProcess(); calls = []
    def popen(args, **kwargs): calls.append((args, kwargs)); return process
    with CodexRPC("/official/codex", tmp_path/"owned", popen=popen) as rpc:
        assert calls[0][1]["env"]["CODEX_HOME"] == str(tmp_path/"owned")
        assert "OPENAI_API_KEY" not in calls[0][1]["env"]
        assert "PRINT_EXTRACTOR_DASHSCOPE_API_KEY" not in calls[0][1]["env"]
        assert calls[0][1]["cwd"] == tmp_path/"owned"
        assert 'cli_auth_credentials_store="file"' in calls[0][0]
        rpc.messages = __import__("queue").Queue()
        rpc.messages.put({"id":99, "method":"item/tool/call", "params":{}})
        rpc.receive(time.monotonic()+1)
        assert "Client-side tool execution is disabled" in process.stdin.getvalue()
    assert process.terminated and process.stdin.closed and process.stdout.closed


def test_failed_initialize_always_stops_child(tmp_path):
    process = FakeProcess(error=True)
    with pytest.raises(ProviderError) as error:
        with CodexRPC("/official/codex", tmp_path/"owned", popen=lambda *a, **kw:process): pass
    assert process.terminated and "secret" not in str(error.value)


class ImageEventRPC(FakeRPC):
    """Replay a single protocol image item, never a live model call."""
    def __init__(self, item):
        super().__init__()
        self.item = item.copy()

    def request(self, method, params):
        result = super().request(method, params)
        if method == "turn/start" and self.item.get("savedPath") in {"__missing__", "__saved__"}:
            from pathlib import Path
            path = Path(params["input"][1]["path"]).parent / "result.png"
            if self.item["savedPath"] == "__saved__":
                path.write_bytes(png_bytes(transparent_image()))
            self.item["savedPath"] = str(path.resolve())
        return result

    def events(self):
        yield {"method": "item/completed", "params": {
            "threadId": "thread-1", "turnId": "turn-1", "item": self.item}}
        yield {"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}}}


def image_event(**updates):
    item = {"type": "imageGeneration", "status": "completed",
            "result": base64.b64encode(png_bytes(transparent_image())).decode()}
    return {**item, **updates}


@pytest.mark.parametrize("status", ["failed", "in_progress", "cancelled", "unknown"])
def test_image_event_status_cannot_claim_success(tmp_path, status):
    fake = ImageEventRPC(image_event(status=status))
    with pytest.raises(ProviderError, match="图像事件没有成功完成"):
        provider(tmp_path, fake, allow_usage=True).edit(transparent_image())
    assert [m for m, _ in fake.calls].count("turn/start") == 1


def test_empty_image_event_reports_missing_payload(tmp_path):
    fake = ImageEventRPC(image_event(result="", savedPath=None))
    with pytest.raises(ProviderError, match="图像事件没有提供结果字节或保存路径"):
        provider(tmp_path, fake, allow_usage=True).edit(transparent_image())
    assert [m for m, _ in fake.calls].count("turn/start") == 1


@pytest.mark.parametrize("result", [None, {}, 7])
def test_invalid_image_event_payload_is_a_provider_error(tmp_path, result):
    fake = ImageEventRPC(image_event(result=result))
    with pytest.raises(ProviderError, match="图像结果字段格式无效"):
        provider(tmp_path, fake, allow_usage=True).edit(transparent_image())


def test_missing_authorized_image_file_is_a_provider_error(tmp_path):
    fake = ImageEventRPC(image_event(savedPath="__missing__"))
    with pytest.raises(ProviderError, match="保存的 PNG 结果不可读取"):
        provider(tmp_path, fake, allow_usage=True).edit(transparent_image())


def test_canonical_saved_path_under_temporary_work_is_accepted(tmp_path):
    fake = ImageEventRPC(image_event(savedPath="__saved__", result=""))
    result = provider(tmp_path, fake, allow_usage=True).edit(transparent_image())
    assert result.getchannel("A").getextrema() == (0, 255)
    assert [m for m, _ in fake.calls].count("turn/start") == 1
