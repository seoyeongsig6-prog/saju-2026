"""The Novelist 판매용 앱 전용 서버.

기존 The Life 게임 API와 화면을 전혀 등록하지 않는다. 판매 서비스는 이 모듈로
시작하고, 게임 서비스만 ``server.main``을 계속 사용한다.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# 이 진입점을 사용한 경우에는 Render 환경변수 설정 여부와 관계없이
# 판매용 기능 경계를 먼저 확정한 뒤 writer 모듈을 불러온다.
os.environ.setdefault("WRITER_LAUNCH_MODE", "1")

from . import db, writer


app = FastAPI(title="The Novelist")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "capacitor://localhost", "ionic://localhost",
        "http://localhost", "https://localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(writer.router)

WEB = Path(__file__).resolve().parent.parent / "web"
db.init()


@app.exception_handler(Exception)
async def safe_errors(request, exc):
    print(f"[novelist] {type(exc).__name__}: {exc}", flush=True)
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "잠시 문제가 생겼어요. 잠시 후 다시 시도해 주세요."},
    )


@app.get("/")
def index():
    return RedirectResponse("/writer")


@app.get("/writer")
def writer_page():
    return FileResponse(WEB / "writer.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        WEB / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/privacy")
def privacy_page():
    return FileResponse(WEB / "privacy.html")


@app.get("/terms")
def terms_page():
    return FileResponse(WEB / "terms.html")


@app.get("/api/health")
def health():
    return {"ok": True, "app": "novelist", "launch_mode": writer.LAUNCH_MODE,
            "db": db.status()}


class FreshStatic(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", FreshStatic(directory=WEB), name="static")
