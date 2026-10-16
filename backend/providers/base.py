"""Shared generated-image intent and safe errors; no account or transport state."""

PROMPT = (
    "只提取参考衣服照片上的印花设计，移除衣物和周围背景，输出真正带透明 Alpha 通道的 PNG。"
    "保留全部原文字和标点、细杯脚、飞溅装饰、黑色眼镜、内部黑色轮廓与细毛发。"
    "区分衣物黑底与印花内部黑色，不要把内部黑色一并删除。"
    "不新增文字、图案或棋盘格，不改写文字，不重新设计，不添加阴影。"
)


class ProviderError(ValueError):
    """Safe user-facing error, without remote bodies, keys or signed URLs."""
