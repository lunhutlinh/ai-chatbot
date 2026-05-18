from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.api.chude6_api import router as chude6_router


app = FastAPI(title="CHATBOT API")


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


BASE_DIR = Path(__file__).resolve().parents[2]
WEB_DIST_DIR = BASE_DIR / "web" / "dist"
if WEB_DIST_DIR.exists():
    app.mount(
        "/app",
        SPAStaticFiles(directory=str(WEB_DIST_DIR), html=True),
        name="web",
    )

WEB_TEMPLATES_INDEX = BASE_DIR / "web" / "templates" / "index.html"
WEB_STATIC_DIR = BASE_DIR / "web" / "static"
if WEB_TEMPLATES_INDEX.exists() and WEB_STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_STATIC_DIR)), name="static")
    app.mount("/ui/static", StaticFiles(directory=str(WEB_STATIC_DIR)), name="ui_static")


@app.get("/ui")
def ui_index():
    if not WEB_TEMPLATES_INDEX.exists():
        return {"error": "UI not installed", "hint": "Copy UI to web/templates and web/static"}
    return FileResponse(str(WEB_TEMPLATES_INDEX), media_type="text/html; charset=utf-8")


@app.get("/ui/")
def ui_index_slash():
    return ui_index()


@app.get("/")
def root():
    return {"service": "chatbot", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


app.include_router(chude6_router, prefix="/chude6")
