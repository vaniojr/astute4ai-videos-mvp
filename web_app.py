#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests as _req
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
OUTPUTS  = BASE_DIR / "outputs"
CONFIGS  = BASE_DIR / "configs"

app       = FastAPI(title="Astute4AI Videos")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Serve outputs/ as static files — Starlette handles range requests correctly
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS)), name="outputs")

_proc:    Optional[asyncio.subprocess.Process] = None
_logs:    deque[str] = deque(maxlen=1000)
_running: bool = False

# ── pipeline runner state ──────────────────────────────────────────────────────
_pipe_proc:    Optional[asyncio.subprocess.Process] = None
_pipe_logs:    deque[str] = deque(maxlen=2000)
_pipe_running: bool = False

STEPS = [
    {"id": 1, "name": "News Collector",           "output": "collected_news.json"},
    {"id": 2, "name": "News Curator",              "output": "curated_news.json"},
    {"id": 3, "name": "Script Writer",             "output": "script.json"},
    {"id": 4, "name": "Editorial Validator",       "output": "script_validated.json"},
    {"id": 5, "name": "Content Packager",          "output": "content_package.json"},
    {"id": 6, "name": "Video Payload Builder",     "output": "video_payload.json"},
    {"id": 7, "name": "Publisher Payload Builder", "output": "publish_payload.json"},
    {"id": 8, "name": "Aprovação do Roteiro",      "output": "approval_status.json"},
    {"id": 9, "name": "Geração do Vídeo",          "output": "video_images.mp4"},
]

_ALLOWED_JSON = {s["output"] for s in STEPS if s["output"].endswith(".json")} | {"image_manifest.json"}

_OUTPUT_FILES = [
    "collected_news.json", "curated_news.json", "script.json",
    "script_validated.json", "content_package.json", "video_payload.json",
    "publish_payload.json", "approval_status.json", "image_manifest.json",
]


# ── pages ──────────────────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── pipeline status ────────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    steps = []
    for s in STEPS:
        path = OUTPUTS / s["output"]
        steps.append({**s, "done": path.exists()})

    approval = None
    ap = OUTPUTS / "approval_status.json"
    if ap.exists():
        approval = json.loads(ap.read_text(encoding="utf-8"))

    return {"steps": steps, "running": _running, "approval": approval, "pipe_running": _pipe_running}


# ── output files ───────────────────────────────────────────────────────────────

@app.get("/api/output/{filename}")
async def api_output(filename: str):
    if filename not in _ALLOWED_JSON:
        raise HTTPException(status_code=404)
    path = OUTPUTS / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo ainda não gerado")
    return json.loads(path.read_text(encoding="utf-8"))


# ── video streaming (player inline) ────────────────────────────────────────────

@app.get("/api/video")
async def api_video(request: Request):
    path = OUTPUTS / "video_images.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Vídeo ainda não gerado")

    file_size = path.stat().st_size
    range_hdr = request.headers.get("range", "").strip()

    start, end, status = 0, file_size - 1, 200
    if range_hdr:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", range_hdr)
        if m:
            s, e = m.group(1), m.group(2)
            if s:
                start = int(s)
                end   = int(e) if e else file_size - 1
            elif e:
                start = max(0, file_size - int(e))
            end = min(end, file_size - 1)
        if start > end or start >= file_size:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
        status = 206

    length = end - start + 1

    def _iter():
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                data = fh.read(min(1 << 16, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Type": "video/mp4",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(_iter(), status_code=status, headers=headers)


@app.get("/api/video/download")
async def api_video_download(request: Request):
    """Mesmo endpoint mas força download via Content-Disposition."""
    path = OUTPUTS / "video_images.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Vídeo ainda não gerado")
    return FileResponse(str(path), media_type="video/mp4",
                        filename="video_images.mp4")


# ── approval ───────────────────────────────────────────────────────────────────

class ApproveBody(BaseModel):
    decision: str
    notes: str = ""


@app.post("/api/approve")
async def api_approve(body: ApproveBody):
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision deve ser 'approved' ou 'rejected'")
    data = {
        "decision":   body.decision,
        "notes":      body.notes,
        "decided_at": datetime.now().isoformat(),
    }
    (OUTPUTS / "approval_status.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return data


# ── reset (novo vídeo) ─────────────────────────────────────────────────────────

class ResetBody(BaseModel):
    keep_video: bool = False


@app.post("/api/reset")
async def api_reset(body: ResetBody):
    deleted = []
    for name in _OUTPUT_FILES:
        p = OUTPUTS / name
        if p.exists():
            p.unlink()
            deleted.append(name)
    if not body.keep_video:
        p = OUTPUTS / "video_images.mp4"
        if p.exists():
            p.unlink()
            deleted.append("video_images.mp4")
    return {"deleted": deleted}


# ── sources ────────────────────────────────────────────────────────────────────

def _sources_path() -> Path:
    return CONFIGS / "sources.json"


@app.get("/api/sources")
async def api_sources_get():
    p = _sources_path()
    if not p.exists():
        return {"sources": []}
    return json.loads(p.read_text(encoding="utf-8"))


class SourcesBody(BaseModel):
    sources: list[dict]


@app.post("/api/sources")
async def api_sources_save(body: SourcesBody):
    _sources_path().write_text(
        json.dumps({"sources": body.sources}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"saved": len(body.sources)}


class TestBody(BaseModel):
    url: str


@app.post("/api/sources/test")
async def api_sources_test(body: TestBody):
    loop = asyncio.get_event_loop()

    def _check():
        try:
            r = _req.get(body.url, timeout=8, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
            return {"ok": r.ok, "status": r.status_code, "url": body.url}
        except Exception as exc:
            return {"ok": False, "status": 0, "error": str(exc), "url": body.url}

    return await loop.run_in_executor(None, _check)


# ── video generation ───────────────────────────────────────────────────────────

@app.post("/api/generate")
async def api_generate():
    global _proc, _running
    if _running:
        raise HTTPException(status_code=409, detail="Processo já em execução")
    _logs.clear()
    _running = True

    async def _run() -> None:
        global _proc, _running
        try:
            _proc = await asyncio.create_subprocess_exec(
                "python3", str(BASE_DIR / "generate_video_images.py"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(BASE_DIR),
            )
            assert _proc.stdout
            async for raw in _proc.stdout:
                _logs.append(raw.decode("utf-8", errors="replace").rstrip())
            await _proc.wait()
        finally:
            _running = False
            _proc = None

    asyncio.create_task(_run())
    return {"started": True}


@app.post("/api/cancel")
async def api_cancel():
    global _proc, _running
    if _proc:
        _proc.terminate()
        _running = False
        return {"cancelled": True}
    return {"cancelled": False}


@app.get("/api/logs")
async def api_logs(request: Request):
    async def _events():
        snapshot = list(_logs)
        for line in snapshot:
            yield f"data: {line}\n\n"
        sent = len(snapshot)
        tick = 0
        while True:
            if await request.is_disconnected():
                break
            current = list(_logs)
            for line in current[sent:]:
                yield f"data: {line}\n\n"
            sent = len(current)
            tick += 1
            if tick % 50 == 0:
                yield ": keepalive\n\n"
            if not _running and sent >= len(current):
                yield "event: done\ndata: \n\n"
                break
            await asyncio.sleep(0.1)

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── pipeline execution ─────────────────────────────────────────────────────────

def _pipe_launch(args: list[str]):
    """Return an async task that runs run_pipeline.py and streams to _pipe_logs."""
    async def _run() -> None:
        global _pipe_proc, _pipe_running
        try:
            _pipe_proc = await asyncio.create_subprocess_exec(
                "python3", str(BASE_DIR / "run_pipeline.py"), *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(BASE_DIR),
            )
            assert _pipe_proc.stdout
            async for raw in _pipe_proc.stdout:
                _pipe_logs.append(raw.decode("utf-8", errors="replace").rstrip())
            await _pipe_proc.wait()
        finally:
            _pipe_running = False
            _pipe_proc = None
    return _run()


@app.post("/api/pipeline/run")
async def api_pipeline_run():
    global _pipe_running
    if _pipe_running:
        raise HTTPException(status_code=409, detail="Pipeline já em execução")
    _pipe_logs.clear()
    _pipe_running = True
    asyncio.create_task(_pipe_launch([]))
    return {"started": True}


@app.post("/api/pipeline/finish")
async def api_pipeline_finish():
    global _pipe_running
    if _pipe_running:
        raise HTTPException(status_code=409, detail="Pipeline já em execução")
    _pipe_logs.clear()
    _pipe_running = True
    asyncio.create_task(_pipe_launch(["--finish"]))
    return {"started": True}


@app.post("/api/pipeline/cancel")
async def api_pipeline_cancel():
    global _pipe_proc, _pipe_running
    if _pipe_proc:
        _pipe_proc.terminate()
        _pipe_running = False
        return {"cancelled": True}
    return {"cancelled": False}


@app.get("/api/pipeline/logs")
async def api_pipeline_logs(request: Request):
    async def _events():
        snapshot = list(_pipe_logs)
        for line in snapshot:
            yield f"data: {line}\n\n"
        sent = len(snapshot)
        tick = 0
        while True:
            if await request.is_disconnected():
                break
            current = list(_pipe_logs)
            for line in current[sent:]:
                yield f"data: {line}\n\n"
            sent = len(current)
            tick += 1
            if tick % 50 == 0:
                yield ": keepalive\n\n"
            if not _pipe_running and sent >= len(current):
                yield "event: done\ndata: \n\n"
                break
            await asyncio.sleep(0.1)

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── app config (API keys) ──────────────────────────────────────────────────────

def _read_env() -> dict[str, str]:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _write_env_key(key: str, value: str) -> None:
    env_path = BASE_DIR / ".env"
    content  = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines    = content.splitlines()
    found    = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"# {key}="):
            new_lines.append(f'{key}="{value}"' if value else f"# {key}=")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f'{key}="{value}"')
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@app.get("/api/config")
async def api_config_get():
    env = _read_env()
    key = env.get("OPENAI_API_KEY", "")
    return {
        "openai_key_set": bool(key),
        "openai_key_preview": f"sk-...{key[-4:]}" if len(key) > 6 else ("(não configurada)" if not key else "***"),
    }


class ConfigBody(BaseModel):
    openai_api_key: str


@app.post("/api/config")
async def api_config_save(body: ConfigBody):
    import os
    _write_env_key("OPENAI_API_KEY", body.openai_api_key.strip())
    os.environ["OPENAI_API_KEY"] = body.openai_api_key.strip()
    return {"saved": True}


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
