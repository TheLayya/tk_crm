from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse
from starlette.responses import Response
from starlette.types import Scope
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        path = path.replace(chr(92), "/")
        if path == "api" or path.startswith("api/"):
            return PlainTextResponse("Not Found", status_code=404)
        if path in {"login", "login/"}:
            return await super().get_response("index.html", scope)
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or Path(path).suffix or scope["method"] not in {"GET", "HEAD"}:
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI, directory: str) -> None:
    if not (Path(directory) / "index.html").is_file():
        raise RuntimeError("Desktop frontend index.html is missing")

    app.mount("/", FrontendFiles(directory=directory, html=True), name="frontend")
