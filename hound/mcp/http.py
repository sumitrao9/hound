"""HTTP (Streamable HTTP MCP) transport for hosted/24-7 Hound.

Endpoints:
  /mcp, /        - Streamable MCP (requires Bearer key when auth enabled)
  /health, /healthz - liveness
  /admin/keys    - POST create, GET list (Authorization: Bearer $HOUND_ADMIN_KEY)
  /admin/keys/revoke - POST {"key": "..."}
  /admin/usage   - GET usage summary
"""

from __future__ import annotations

import contextlib
import os
import secrets
from typing import Any

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from .metering import MeterStore
from .server import build_server


def _admin_key() -> str:
    return os.environ.get("HOUND_ADMIN_KEY", "").strip()


def _extract_bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    x = request.headers.get("x-api-key", "").strip()
    return x


def _is_admin(request: Request) -> bool:
    ak = _admin_key()
    token = _extract_bearer(request)
    return bool(ak and token and secrets.compare_digest(token, ak))


def create_app(meter: MeterStore | None = None) -> Starlette:
    server = build_server()
    session: Any = server.hound_session  # type: ignore[attr-defined]
    store = meter or MeterStore()
    session_manager = StreamableHTTPSessionManager(
        server,
        json_response=os.environ.get("HOUND_JSON_RESPONSE", "0") == "1",
        stateless=os.environ.get("HOUND_STATELESS", "0") == "1",
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        await session.start()
        async with session_manager.run():
            yield
        await session.stop()
        store.close()

    async def health(_request: Request):
        return PlainTextResponse("ok")

    async def mcp_guarded(scope, receive, send):
        # ASGI-level guard so we can wrap handle_request
        request = Request(scope, receive)
        path = request.url.path
        if not store.auth_required():
            return await session_manager.handle_request(scope, receive, send)
        token = _extract_bearer(request)
        ok, reason = store.check_and_record(token, path)
        if not ok:
            status = 401 if reason == "invalid_key" else 429
            resp = JSONResponse({"error": reason}, status_code=status)
            return await resp(scope, receive, send)
        return await session_manager.handle_request(scope, receive, send)

    async def admin_keys(request: Request):
        if not _is_admin(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if request.method == "GET":
            keys = store.list_keys()
            for k in keys:
                if k.get("key"):
                    k["key_preview"] = k["key"][:6] + "…" + k["key"][-4:]
            return JSONResponse({"keys": keys})
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        key = store.create_key(
            name=str(body.get("name", "")),
            rpm=body.get("rpm"),
            daily=body.get("daily"),
            token_daily=body.get("token_daily"),
        )
        return JSONResponse({"key": key, "name": body.get("name", "")}, status_code=201)

    async def admin_revoke(request: Request):
        if not _is_admin(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        revoked = store.revoke_key(str(body.get("key", "")))
        return JSONResponse({"revoked": revoked})

    async def admin_usage(request: Request):
        if not _is_admin(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        key = request.query_params.get("key")
        return JSONResponse({"usage": store.usage_summary(key)})

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/healthz", health),
            Route("/admin/keys", admin_keys, methods=["GET", "POST"]),
            Route("/admin/keys/revoke", admin_revoke, methods=["POST"]),
            Route("/admin/usage", admin_usage, methods=["GET"]),
            Mount("/mcp", app=mcp_guarded),
            Mount("/", app=mcp_guarded),
        ],
        lifespan=lifespan,
    )
    return app


def main() -> None:
    host = os.environ.get("HOUND_HOST", "0.0.0.0")
    port = int(os.environ.get("HOUND_PORT", os.environ.get("PORT", "8000")))
    uvicorn.run(create_app(), host=host, port=port, log_level=os.environ.get("HOUND_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
