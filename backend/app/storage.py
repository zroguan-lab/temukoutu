import json
import re
import shutil
import threading
import uuid
from pathlib import Path
from PIL import Image
from extractor_core.io import atomic_bytes, save_png


class Store:
    """Immutable revision directories; meta.json is the sole current-state pointer."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.locks = {}
        self.guard = threading.RLock()

    def path(self, task_id):
        if not re.fullmatch(r"[a-f0-9]{32}",task_id):
            raise FileNotFoundError("任务不存在")
        path = self.root / task_id
        if not (path / "meta.json").is_file():
            raise FileNotFoundError("任务不存在或已删除")
        return path

    def lock(self, task_id):
        with self.guard:
            return self.locks.setdefault(task_id,threading.RLock())

    def meta(self, task_id):
        return json.loads((self.path(task_id)/"meta.json").read_text(encoding="utf-8"))

    def write_meta(self, task_id, meta):
        atomic_bytes(self.root/task_id/"meta.json", json.dumps(meta,ensure_ascii=False).encode())

    def create(self, image, provenance=None):
        task_id = uuid.uuid4().hex
        path = self.root/task_id
        path.mkdir()
        save_png(path/"original.png",image)
        self.write_meta(task_id,{"id":task_id,"history":[],"cursor":-1,"version":"0.1.0"})
        meta = self.meta(task_id)
        if provenance:
            meta["provenance"] = provenance
            self.write_meta(task_id, meta)
        transparent = bool(provenance and provenance.get("transparent"))
        warning = ("AI 生成图：请对照原商品图检查文字与细节，原生成文件已保留" if transparent
                   else "AI 生成图尚无透明背景，请生成分割候选或用画笔清理背景；原生成文件已保留" if provenance
                   else "请先确认印花选区，再生成候选蒙版")
        self.commit(task_id,image,image.getchannel("A"),{"method":"generated" if transparent else "unprocessed","transformed":False,"warnings":[warning]})
        return self.describe(task_id)

    def current(self, task_id):
        meta = self.meta(task_id)
        entry = meta["history"][meta["cursor"]]
        folder = self.path(task_id)/entry["rev"]
        with Image.open(folder/"work.png") as im:
            image = im.copy()
        with Image.open(folder/"mask.png") as im:
            mask = im.copy()
        return image,mask,entry

    def commit(self, task_id, image, mask, info, candidates=None):
        meta = self.meta(task_id)
        rev = uuid.uuid4().hex
        folder = self.path(task_id)/rev
        folder.mkdir()
        save_png(folder/"work.png",image)
        save_png(folder/"mask.png",mask)
        for name, candidate in (candidates or {}).items():
            save_png(folder/(name+".png"),candidate)
        entry = {**info,"rev":rev,"width":image.width,"height":image.height,
                 "candidates":list(candidates or {}),"ai_used":bool(meta.get("provenance")),"status":"needs_review"}
        history = meta["history"][:meta["cursor"]+1] + [entry]
        meta["history"] = history[-20:]
        meta["cursor"] = len(meta["history"])-1
        meta.pop("export",None)
        self.write_meta(task_id,meta)
        (self.path(task_id)/"output.png").unlink(missing_ok=True)
        keep = {e["rev"] for e in meta["history"]}
        for child in self.path(task_id).iterdir():
            if child.is_dir() and child.name not in keep:
                shutil.rmtree(child)
        return self.describe(task_id)

    def describe(self, task_id):
        meta = self.meta(task_id)
        entry = meta["history"][meta["cursor"]]
        return {**entry,"id":task_id,"version":meta["version"],"can_undo":meta["cursor"]>0,
                "can_redo":meta["cursor"]<len(meta["history"])-1,"export":meta.get("export"),"provenance":meta.get("provenance")}

    def history(self, task_id, direction):
        meta = self.meta(task_id)
        cursor = meta["cursor"] + (-1 if direction=="undo" else 1)
        if not 0<=cursor<len(meta["history"]):
            raise ValueError("没有可恢复的操作")
        meta["cursor"] = cursor
        meta.pop("export",None)
        self.write_meta(task_id,meta)
        (self.path(task_id)/"output.png").unlink(missing_ok=True)
        return self.describe(task_id)
