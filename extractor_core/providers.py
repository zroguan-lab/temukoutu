"""Provider contracts distinguish source masks from newly generated pixels.

The core remains offline. Network adapters live in backend.providers.
"""
from dataclasses import dataclass
from typing import Literal, Protocol

from PIL import Image

from .segmentation import segment


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    output: Literal["source_mask", "generated_image"]
    network: bool
    preserves_source_rgb: bool


class MaskProvider(Protocol):
    spec: ProviderSpec

    def segment(self, image: Image.Image, method="auto", options=None, seed=None) -> tuple[Image.Image, list[str]]: ...


class ImageEditProvider(Protocol):
    spec: ProviderSpec

    def edit(self, image: Image.Image, model: str) -> Image.Image: ...


class LocalMaskProvider:
    spec = ProviderSpec("local", "本地颜色与 GrabCut", "source_mask", False, True)

    def segment(self, image, method="auto", options=None, seed=None):
        return segment(image, method, options, seed)


LOCAL_MASK_PROVIDER: MaskProvider = LocalMaskProvider()
