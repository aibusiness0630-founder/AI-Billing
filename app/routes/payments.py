import json
import os
from datetime import datetime, timedelta

from flask import Blueprint, request, session, jsonify

from app import db
from app.models import (
    Shop, Subscription, SubscriptionPayment, SubscriptionOrder, AuditLog
)
from app.utils.decorators import shop_session_required
from app.utils.plans import PLAN_PRICES, PLAN_DAYS
from app.utils import razorpay_utils as rzp

payments_bp = Blueprint("payments", __name__, url_prefix="/payment")


def _json_error(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def _csrf_ok():
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return False
    token = request.headers.get("X-CSRF-Token", "")
    return bool(token) and token == session.get("csrf_token")


def fulfill_order(order_id, payment_id):
    """Activate / extend the subscription for a paid order.
    Safe to call many times (verify + webhook both call it)."""

    order = (
        SubscriptionOrder.query
        .filter_by(razorpay_order_id=order_id)
        .with_for_update()
        .first()
    )

    if not order:
        return None

    if order.status == "PAID":
        return order

    today = datetime.now().date()

    sub = Subscription.query.filter_by(shop_id=order.shop_id).first()

    if not sub:
        sub = Subscription(shop_id=order.shop_id, start_date=today)
        db.session.add(sub)

    if sub.expiry_date and sub.expiry_date >= today:
        base = sub.expiry_date
    else:
        base = today

    sub.expiry_date = base + timedelta(days=order.days)
    sub.plan = order.plan
    sub.status = "Active"
    sub.reminder_sent = False

    if not sub.start_date:
        sub.start_date = today

    db.session.add(SubscriptionPayment(
        shop_id=order.shop_id,
        amount=order.amount,
        method="Razorpay",
        plan=order.plan,
        days=order.days,
        note=(payment_id or "")[:255] or None,
        created_by="razorpay"
    ))

    db.session.add(AuditLog(
        shop_id=order.shop_id,
        user_id=None,
        action="SUBSCRIPTION_PAID",
        entity_type="SHOP",
        entity_id=order.shop_id,
        details=f"Razorpay {payment_id}: {order.plan} {order.days} days Rs.{order.amount:g}",
        ip_address=request.remote_addr
    ))

    order.status = "PAID"
    order.razorpay_payment_id = payment_id
    order.paid_at = datetime.utcnow()

    db.session.commit()
    return order


@payments_bp.route("/create_order", methods=["POST"])
@shop_session_required
def create_order():

    if not _csrf_ok():
        return _json_error("Session expired. Refresh the page.", 400)

    if not rzp.is_configured():
        return _json_error("Online payment is not set up yet.", 503)

    data = request.get_json(silent=True) or {}
    plan = data.get("plan")

    if plan not in PLAN_PRICES:
        return _json_error("Invalid plan.")

    shop_id = session["shop_id"]
    shop = Shop.query.get(shop_id)

    today = datetime.now().date()
    sub = Subscription.query.filter_by(shop_id=shop_id).first()

    if (sub and sub.plan == "Premium" and plan == "Basic"
            and sub.expiry_date and sub.expiry_date >= today):
        return _json_error("Your Premium plan is still active.")

    amount = PLAN_PRICES[plan]
    paise = int(amount * 100)

    try:
        order = rzp.create_order(
            paise,
            receipt=f"s{shop_id}-{int(datetime.utcnow().timestamp())}",
            notes={"shop_id": str(shop_id), "plan": plan}
        )
    except rzp.RazorpayError as e:
        return _json_error(str(e), 502)

    db.session.add(SubscriptionOrder(
        shop_id=shop_id,
        razorpay_order_id=order["id"],
        plan=plan,
        days=PLAN_DAYS,
        amount=amount,
        amount_paise=paise,
        status="CREATED"
    ))
    db.session.commit()

    key_id, _ = rzp.get_keys()

    return jsonify({
        "ok": True,
        "key_id": key_id,
        "order_id": order["id"],
        "amount": paise,
        "currency": "INR",
        "name": "AI Billing",
        "description": f"{plan} plan - {PLAN_DAYS} days",
        "prefill": {
            "name": getattr(shop, "shop_name", "") or "",
            "contact": getattr(shop, "mobile", "") or getattr(shop, "phone", "") or "",
            "email": getattr(shop, "email", "") or ""
        }
    })


@payments_bp.route("/verify", methods=["POST"])
@shop_session_required
def verify():

    if not _csrf_ok():
        return _json_error("Session expired. Refresh the page.", 400)

    data = request.get_json(silent=True) or {}

    order_id = data.get("razorpay_order_id", "")
    payment_id = data.get("razorpay_payment_id", "")
    signature = data.get("razorpay_signature", "")

    _, secret = rzp.get_keys()

    if not rzp.verify_payment_signature(order_id, payment_id, signature, secret):
        return _json_error("Payment could not be verified.", 400)

    order = SubscriptionOrder.query.filter_by(razorpay_order_id=order_id).first()

    if not order or order.shop_id != session["shop_id"]:
        return _json_error("Order not found.", 404)

    fulfill_order(order_id, payment_id)

    return jsonify({"ok": True})


@payments_bp.route("/webhook", methods=["POST"])
def webhook():
    """Razorpay server -> our server. Backup in case the browser closed
    before /verify ran. No login / CSRF; signature is the protection."""

    body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")
    secret = rzp.get_webhook_secret()

    if not rzp.verify_webhook_signature(body, signature, secret):
        return "invalid signature", 400

    try:
        event = json.loads(body.decode("utf-8"))
    except Exception:
        return "ok", 200

    if event.get("event") not in ("payment.captured", "order.paid"):
        return "ok", 200

    payload = event.get("payload", {})
    payment = payload.get("payment", {}).get("entity", {})
    order_id = payment.get("order_id") or payload.get("order", {}).get("entity", {}).get("id")
    payment_id = payment.get("id")

    if not order_id:
        return "ok", 200

    order = SubscriptionOrder.query.filter_by(razorpay_order_id=order_id).first()

    if not order:
        return "ok", 200

    if payment.get("amount") is not None and int(payment["amount"]) != order.amount_paise:
        return "ok", 200

    fulfill_order(order_id, payment_id)

    return "ok", 200
