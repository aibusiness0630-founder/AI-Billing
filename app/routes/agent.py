from flask import Blueprint, render_template, request, session, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func

from app import db
from app.models import Shop, Subscription, SubscriptionPayment
from app.utils.decorators import superadmin_required
from app.utils.agent_engine import answer, CHIPS
from app.routes.superadmin import (
    _shop_state, _wa_link, _ist, _month_keys, _today, _csrf, PLAN_PRICES
)

agent_bp = Blueprint("agent", __name__, url_prefix="/superadmin/agent")


class _PhoneShop:
    """tiny object so superadmin._wa_link(shop, text) can be reused"""
    def __init__(self, phone):
        self.phone = phone


def _load_data():
    today = _today()
    keys = _month_keys(2)
    this_key, last_key = keys[-1], keys[-2]
    start_utc = datetime(last_key[0], last_key[1], 1) - timedelta(hours=5, minutes=30)

    # ---- payments ----
    pay_this = pay_last = pay_today = 0.0
    for p in SubscriptionPayment.query.filter(
        SubscriptionPayment.created_at >= start_utc
    ).all():
        if not p.created_at:
            continue
        d = _ist(p.created_at)
        amt = float(p.amount or 0)
        if (d.year, d.month) == this_key:
            pay_this += amt
        elif (d.year, d.month) == last_key:
            pay_last += amt
        if d.date() == today:
            pay_today += amt

    pay_total = float(
        db.session.query(func.coalesce(func.sum(SubscriptionPayment.amount), 0)).scalar() or 0
    )

    # ---- shops ----
    shops = Shop.query.filter(Shop.approval_status.in_(("APPROVED", "SUSPENDED"))).all()
    subs = {}
    if shops:
        for sub in Subscription.query.filter(
            Subscription.shop_id.in_([s.id for s in shops])
        ).all():
            subs[sub.shop_id] = sub

    shop_rows = []
    for shop in shops:
        sub = subs.get(shop.id)
        state, days_left = _shop_state(shop, sub, today)
        plan = sub.plan if (sub and sub.plan in PLAN_PRICES) else "Basic"
        shop_rows.append({
            "id": shop.id,
            "name": shop.shop_name or "Shop %d" % shop.id,
            "phone": shop.phone,
            "status": shop.approval_status,
            "plan": plan,
            "expiry": sub.expiry_date if sub else None,
            "state": state,
            "days_left": days_left,
        })

    # ---- signups ----
    signups_this = signups_last = 0
    for s in Shop.query.filter(
        Shop.created_at >= start_utc, Shop.approval_status != "REJECTED"
    ).all():
        if s.created_at:
            d = _ist(s.created_at)
            if (d.year, d.month) == this_key:
                signups_this += 1
            elif (d.year, d.month) == last_key:
                signups_last += 1

    # ---- recent payments ----
    names = {s.id: s.shop_name for s in shops}
    recent = []
    for p in SubscriptionPayment.query.order_by(
        SubscriptionPayment.created_at.desc()
    ).limit(8).all():
        nm = names.get(p.shop_id)
        if nm is None:
            sh = Shop.query.get(p.shop_id)
            nm = sh.shop_name if sh else "Shop %s" % p.shop_id
        recent.append({
            "shop": nm,
            "amount": float(p.amount or 0),
            "method": p.method,
            "plan": p.plan,
            "when": _ist(p.created_at).strftime("%d-%m-%Y") if p.created_at else "-",
        })

    return {
        "today": today,
        "pending": Shop.query.filter(Shop.approval_status == "PENDING").count(),
        "shops": shop_rows,
        "pay_this": pay_this,
        "pay_last": pay_last,
        "pay_total": pay_total,
        "pay_today": pay_today,
        "signups_this": signups_this,
        "signups_last": signups_last,
        "recent_payments": recent,
        "prices": PLAN_PRICES,
        "wa": lambda shop, text: _wa_link(_PhoneShop(shop.get("phone")), text),
    }


@agent_bp.route("/")
@superadmin_required
def page():
    pending = Shop.query.filter(Shop.approval_status == "PENDING").count()
    return render_template(
        "superadmin_agent.html",
        active="agent",
        chips=CHIPS,
        csrf=_csrf(),
        pending_count=pending,
        admin_name=session.get("superadmin_name", "admin"),
    )


@agent_bp.route("/ask", methods=["POST"])
@superadmin_required
def ask():
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify({"text": "Bad request", "cards": [], "chips": []}), 400

    token = request.headers.get("X-CSRF-Token", "")
    if not token or token != session.get("sa_csrf"):
        return jsonify({"text": "Session expired. Page refresh pannunga.",
                        "cards": [], "chips": []}), 400

    payload = request.get_json(silent=True) or {}
    question = str(payload.get("q", ""))[:300]

    try:
        result = answer(question, _load_data())
    except Exception as e:
        db.session.rollback()
        print("[agent] error:", e)
        result = {"text": "Oru error vandhuduchu. Marubadi try pannunga.",
                  "cards": [], "chips": []}

    return jsonify(result)