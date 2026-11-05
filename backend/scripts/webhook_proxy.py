"""Local development gate. Tunnel only this app, never the full backend port."""

import httpx
from fastapi import FastAPI, Request
from starlette.responses import Response

from app.evidence.limits import MAX_REQUEST_BYTES

PATH = b"/api/paypal/sandbox/webhook"
UPSTREAM = "http://127.0.0.1:8000" + PATH.decode()
app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


def upstream_client():
    return httpx.AsyncClient(timeout=45, follow_redirects=False, trust_env=False)


@app.middleware("http")
async def exact_webhook_only(request: Request, call_next):
    # Check raw bytes too: encoded slashes, aliases and trailing slashes fail shut.
    if (
        request.method != "POST"
        or request.scope.get("raw_path") != PATH
        or request.scope.get("query_string")
    ):
        return Response(status_code=404)
    return await call_next(request)


@app.post(PATH.decode())
async def forward(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            return Response(status_code=413)
        body.extend(chunk)
    # No JSON parsing, reserialization, credentials, cookies or forwarded routing.
    # Raw header values retain signature material; HTTPX supplies Host/framing.
    headers = [
        (key, value)
        for key, value in request.headers.raw
        if key.lower().startswith(b"paypal-")
        or key.lower() in {b"content-type", b"content-encoding"}
    ]
    try:
        async with upstream_client() as client:
            result = await client.post(UPSTREAM, content=bytes(body), headers=headers)
    except httpx.RequestError:
        # No retries: backend may already have processed this notification.
        return Response(status_code=502)
    # Relay status unchanged so verification/reconciliation failures invite retry.
    # HTTPX decodes response content; don't forward stale compression/framing.
    return Response(
        content=result.content,
        status_code=result.status_code,
        headers={
            "content-type": result.headers.get("content-type", "application/json")
        },
    )
