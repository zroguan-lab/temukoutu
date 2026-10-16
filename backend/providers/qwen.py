"""Qwen Image 2.1 JSON contract; verified with mocks, live quality unverified.

https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference
"""
import base64
import re
from urllib.parse import urlsplit

import httpx

from extractor_core.io import MAX_BYTES, png_bytes
from extractor_core.providers import ProviderSpec
from .base import PROMPT, ProviderError
from .images import transparent_png
from .generated import GeneratedImage

# Beijing list prices, checked 2026-10-15. One output per explicit request.
MODELS = {"qwen-image-2.1-turbo": 0.10, "qwen-image-2.1-pro": 0.25}
class QwenImageProvider:
    spec = ProviderSpec("qwen-image", "千问实验接口（未验证可用）", "generated_image", True, False)

    def __init__(self, api_key, workspace_id="", *, transport=None):
        if workspace_id and not re.fullmatch(r"[A-Za-z0-9-]{1,80}", workspace_id):
            raise ValueError("百炼业务空间 ID 格式无效")
        host = f"{workspace_id}.cn-beijing.maas.aliyuncs.com" if workspace_id else "dashscope.aliyuncs.com"
        self.endpoint = f"https://{host}/compatible-mode/v1/images/generations"
        self._api_key = api_key
        self._transport = transport

    @staticmethod
    def validate_input(image):
        if max(image.size) > 8000 or max(image.size) / min(image.size) > 10:
            raise ProviderError("千问输入长边最多 8000px，宽高比不超过 10:1；请先裁切")
        data = png_bytes(image)
        if len(data) > 10 * 1024 * 1024:
            raise ProviderError("千问输入 PNG 超过 10MB；请先缩小选区")
        return data

    def edit(self, image, model):
        try: return transparent_png(self.generate(image, model).data)
        except ValueError as exc: raise ProviderError(str(exc)) from None

    def generate(self, image, model):
        if model not in MODELS:
            raise ProviderError("未支持的千问图像型号")
        data = self.validate_input(image)
        payload = {"model": model, "prompt": PROMPT, "image": "data:image/png;base64," + base64.b64encode(data).decode(),
                   "n": 1, "prompt_extend": False, "watermark": False}
        try:
            # No retries, redirects, environment proxies, or auth headers on downloads.
            with httpx.Client(timeout=httpx.Timeout(90, connect=10), follow_redirects=False,
                              trust_env=False, transport=self._transport) as client:
                response = client.post(self.endpoint, json=payload,
                                       headers={"Authorization": "Bearer " + self._api_key})
                if response.status_code != 200:
                    raise ProviderError(f"千问实验请求失败（HTTP {response.status_code}）；尚未验证可用性，原因以服务响应为准。不会自动重试")
                try:
                    items = response.json()["data"]
                    if len(items) != 1:
                        raise ValueError("expected one output")
                    url = items[0]["url"]
                    parts = urlsplit(url)
                    if (parts.scheme != "https" or not parts.hostname or not parts.hostname.endswith(".aliyuncs.com")
                            or parts.username or parts.password or parts.port not in {None, 443}):
                        raise ValueError("untrusted result URL")
                except (KeyError, TypeError, ValueError):
                    raise ProviderError("千问返回了无效结果地址；未下载、未重试") from None
                with client.stream("GET", url) as download:
                    if download.status_code != 200:
                        raise ProviderError("生成图下载失败；请检查本地请求记录，勿直接重复付费")
                    content = bytearray()
                    for chunk in download.iter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_BYTES:
                            raise ProviderError("生成图超过 25MB；已中止下载")
            try:
                return GeneratedImage.decode(bytes(content))
            except ValueError as exc:
                raise ProviderError(str(exc)) from None
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, OSError):
            raise ProviderError("千问调用或解码失败，可能已计费；不会自动重试，请先核对服务端用量") from None
