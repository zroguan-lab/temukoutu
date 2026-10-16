"""File acceptance is shared across generated-image providers, never a quality claim."""
import io
from PIL import Image
from extractor_core.io import read_image


def transparent_png(data):
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != "PNG" or ("A" not in probe.getbands() and "transparency" not in probe.info):
                raise ValueError("生成图没有真实 PNG Alpha 通道；未作为透明结果保存")
        result = read_image(data)
    except (OSError, SyntaxError):
        raise ValueError("生成图不是可解码的 PNG") from None
    low, high = result.getchannel("A").getextrema()
    if low != 0 or high == 0:
        raise ValueError("生成图缺少全透明背景或前景为空；请勿把棋盘格当透明")
    return result
