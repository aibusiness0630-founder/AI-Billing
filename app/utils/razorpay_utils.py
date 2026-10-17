"""
Small Razorpay helper using only the Python standard library
(no extra pip package needed).

.env keys:
    RAZORPAY_KEY_ID
    RAZORPAY_KEY_SECRET
    RAZORPAY_WEBHOOK_SECRET
"""
import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

API_BASE = "https://api.razorpay.com/v1/"


class RazorpayError(Exception):
    pass


def get_keys():
    return (
        os.environ.get("RAZORPAY_KEY_ID", "").strip(),
        os.environ.get("RAZORPAY_KEY_SECRET", "").strip(),
    )


def get_webhook_secret():
    return os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()


def is_configured():
    key_id, key_secret = get_keys()
    return bool(key_id and key_secret)


def create_order(amount_paise, receipt, notes=None):
    """Create a Razorpay order. Returns the order dict (has 'id')."""
    key_id, key_secret = get_keys()

    if not (key_id and key_secret):
        raise RazorpayError("Razorpay keys are not configured")

    payload = {
        "amount": int(amount_paise),
        "currency": "INR",
        "receipt": str(receipt)[:40],
        "notes": notes or {},
    }

    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()

    req = urllib.request.Request(
        API_BASE + "orders",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Basic " + token,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        description = "request failed"
        try:
            body = json.loads(e.read().decode("utf-8"))
            description = body.get("error", {}).get("description", description)
        except Exception:
            pass
        raise RazorpayError(f"Razorpay: {description}")

    except Exception:
        raise RazorpayError("Could not reach Razorpay. Try again.")


def _hmac_hex(secret, message_bytes):
    return hmac.new(secret.encode("utf-8"), message_bytes, hashlib.sha256).hexdigest()


def verify_payment_signature(order_id, payment_id, signature, secret):
    """Checkout success signature: HMAC_SHA256(order_id|payment_id)."""
    if not (order_id and payment_id and signature and secret):
        return False

    expected = _hmac_hex(secret, f"{order_id}|{payment_id}".encode("utf-8"))
    return hmac.compare_digest(expected, str(signature))


def verify_webhook_signature(body_bytes, signature, secret):
    """Webhook signature: HMAC_SHA256(raw request body)."""
    if not (body_bytes and signature and secret):
        return False

    expected = _hmac_hex(secret, body_bytes)
    return hmac.compare_digest(expected, str(signature))
