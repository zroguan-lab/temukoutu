from pathlib import Path
from PIL import Image
import json
from .io import read_image, save_png, atomic_bytes, MAX_BYTES
from .transforms import crop
from .providers import LOCAL_MASK_PROVIDER
from .export import export_png
from .masks import adjust


def extract(input_path, output_path, roi=None, mask=None, method="auto", options=None):
    options = options or {}
    out = Path(output_path)
    mask_path = out.with_name(out.stem+".mask.png")
    if out.suffix.lower() != ".png":
        raise ValueError("输出路径必须使用 .png 扩展名")
    sources = {Path(input_path).resolve()}
    if mask is not None and not isinstance(mask,Image.Image):
        sources.add(Path(mask).resolve())
    if any(p.resolve() in sources for p in [out, mask_path, out.with_suffix('.json')]):
        raise ValueError("输出文件不能覆盖原图或输入蒙版")
    with Path(input_path).open('rb') as source:
        image = read_image(source.read(MAX_BYTES+1))
    if roi is not None:
        image = crop(image,roi)
    if mask is None:
        mask, warnings = LOCAL_MASK_PROVIDER.segment(image,method,options)
    else:
        mask = mask.convert("L") if isinstance(mask,Image.Image) else Image.open(mask).convert("L")
        warnings = ["用户蒙版，需人工检查细线与衣服残留"]
    mask = adjust(mask,options.get("smooth",0),options.get("feather",0),options.get("expand",0))
    metadata = export_png(image,mask,output_path,options.get("padding",12),options.get("scale",1),options.get("target_long_edge"))
    save_png(mask_path,mask)
    result = {"status":"needs_review","output_path":str(output_path),"mask_path":str(mask_path),"method":method,
            "version":"0.1.0","ai_used":False,"warnings":warnings,**metadata}
    atomic_bytes(Path(output_path).with_suffix(".json"),json.dumps(result,ensure_ascii=False,indent=2).encode())
    return result
