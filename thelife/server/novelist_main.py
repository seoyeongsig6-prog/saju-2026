"""The Novelist 판매용 앱 전용 서버.

기존 The Life 게임 API와 화면을 전혀 등록하지 않는다. 판매 서비스는 이 모듈로
시작하고, 게임 서비스만 ``server.main``을 계속 사용한다.
"""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# 이 진입점을 사용한 경우에는 Render 환경변수 설정 여부와 관계없이
# 판매용 기능 경계를 먼저 확정한 뒤 writer 모듈을 불러온다.
os.environ.setdefault("WRITER_LAUNCH_MODE", "1")

from . import db, writer


app = FastAPI(title="The Novelist", docs_url=None, redoc_url=None, openapi_url=None)
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


@app.middleware("http")
async def production_security(request: Request, call_next):
    path = request.url.path
    try:
        if int(request.headers.get("content-length", "0")) > 10 * 1024 * 1024:
            return JSONResponse(status_code=413,
                                content={"ok": False, "error": "파일이나 내용이 너무 커요."})
    except ValueError:
        return JSONResponse(status_code=400, content={"ok": False, "error": "잘못된 요청이에요."})
    if path == "/api/writer/auth/device":
        client_ip = request.client.host if request.client else "unknown"
        if not writer.allow_device_registration(client_ip):
            return JSONResponse(status_code=429,
                                content={"ok": False, "error": "잠시 후 다시 시도해 주세요."})
    # 공개 등록, RevenueCat 웹훅과 운영자 API는 각각 별도 비밀값으로 검증한다.
    exempt = (path in ("/api/writer/auth/device", "/api/writer/auth/recover") or
              path == "/api/writer/rc-webhook" or
              path.startswith("/api/writer/admin/"))
    if path.startswith("/api/writer/") and not exempt:
        user = request.headers.get("X-User-Id", "")
        token = request.headers.get("X-Device-Token", "")
        if not writer.valid_device_token(user, token):
            return JSONResponse(status_code=401,
                                content={"ok": False, "error": "기기 인증이 필요해요."})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self' https: capacitor:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(Exception)
async def safe_errors(request, exc):
    # 예외 본문에는 DB 주소나 외부 API 응답이 섞일 수 있어 운영 로그에는 종류만 남긴다.
    print(f"[novelist] {type(exc).__name__}", flush=True)
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


@app.get("/delete-account")
def delete_account_page():
    """Google Play의 외부 계정·데이터 삭제 URL로 제출하는 공개 페이지."""
    return FileResponse(WEB / "delete-account.html")


@app.get("/api/health")
def health():
    state = db.status()
    ready = bool(writer.APP_AUTH_SECRET and state.get("using") == "postgres" and not writer.llm.is_mock)
    return {"ok": True, "ready": ready, "app": "novelist",
            "launch_mode": writer.LAUNCH_MODE, "database": state.get("using"),
            "ai_connected": not writer.llm.is_mock, "auth_configured": bool(writer.APP_AUTH_SECRET)}


class FreshStatic(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", FreshStatic(directory=WEB), name="static")
