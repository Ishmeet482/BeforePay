"""Fixed sandbox transport. No live URL, redirects, automatic retries or raw logs."""

import re

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

BASE = "https://api-m.sandbox.paypal.com"
SDK = "https://www.sandbox.paypal.com/web-sdk/v6/core"


class PayPalFailure(Exception):
    def __init__(self, code, status=None):
        super().__init__(code)
        self.code = code
        self.status = status


def configured():
    settings = get_settings()
    return bool(
        settings.paypal_environment == "sandbox"
        and settings.paypal_sandbox_enabled
        and settings.paypal_sandbox_client_id.strip()
        and settings.paypal_sandbox_merchant_id.strip()
        and settings.paypal_sandbox_client_secret
        and settings.paypal_sandbox_client_secret.get_secret_value().strip()
    )


def require_configured():
    if not configured():
        raise HTTPException(
            503,
            {
                "code": "paypal_sandbox_not_configured",
                "message": "Enable sandbox and configure backend sandbox "
                "client ID, secret and merchant ID.",
            },
        )


def provider_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise PayPalFailure("paypal_invalid_identifier")
    return value


class SandboxPayPal:
    def __init__(self):
        self.token = None

    def _client(self):
        return httpx.Client(timeout=15, follow_redirects=False, trust_env=False)

    def _request(self, method, path, *, payload=None, key=None):
        require_configured()
        settings = get_settings()
        try:
            with self._client() as client:
                if self.token is None:
                    auth = client.post(
                        BASE + "/v1/oauth2/token",
                        auth=(
                            settings.paypal_sandbox_client_id,
                            settings.paypal_sandbox_client_secret.get_secret_value(),
                        ),
                        data={"grant_type": "client_credentials"},
                    )
                    auth.raise_for_status()
                    token = auth.json().get("access_token")
                    if not isinstance(token, str) or not token:
                        raise PayPalFailure("paypal_auth_invalid")
                    self.token = token
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Prefer": "return=representation",
                }
                if key:
                    headers["PayPal-Request-Id"] = key
                response = client.request(
                    method, BASE + path, headers=headers, json=payload
                )
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise PayPalFailure("paypal_invalid_response")
                return result
        except httpx.TimeoutException as error:
            raise PayPalFailure("paypal_timeout") from error
        except httpx.HTTPStatusError as error:
            raise PayPalFailure(
                "paypal_http_error", error.response.status_code
            ) from error
        except (httpx.RequestError, ValueError) as error:
            raise PayPalFailure("paypal_unavailable_or_invalid_response") from error

    def create(self, attempt):
        merchant = get_settings().paypal_sandbox_merchant_id
        return self._request(
            "POST",
            "/v2/checkout/orders",
            key=attempt.create_key,
            payload={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": str(attempt.id),
                        "custom_id": str(attempt.id),
                        "invoice_id": f"contextkey-{attempt.id}",
                        "payee": {"merchant_id": merchant},
                        "amount": {
                            "currency_code": attempt.currency,
                            "value": attempt.amount,
                        },
                    }
                ],
                "payment_source": {
                    "paypal": {
                        "experience_context": {
                            "shipping_preference": "NO_SHIPPING",
                            "user_action": "PAY_NOW",
                        }
                    }
                },
            },
        )

    def get(self, order_id):
        return self._request("GET", f"/v2/checkout/orders/{provider_id(order_id)}")

    def verify_webhook(self, event, headers):
        webhook_id = get_settings().paypal_sandbox_webhook_id.strip()
        if not webhook_id:
            raise HTTPException(503, "Sandbox webhook ID is not configured")
        payload = {"webhook_id": webhook_id, "webhook_event": event}
        for field in (
            "auth_algo",
            "cert_url",
            "transmission_id",
            "transmission_sig",
            "transmission_time",
        ):
            value = headers.get("paypal-" + field.replace("_", "-"))
            if not value or len(value) > 4096:
                raise HTTPException(400, "Missing or invalid PayPal signature headers")
            payload[field] = value
        # Certificate URL is data sent to PayPal, never a local fetch target.
        result = self._request(
            "POST", "/v1/notifications/verify-webhook-signature", payload=payload
        )
        if result.get("verification_status") != "SUCCESS":
            raise HTTPException(400, "PayPal webhook signature verification failed")

    def capture(self, attempt):
        return self._request(
            "POST",
            f"/v2/checkout/orders/{provider_id(attempt.order_id)}/capture",
            key=attempt.capture_key,
            payload={},
        )


def get_paypal():
    return SandboxPayPal()
