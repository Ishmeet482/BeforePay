"""Proxy tests never contact real backend, database or external providers."""

import httpx
import pytest
from fastapi.testclient import TestClient

from scripts import webhook_proxy as proxy


@pytest.fixture
def upstream(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"detail": "synthetic retry"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        proxy, "upstream_client", lambda: httpx.AsyncClient(transport=transport)
    )
    return calls


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/docs",
        "/openapi.json",
        "/api/bookings",
        "/api/paypal/sandbox/webhook/",
        "/api/paypal/sandbox/webhook?x=1",
        "/api/paypal/sandbox%2Fwebhook",
        "/api/paypal/sandbox/webhook/extra",
    ],
)
def test_other_paths_never_forward(upstream, path):
    with TestClient(proxy.app) as client:
        assert client.post(path, content=b"{}").status_code == 404
    assert upstream == []


@pytest.mark.parametrize(
    "method", ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]
)
def test_other_methods_never_forward(upstream, method):
    with TestClient(proxy.app) as client:
        assert client.request(method, proxy.PATH.decode()).status_code == 404
    assert upstream == []


def test_preserves_exact_body_and_signature_headers(upstream):
    body = b'{ "resource": {"text": "\\u0061"}, "id": "synthetic" }\n'
    headers = {
        "PayPal-Auth-Algo": "SHA256withRSA",
        "PayPal-Cert-Url": "https://example.invalid/cert",
        "PayPal-Transmission-Id": "synthetic-id",
        "PayPal-Transmission-Sig": "fake+/signature==",
        "PayPal-Transmission-Time": "2026-11-02T00:00:00Z",
        "Content-Type": "application/json",
        "Authorization": "Bearer do-not-forward",
        "Cookie": "do-not-forward",
        "X-Forwarded-Host": "example.invalid",
    }
    with TestClient(proxy.app) as client:
        response = client.post(proxy.PATH.decode(), content=body, headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "synthetic retry"}
    assert len(upstream) == 1
    request = upstream[0]
    assert str(request.url) == proxy.UPSTREAM and request.content == body
    for name, value in headers.items():
        if name.lower().startswith("paypal-") or name == "Content-Type":
            assert request.headers[name] == value
    for name in ("authorization", "cookie", "x-forwarded-host"):
        assert name not in request.headers


def test_oversize_never_forwarded(upstream, monkeypatch):
    monkeypatch.setattr(proxy, "MAX_REQUEST_BYTES", 4)
    with TestClient(proxy.app) as client:
        assert client.post(proxy.PATH.decode(), content=b"12345").status_code == 413
    assert upstream == []


def test_unavailable_backend_returns_retryable_error(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("synthetic failure")

    monkeypatch.setattr(
        proxy,
        "upstream_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with TestClient(proxy.app) as client:
        assert client.post(proxy.PATH.decode(), content=b"{}").status_code == 502
    assert len(calls) == 1
