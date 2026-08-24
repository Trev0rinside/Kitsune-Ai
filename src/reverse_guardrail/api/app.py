"""FastAPI application factory for Reverse-Guardrail."""

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from reverse_guardrail.api.routes import router
from reverse_guardrail.core.scope_guard import ScopeAuthorizationError


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Reverse-Guardrail Security Testing API",
        description="Automated red-teaming pipeline for LLM Guardrail system prompt leakage assessment.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ScopeAuthorizationError)
    async def scope_authorization_exception_handler(
        request: Request, exc: ScopeAuthorizationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": "KILL_SWITCH_BLOCKED",
                "message": str(exc),
                "hint": "Ensure 'target.authorized: true' and a valid 'engagement_id' are configured.",
            },
        )

    # Mount static assets
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_index():
            index_path = os.path.join(static_dir, "index.html")
            return FileResponse(index_path)

    # Mount WebSocket relay endpoint for Chrome Extension
    from fastapi import WebSocket, WebSocketDisconnect
    from reverse_guardrail.core.relay_manager import relay_manager

    @app.websocket("/ws/relay")
    async def websocket_relay_endpoint(websocket: WebSocket):
        await websocket.accept()
        await relay_manager.register(websocket)
        try:
            while True:
                data_str = await websocket.receive_text()
                await relay_manager.handle_incoming_message(data_str)
        except WebSocketDisconnect:
            await relay_manager.unregister(websocket)
        except Exception:
            await relay_manager.unregister(websocket)

    app.include_router(router)
    return app


app = create_app()
