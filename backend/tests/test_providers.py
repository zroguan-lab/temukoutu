"""Mock HTTP contracts only. These do not demonstrate real model output quality."""
import base64
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.app.main import create_app
from backend.providers.qwen import QwenImageProvider, ProviderError
from extractor_core.io import png_bytes
from extractor_core.providers import LOCAL_MASK_PROVIDER
from tests.synthetic import sample


def transparent_image():
    result = Image.new("RGBA", (32, 32))
    ImageDraw.Draw(result).rectangle((8, 8, 24, 24), fill=(0, 0, 0, 255))
    return result


def adapter(handler):
    return QwenImageProvider("test-only-secret", transport=httpx.MockTransport(handler))


def test_qwen_json_contract_and_no_key_on_result_download():
    calls = []
    source, _ = sample()
    def handle(request):
        calls.append(request)
        if request.method == "POST":
            assert str(request.url) == "https://dashscope.aliyuncs.com/compatible-mode/v1/images/generations"
            assert request.headers["authorization"] == "Bearer test-only-secret"
            assert request.headers["content-type"] == "application/json"
            body = json.loads(request.content)
            assert body["model"] == "qwen-image-2.1-turbo" and body["n"] == 1
            assert body["prompt_extend"] is False
            decoded = Image.open(io.BytesIO(base64.b64decode(body["image"].split(",")[1])))
            assert decoded.tobytes() == source.tobytes()
            assert "mask" not in body and "background" not in body and "response_format" not in body
            return httpx.Response(200, json={"data": [{"url": "https://result.oss-cn-beijing.aliyuncs.com/result.png"}]})
        assert "authorization" not in request.headers
        return httpx.Response(200, content=png_bytes(transparent_image()))
    output = adapter(handle).edit(source, "qwen-image-2.1-turbo")
    assert output.getchannel("A").getextrema() == (0, 255)
    assert output.getpixel((12, 12)) == (0, 0, 0, 255)  # Internal black is retained, not keyed out.
    assert len(calls) == 2


@pytest.mark.parametrize("url", ["http://result.aliyuncs.com/x", "https://evil.example/x", "https://127.0.0.1/x",
    "https://result.aliyuncs.com.evil.example/x", "https://key@result.aliyuncs.com/x", "https://result.aliyuncs.com:8000/x"])
def test_untrusted_download_url_is_rejected_without_fetch(url):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"url": url}]})
    with pytest.raises(ProviderError, match="无效结果地址"):
        adapter(handle).edit(transparent_image(), "qwen-image-2.1-pro")
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["rgb", "opaque", "empty", "jpeg", "broken", "oversized"])
def test_false_transparency_and_bad_images_are_rejected(kind):
    image = transparent_image()
    if kind == "rgb": image = image.convert("RGB")
    if kind == "opaque": image.putalpha(255)
    if kind == "empty": image.putalpha(0)
    stream = io.BytesIO()
    (image.convert("RGB") if kind == "jpeg" else image).save(stream, format="JPEG" if kind == "jpeg" else "PNG")
    content = b"broken" if kind == "broken" else b"x"*(25*1024*1024+1) if kind == "oversized" else stream.getvalue()
    def handle(request):
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": "https://result.aliyuncs.com/result.png"}]})
        return httpx.Response(200, content=content)
    with pytest.raises(ProviderError): adapter(handle).edit(transparent_image(), "qwen-image-2.1-pro")


@pytest.mark.parametrize("response", [httpx.Response(401, text="test-only-secret"), httpx.Response(429),
    httpx.Response(200, json={"data": []}), httpx.Response(200, content=b"not json"), httpx.Response(302)])
def test_remote_error_is_sanitized_and_never_retried(response):
    calls = []
    def handle(request):
        calls.append(request)
        return response
    with pytest.raises(ProviderError) as exc: adapter(handle).edit(transparent_image(), "qwen-image-2.1-pro")
    assert "test-only-secret" not in str(exc.value) and len(calls) == 1


def test_timeout_not_retried_and_invalid_model_has_no_network():
    calls = []
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("test-only-secret")
    with pytest.raises(ProviderError): adapter(handle).edit(transparent_image(), "unknown")
    assert not calls
    with pytest.raises(ProviderError) as exc: adapter(handle).edit(transparent_image(), "qwen-image-2.1-pro")
    assert len(calls) == 1 and "test-only-secret" not in str(exc.value)


class StubProvider:
    calls = 0
    failure = False
    def edit(self, image, model):
        self.calls += 1
        if self.failure: raise ProviderError("模拟网络超时，可能已计费")
        return transparent_image()


def setup_client(tmp_path, provider=None):
    client = TestClient(create_app(tmp_path / "tasks", image_edit_provider=provider), base_url="http://127.0.0.1:7860")
    task = client.post("/api/tasks", files={"file": ("input.png", png_bytes(sample()[0]))}).json()
    body = {"model": "qwen-image-2.1-turbo", "request_id": "a"*32, "source_revision": task["rev"],
            "allow_upload": True, "max_estimated_cost_cny": 0.10}
    return client, task, body


def test_cloud_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PRINT_EXTRACTOR_CLOUD_ENABLED", raising=False)
    c, task, body = setup_client(tmp_path)
    config = c.get("/api/providers").json()
    assert config["local"]["output"] == "source_mask" and not config["cloud"]["enabled"]
    assert config["cloud"]["verification"] == "mock_contract_only"
    assert config["cloud"]["experimental"] and not config["cloud"]["generation_verified"]
    assert {model["provider"] for model in config["models"]} == {"gpt", "grok"}
    assert c.post(f"/api/tasks/{task['id']}/generations", json=body).status_code == 409


def test_configuration_does_not_reuse_general_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINT_EXTRACTOR_CLOUD_ENABLED", "1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "existing-key-must-not-be-used")
    monkeypatch.delenv("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", raising=False)
    c, _, _ = setup_client(tmp_path)
    assert c.get("/api/providers").json()["cloud"]["enabled"] is False
    monkeypatch.setenv("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", "test-only-key")
    c, _, _ = setup_client(tmp_path / "configured")
    response = c.get("/api/providers")
    assert response.json()["cloud"]["enabled"] and "test-only-key" not in response.text


def test_consent_budget_revision_idempotency_and_separate_artifact(tmp_path):
    stub = StubProvider()
    c, task, body = setup_client(tmp_path, stub)
    base = f"/api/tasks/{task['id']}"
    for changes in [{"allow_upload": False}, {"max_estimated_cost_cny": 0}, {"model": "unknown"}, {"request_id": "../../secret"}, {"source_revision": "b"*32}]:
        assert c.post(base+"/generations", json={**body, **changes}).status_code in {409, 422}
    assert stub.calls == 0
    original = c.get(base+"/preview?kind=work").content
    response = c.post(base+"/generations", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["state"] == "completed" and not result["preserves_source_rgb"]
    assert 0 < result["transparent_fraction"] < 1
    assert c.get(base).json()["rev"] == task["rev"]
    assert c.get(base+"/preview?kind=work").content == original
    assert c.post(base+"/generations", json=body).json() == result and stub.calls == 1
    assert c.post(base+"/generations", json={**body,"model":"qwen-image-2.1-pro","max_estimated_cost_cny":.25}).status_code == 409
    png = c.get(base+f"/generations/{body['request_id']}/image")
    assert Image.open(io.BytesIO(png.content)).getchannel("A").getextrema() == (0, 255)
    # A local edit and undo never deletes or applies the generated RGB artifact.
    c.post(base+"/segment", json={"method":"color"})
    assert c.get(base+f"/generations/{body['request_id']}/image").content == png.content
    c.post(base+"/history/undo")
    assert c.get(base+"/preview?kind=work").content == original
    assert len(c.get(base+"/generations").json()) == 1
    c.delete(base)
    assert c.get(base+f"/generations/{body['request_id']}/image").status_code == 404


def test_failed_and_interrupted_requests_cannot_be_replayed(tmp_path):
    stub = StubProvider(); stub.failure = True
    c, task, body = setup_client(tmp_path, stub)
    base = f"/api/tasks/{task['id']}/generations"
    assert c.post(base, json=body).status_code == 422
    assert c.post(base, json=body).status_code == 409 and stub.calls == 1
    assert c.get(base).json()[0]["state"] == "failed"
    record = tmp_path / "tasks" / task["id"] / f"generation-{body['request_id']}.json"
    saved = json.loads(record.read_text()); saved["state"] = "pending"; record.write_text(json.dumps(saved))
    assert c.post(base, json=body).status_code == 409 and stub.calls == 1


def test_local_mask_provider_preserves_existing_contract():
    image, _ = sample()
    mask, warnings = LOCAL_MASK_PROVIDER.segment(image, "color")
    assert mask.mode == "L" and mask.size == image.size and warnings
    assert LOCAL_MASK_PROVIDER.spec.preserves_source_rgb and not LOCAL_MASK_PROVIDER.spec.network
