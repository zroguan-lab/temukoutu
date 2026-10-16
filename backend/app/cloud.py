"""Provider orchestration and immutable generated originals, outside mask history."""
import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, SecretStr

from extractor_core.io import atomic_bytes
from extractor_core.providers import LOCAL_MASK_PROVIDER
from backend.providers.base import ProviderError
from backend.providers.generated import GeneratedImage
from backend.providers.qwen import MODELS, QwenImageProvider
from .connections import Connections
from .settings import (CloudSettings, SettingsError, user_config_path, runtime_settings,
                       validate_settings, write_settings)

MODEL_PROVIDERS = {"gpt-image": "gpt", "grok-native": "grok", **{m: "qwen" for m in MODELS}}


class GenerateRequest(BaseModel):
    model: Literal["gpt-image", "grok-native", "qwen-image-2.1-turbo", "qwen-image-2.1-pro"]
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    source_revision: str = Field(pattern=r"^[a-f0-9]{32}$")
    allow_upload: bool = False
    allow_account_usage: bool = False
    max_estimated_cost_cny: float = Field(default=0, ge=0, le=1)


class SettingsRequest(BaseModel):
    api_key: SecretStr | None = None
    enabled: bool = True
    workspace_id: str = ""


def install_cloud_routes(app, store, provider=None, config_path=None, account_providers=None):
    config_path = Path(config_path or user_config_path())
    settings_lock = threading.RLock()
    app.state.settings_error = ""
    try:
        settings = runtime_settings(config_path)
    except SettingsError as exc:
        settings = CloudSettings()
        app.state.settings_error = str(exc)
    app.state.cloud_settings = settings
    app.state.image_edit_provider = provider or (QwenImageProvider(settings.api_key, settings.workspace_id) if settings.enabled else None)
    connections = Connections(config_path, account_providers)
    app.state.connections = connections

    @app.get("/api/settings")
    def settings_status():
        return {**app.state.cloud_settings.public(), "error": app.state.settings_error}

    @app.put("/api/settings")
    def save_settings(body: SettingsRequest):
        with settings_lock:
            supplied_key = body.api_key.get_secret_value() if body.api_key else ""
            previous = app.state.cloud_settings
            settings = validate_settings(body.enabled, supplied_key or previous.api_key, body.workspace_id)
            write_settings(config_path, settings)
            app.state.cloud_settings, app.state.settings_error = settings, ""
            app.state.image_edit_provider = QwenImageProvider(settings.api_key, settings.workspace_id) if settings.enabled else None
            return settings.public()

    @app.delete("/api/settings")
    def clear_settings():
        with settings_lock:
            config_path.unlink(missing_ok=True)
            app.state.cloud_settings, app.state.image_edit_provider, app.state.settings_error = CloudSettings(), None, ""
            return app.state.cloud_settings.public()

    @app.get("/api/providers")
    def providers():
        qwen = {**asdict(QwenImageProvider.spec), "enabled": app.state.image_edit_provider is not None,
                "key_configured": bool(app.state.cloud_settings.api_key), "configuration_error": app.state.settings_error,
                "models": MODELS, "region": "cn-beijing", "price_checked": "2026-10-15",
                "verification": "mock_contract_only", "quality_verified": False, "experimental": True, "generation_verified": False}
        return {"local": asdict(LOCAL_MASK_PROVIDER.spec), "cloud": qwen,
                "connections": {name: connections.public(name) for name in ("gpt", "grok")},
                "models": [{"id": "gpt-image", "provider": "gpt", "label": "GPT · Codex 登录", "account_usage": True},
                           {"id": "grok-native", "provider": "grok", "label": "Grok · Build 登录", "account_usage": True}]}

    @app.get("/api/connections/{name}")
    def connection(name: str): return connections.public(name)

    @app.post("/api/connections/{name}/check")
    def check_connection(name: str): return connections.check(name)

    @app.post("/api/connections/{name}/login")
    def login(name: str): return connections.login(name)

    def record_path(task_id, request_id):
        if len(request_id) != 32 or any(c not in "0123456789abcdef" for c in request_id):
            raise HTTPException(404, "生成记录不存在")
        return store.path(task_id)/f"generation-{request_id}.json"

    def read_record(task_id, request_id):
        record = record_path(task_id, request_id)
        saved = json.loads(record.read_text(encoding="utf-8"))
        if saved["state"] != "completed": raise HTTPException(404, "此请求没有可用生成图")
        extension = saved.get("format", "png")
        if extension not in {"png", "jpg", "webp"}: raise HTTPException(404, "生成图格式无效")
        return record, saved, record.with_suffix("."+extension)

    @app.get("/api/tasks/{task_id}/generations")
    def generations(task_id: str):
        with store.lock(task_id):
            return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(store.path(task_id).glob("generation-*.json"))]

    @app.post("/api/tasks/{task_id}/generations")
    def generate(task_id: str, body: GenerateRequest):
        name = MODEL_PROVIDERS[body.model]
        with store.lock(task_id):
            # Resolve idempotency before any auth/network operation, including failed attempts.
            record = record_path(task_id, body.request_id)
            if record.exists():
                saved = json.loads(record.read_text(encoding="utf-8"))
                if saved["model"] != body.model or saved["source_revision"] != body.source_revision:
                    raise HTTPException(409, "请求 ID 已用于不同图像或型号")
                if saved["state"] == "completed": return saved
                raise HTTPException(409, "此请求已尝试，可能已使用额度；请先核对生成记录与用量，不会重复提交")
            if not body.allow_upload: raise HTTPException(422, "请先同意将当前工作图上传到所选官方服务")
            if name == "qwen":
                adapter = app.state.image_edit_provider
                if adapter is None: raise HTTPException(409, "请先配置并启用百炼 API Key；本地提取仍可用")
                if body.max_estimated_cost_cny < MODELS[body.model]: raise HTTPException(422, "请确认本次预计费用")
            else:
                if not body.allow_account_usage: raise HTTPException(422, "请先同意使用所选账号额度")
                adapter = connections.adapter(name)
            image, _, info = store.current(task_id)
            if body.source_revision != info["rev"]: raise HTTPException(409, "工作图已改变，请重新检查后再生成")
            if name == "qwen": QwenImageProvider.validate_input(image)
            usage_lock = connections.usage_locks[name]
            if not usage_lock.acquire(blocking=False): raise HTTPException(409, "此账号正在处理另一项请求，请稍后再试")
            saved = {"id": body.request_id, "source_revision": info["rev"], "provider": name, "model": body.model,
                     "state": "pending", "estimated_cost_cny": MODELS.get(body.model), "status": "needs_review",
                     "preserves_source_rgb": False, "warning": "AI 可能改变文字和纹样，请与原图核对；需要时继续精修"}
            def persist(): atomic_bytes(record, json.dumps(saved, ensure_ascii=False).encode())
            try:
                persist()
                result = adapter.generate(image, body.model) if hasattr(adapter, "generate") else GeneratedImage.from_image(adapter.edit(image, body.model))
                if not isinstance(result, GeneratedImage): raise ProviderError("服务没有返回可验证的生成图")
                atomic_bytes(record.with_suffix("."+result.extension), result.data)
                saved.update(state="completed", **result.public())
                persist()
            except Exception as exc:
                saved.update(state="failed", error=str(exc) if isinstance(exc, ProviderError) else "生成未完成，请检查服务、登录和用量；不会自动重试")
                persist()
                connections.expired(name)
                raise ProviderError(saved["error"]) from None
            finally:
                usage_lock.release()
            return saved

    @app.get("/api/tasks/{task_id}/generations/{request_id}/image")
    def generated_image(task_id: str, request_id: str):
        with store.lock(task_id):
            _, saved, path = read_record(task_id, request_id)
            return Response(path.read_bytes(), media_type=saved.get("media_type", "image/png"), headers={
                "Content-Disposition": f'attachment; filename="generated-original.{saved.get("format", "png")}"'})

    @app.post("/api/tasks/{task_id}/generations/{request_id}/refine")
    def refine(task_id: str, request_id: str):
        with store.lock(task_id):
            _, saved, path = read_record(task_id, request_id)
            result = GeneratedImage.decode(path.read_bytes())
            return store.create(result.image, provenance={"task_id": task_id, "generation_id": request_id,
                "provider": saved.get("provider", "qwen"), "model": saved["model"], "transparent": result.transparent})
