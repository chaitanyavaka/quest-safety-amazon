import os
import socket
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from routes.amazon_metrics_routes import router as amazon_metrics_router
from routes.research_routes import router as research_router
from services.analysis_store import clear_current_analysis

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
SESSION_COOKIE = "qs_user_v2"
DEMO_USERS = {
    "quest": "12345678",
    "admin": "12345678",
    "analyst": "12345678",
}

app = FastAPI(
    title="QuestSafety SP-API Sandbox Backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "running"}


app.include_router(amazon_metrics_router)
app.include_router(research_router)


def _is_authenticated(request: Request) -> bool:
    username = request.cookies.get(SESSION_COOKIE)
    return bool(username and username in DEMO_USERS)


def _protected_template(request: Request, filename: str):
    if not _is_authenticated(request):
        return RedirectResponse("/login", status_code=303)

    return FileResponse(TEMPLATE_DIR / filename, headers={"Cache-Control": "no-store"})


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    return FileResponse(TEMPLATE_DIR / "login.html", headers={"Cache-Control": "no-store"})


@app.post("/api/auth/login")
async def auth_login(request: Request):
    payload = await request.json()
    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", ""))

    if DEMO_USERS.get(username) != password:
        return JSONResponse(
            {"success": False, "message": "Invalid username or password."},
            status_code=401,
        )

    clear_current_analysis()
    response = JSONResponse({"success": True, "username": username})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=username,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    response.delete_cookie("qs_user")
    return response


@app.get("/api/auth/session")
def auth_session(request: Request):
    username = request.cookies.get(SESSION_COOKIE)
    return {
        "authenticated": _is_authenticated(request),
        "username": username if username in DEMO_USERS else None,
    }


@app.post("/api/auth/logout")
def auth_logout():
    clear_current_analysis()
    response = JSONResponse({"success": True})
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie("qs_user")
    return response


@app.get("/", include_in_schema=False)
def frontend_index(request: Request):
    return RedirectResponse("/login", status_code=303)


@app.get("/pipeline", include_in_schema=False)
def frontend_pipeline(request: Request):
    return _protected_template(request, "main.html")


@app.get("/review", include_in_schema=False)
def frontend_review(request: Request):
    return _protected_template(request, "review.html")


@app.get("/dashboard", include_in_schema=False)
def frontend_dashboard(request: Request):
    return _protected_template(request, "dashboard.html")


@app.get("/metrics", include_in_schema=False)
def frontend_metrics(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse("/login", status_code=303)

    return RedirectResponse("/dashboard", status_code=303)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def _local_port() -> int:
    preferred_port = int(os.getenv("PORT", "8000"))

    if "PORT" in os.environ:
        return preferred_port

    if _is_port_free(preferred_port):
        return preferred_port

    for port in range(preferred_port + 1, preferred_port + 20):
        if _is_port_free(port):
            print(
                f"Port {preferred_port} is busy. Starting local app on http://127.0.0.1:{port}",
                flush=True,
            )
            return port

    raise RuntimeError("No free local port found between 8000 and 8019.")


if __name__ == "__main__":
    port = _local_port()
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=port,
    )
