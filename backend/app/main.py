import io
import os
import shutil
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image

from extractor_core.io import read_image, png_bytes, MAX_BYTES
from extractor_core.detection import detect
from extractor_core.transforms import crop, perspective
from extractor_core.providers import LOCAL_MASK_PROVIDER
from extractor_core.masks import adjust
from extractor_core.export import compose, export_png
from .storage import Store
from .cloud import install_cloud_routes

ROOT = Path(__file__).resolve().parents[2]
POOL = ThreadPoolExecutor(max_workers=2,thread_name_prefix="segmentation")


class RequestSizeLimit:
    """Bound chunked bodies before multipart parsing can spool unbounded files."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST","PUT","PATCH"}:
            return await self.app(scope,receive,send)
        messages = []
        async def collect():
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return False
                total += len(message.get("body",b""))
                if total > MAX_BYTES+1024*1024:
                    raise ValueError("body too large")
                messages.append(message)
                if not message.get("more_body",False):
                    return True
        try:
            connected = await asyncio.wait_for(collect(),timeout=30)
        except (ValueError, asyncio.TimeoutError) as exc:
            code = 413 if isinstance(exc,ValueError) else 408
            return await JSONResponse({"error":{"code":str(code),"message":"上传请求过大或超时"}},status_code=code)(scope,receive,send)
        if not connected:
            return
        cursor = 0
        async def replay():
            nonlocal cursor
            if cursor<len(messages):
                message=messages[cursor];cursor+=1;return message
            return await receive()
        await self.app(scope,replay,send)


class Selection(BaseModel):
    points: list[tuple[float,float]] = Field(min_length=3,max_length=200)


class SegmentRequest(BaseModel):
    method: Literal["auto","color","grabcut","manual"] = "auto"
    tolerance: float = Field(default=28,ge=2,le=150)
    use_seed: bool = False


class EdgeRequest(BaseModel):
    smooth: int = Field(default=0,ge=0,le=10)
    feather: float = Field(default=0,ge=0,le=20)
    expand: int = Field(default=0,ge=-20,le=20)


class ExportRequest(BaseModel):
    padding: int = Field(default=12,ge=0,le=200)
    scale: Literal[1,2,4] = 1
    target_long_edge: int | None = Field(default=None,ge=8,le=8192)


class CandidateRequest(BaseModel):
    name: Literal["color","grabcut","manual"]


def validate_ready(image, mask, info):
    if info["method"] in {"unprocessed","cropped"}:
        raise ValueError("尚未提取印花：请确认选区后生成分割候选，或用画笔移除衣服背景，再导出")
    # Evaluate content BEFORE padding: a transparent border is not extraction.
    alpha = compose(image,mask).getchannel("A")
    if alpha.getextrema()[0] == 255:
        raise ValueError("当前蒙版仍保留整张工作图，没有移除背景；请生成分割候选或使用擦除画笔")


def create_app(data_dir=None, *, image_edit_provider=None, config_path=None, account_providers=None):
    app = FastAPI(title="Print Extractor AI",version="0.1.0")
    app.add_middleware(RequestSizeLimit)
    store = Store(data_dir or os.environ.get("PRINT_EXTRACTOR_DATA",ROOT/"data"/"tasks"))
    app.state.store = store
    install_cloud_routes(app, store, image_edit_provider, config_path, account_providers)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        origin = request.headers.get("origin")
        allowed = {"http://127.0.0.1:7860","http://127.0.0.1:5173"}
        if host != "127.0.0.1" or (origin and origin not in allowed) or request.headers.get("sec-fetch-site")=="cross-site":
            return JSONResponse({"error":{"code":"local_only","message":"仅允许本地来源访问"}},status_code=403)
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length)>MAX_BYTES+1024*1024:
            return JSONResponse({"error":{"code":"too_large","message":"请求超过大小限制"}},status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Validation details must never echo a submitted credential or request body.
        details = [{"loc": e["loc"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"error":{"code":"validation","message":"参数无效","details":details}},status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"error":{"code":str(exc.status_code),"message":str(exc.detail)}},status_code=exc.status_code)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"error":{"code":"invalid_input","message":str(exc)}},status_code=422)

    @app.exception_handler(FileNotFoundError)
    async def not_found(request, exc):
        return JSONResponse({"error":{"code":"not_found","message":"任务或文件不存在"}},status_code=404)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logging.exception("Local request failed")
        return JSONResponse({"error":{"code":"processing_error","message":"处理失败，原始图片已保留；请检查服务日志"}},status_code=500)

    @app.get("/api/health")
    def health():
        return {"status":"ok","app":"print-extractor-ai","version":"0.1.0","models":[],"ai_used":False}

    def bounded_segment(image, method, options=None, seed=None):
        # Timed work is pure: a late result can never mutate a task.
        future = POOL.submit(LOCAL_MASK_PROVIDER.segment,image,method,options,seed)
        try:
            return future.result(timeout=45)
        except TimeoutError:
            future.cancel()
            raise HTTPException(504,"分割超过 45 秒，请缩小选区或使用手动画笔")

    @app.post("/api/tasks")
    def upload(file: UploadFile=File(...)):
        data = file.file.read(MAX_BYTES+1)
        image = read_image(data)
        return store.create(image)

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        with store.lock(task_id):
            return store.describe(task_id)

    @app.delete("/api/tasks/{task_id}")
    def delete(task_id: str):
        with store.lock(task_id):
            shutil.rmtree(store.path(task_id))
        return {"status":"deleted"}

    @app.post("/api/tasks/{task_id}/detect")
    def detection(task_id: str):
        with store.lock(task_id):
            image,_,_ = store.current(task_id)
            return detect(image)

    @app.post("/api/tasks/{task_id}/crop")
    def cropping(task_id: str, body: Selection):
        with store.lock(task_id):
            image,_,info = store.current(task_id)
            image = crop(image,body.points)
            return store.commit(task_id,image,image.getchannel("A"),{**info,"method":"cropped","warnings":["选区已裁切，请生成候选蒙版"]})

    @app.post("/api/tasks/{task_id}/transform")
    def transform(task_id: str, body: Selection):
        with store.lock(task_id):
            image,mask,info = store.current(task_id)
            image,mask = perspective(image,body.points,mask)
            return store.commit(task_id,image,mask,{**info,"transformed":True,"warnings":["已进行透视采样；只能修正近似平面，无法恢复褶皱遮挡内容"]})

    @app.post("/api/tasks/{task_id}/segment")
    def segmentation(task_id: str, body: SegmentRequest):
        with store.lock(task_id):
            image,mask,info = store.current(task_id)
            if body.use_seed and body.method not in {"auto","grabcut"}:
                raise ValueError("种子交互仅用于 GrabCut")
            seed = mask if body.use_seed else None
            mask,warnings = bounded_segment(image,body.method,{"tolerance":body.tolerance},seed)
            candidates = {"color":bounded_segment(image,"color",{"tolerance":body.tolerance})[0],
                          "grabcut": mask if body.method in {"auto","grabcut"} else bounded_segment(image,"grabcut",{"tolerance":body.tolerance})[0],
                          "manual":image.getchannel("A")}
            return store.commit(task_id,image,mask,{**info,"method":body.method,"warnings":warnings},candidates)

    @app.post("/api/tasks/{task_id}/candidate")
    def candidate(task_id: str, body: CandidateRequest):
        with store.lock(task_id):
            image,_,info = store.current(task_id)
            folder = store.path(task_id)/info["rev"]
            if body.name not in info["candidates"]:
                raise ValueError("当前状态没有此候选，请重新生成")
            candidates = {n:Image.open(folder/(n+".png")).copy() for n in info["candidates"]}
            return store.commit(task_id,image,candidates[body.name],{**info,"method":body.name},candidates)

    @app.put("/api/tasks/{task_id}/mask")
    def save_mask(task_id: str, file: UploadFile=File(...)):
        with store.lock(task_id):
            image,_,info = store.current(task_id)
            data = file.file.read(MAX_BYTES+1)
            mask = read_image(data).convert("L")
            if mask.size != image.size:
                raise ValueError("蒙版像素尺寸必须匹配工作图像")
            return store.commit(task_id,image,mask,{**info,"method":"interactive","warnings":["已保存手动蒙版，请检查细线和背景残留"]})

    @app.post("/api/tasks/{task_id}/edges")
    def edges(task_id: str, body: EdgeRequest):
        with store.lock(task_id):
            image,mask,info = store.current(task_id)
            return store.commit(task_id,image,adjust(mask,body.smooth,body.feather,body.expand),{**info,"edge_options":body.model_dump()})

    @app.post("/api/tasks/{task_id}/history/{direction}")
    def history(task_id: str, direction: Literal["undo","redo"]):
        with store.lock(task_id):
            return store.history(task_id,direction)

    @app.post("/api/tasks/{task_id}/reset")
    def reset(task_id: str):
        with store.lock(task_id):
            with Image.open(store.path(task_id)/"original.png") as src:
                image = src.copy()
            return store.commit(task_id,image,image.getchannel("A"),{"method":"unprocessed","transformed":False,"warnings":["已恢复原图，可撤销"]})

    @app.get("/api/tasks/{task_id}/preview")
    def preview(task_id: str, kind: Literal["result","work","original","mask"]="result"):
        with store.lock(task_id):
            image,mask,_ = store.current(task_id)
            if kind=="original":
                return Response((store.path(task_id)/"original.png").read_bytes(),media_type="image/png")
            return Response(png_bytes(mask if kind=="mask" else image if kind=="work" else compose(image,mask)),media_type="image/png")

    @app.post("/api/tasks/{task_id}/export")
    def exporting(task_id: str, body: ExportRequest):
        with store.lock(task_id):
            image,mask,info = store.current(task_id)
            validate_ready(image,mask,info)
            result = export_png(image,mask,store.path(task_id)/"output.png",body.padding,body.scale,body.target_long_edge)
            # Diagnostic flags are heuristics, never an accuracy score.
            import numpy as np
            alpha = np.asarray(compose(image,mask).getchannel("A"))
            edge = np.concatenate([alpha[0],alpha[-1],alpha[:,0],alpha[:,-1]])
            result.update({"status":"needs_review","warnings":info["warnings"],"possible_background_residue":bool((edge>127).mean()>.1),"transformed":info["transformed"],"ai_used":False})
            meta = store.meta(task_id)
            meta["export"] = result
            store.write_meta(task_id,meta)
            return result

    @app.get("/api/tasks/{task_id}/download")
    def download(task_id: str):
        with store.lock(task_id):
            image,mask,info = store.current(task_id)
            validate_ready(image,mask,info)
            path = store.path(task_id)/"output.png"
            if not store.meta(task_id).get("export") or not path.exists():
                raise HTTPException(404,"请先导出当前蒙版")
            return Response(path.read_bytes(),media_type="image/png",headers={"Content-Disposition":'attachment; filename="print-extracted.png"'})

    dist = ROOT/"frontend"/"dist"
    if dist.is_dir():
        app.mount("/",StaticFiles(directory=dist,html=True),name="frontend")
    return app


app = create_app()
