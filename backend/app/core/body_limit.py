from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.evidence.limits import MAX_REQUEST_BYTES


class RequestBodyLimit:
    """Bound raw bodies before JSON/multipart parsing, including chunked requests."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        body = bytearray()
        settings = get_settings()
        maximum = (
            min(MAX_REQUEST_BYTES, settings.demo_pdf_max_bytes + 64 * 1024)
            if settings.public_demo_mode
            and scope.get("path", "").startswith("/api/bookings")
            else MAX_REQUEST_BYTES
        )
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > maximum:
                await JSONResponse(
                    status_code=413,
                    content={"detail": "Request exceeds the upload body limit."},
                )(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
