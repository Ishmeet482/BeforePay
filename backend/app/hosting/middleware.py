from pydantic import ValidationError
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.hosting.diagnostics import log_settings_failure


class HostingBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        try:
            settings = get_settings()
        except ValidationError as error:
            log_settings_failure(error)
            return await JSONResponse(
                {
                    "detail": {
                        "code": "public_setup_required",
                        "message": (
                            "Deployment configuration is incomplete. "
                            "Ask the organiser; no action was performed."
                        ),
                    }
                },
                status_code=503,
            )(scope, receive, send)
        if (
            settings.public_demo_mode
            and scope.get("path", "").startswith("/api/paypal/")
            and not settings.public_webhooks_enabled
        ):
            return await JSONResponse(
                {"detail": "Webhook exposure is disabled."}, status_code=404
            )(scope, receive, send)
        await self.app(scope, receive, send)
