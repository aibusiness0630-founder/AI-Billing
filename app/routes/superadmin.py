from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session,
    flash,
    abort
)

from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import os
import secrets
from urllib.parse import quote

from app import db
from app.models import (
    Shop,
    Subscription,
    SuperAdmin,
    AuditLog,
    Invoice,
    Customer,
    Product,
    SubscriptionPayment
)
from app.utils.decorators import superadmin_required

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/superadmin")

STATUSES = ("PENDING", "APPROVED", "REJECTED")
PLANS = ("Basic", "Premium")
PLAN_PRICES = {"Basic": 499, "Premium": 999}
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PAY_METHODS = ("Cash", "UPI", "Bank Transfer", "Other")
FILTERS = ("all", "active", "expiring", "expired", "suspended")
SA_ATTEMPTS = {}


# ---------------------------------------------------------------
# helpers
# ---------------------------------------------------------------

def _csrf():
    if "sa_csrf" not in session:
        session["sa_csrf"] = os.urandom(32).hex()
    return session["sa_csrf"]


def _csrf_ok():
    token = request.form.get("csrf_token", "")
    return bool(token) and token == session.get("sa_csrf")


def _key(username):
    return f"{username}_{request.remote_addr}"


def _is_blocked(username):
    data = SA_ATTEMPTS.get(_key(username))
    if data and data.get("blocked_until") and datetime.now() < data["blocked_until"]:
        return True
    return False


def _record_fail(username):
    data = SA_ATTEMPTS.setdefault(_key(username), {"attempts": 0, "blocked_until": None})
    data["attempts"] += 1
    if data["attempts"] >= 5:
        data["blocked_until"] = datetime.now() + timedelta(minutes=15)


def _log(shop, action, details):
    db.session.add(AuditLog(
        shop_id=shop.id,
        user_id=None,
        action=action,
        entity_type="SHOP",
        entity_id=shop.id,
        details=details,
        ip_address=request.remote_addr
    ))


def _admin_name():
    return session.get("superadmin_name", "admin")


def _today():
    return datetime.now().date()


def _get_shop_or_404(shop_id):
    shop = Shop.query.filter_by(id=shop_id).first()
    if not shop:
        abort(404)
    return shop


def _get_or_create_sub(shop):
    sub = Subscription.query.filter_by(shop_id=shop.id).first()
    if not sub:
        sub = Subscription(shop_id=shop.id, plan="Basic", status="Active")
        db.session.add(sub)
    return sub


def _read_days(default=30):
    try:
        days = int(request.form.get("days", default))
    except (TypeError, ValueError):
        days = default
    return max(1, min(days, 3650))


def _read_amount():
    try:
        amount = float(request.form.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    return max(0, min(amount, 10000000))


def _record_payment(shop, plan, days):
    """Save the 'amount received' fields of a form, if an amount was typed."""
    amount = _read_amount()
    if amount <= 0:
        return 0

    method = request.form.get("method", "Cash")
    if method not in PAY_METHODS:
        method = "Other"

    db.session.add(SubscriptionPayment(
        shop_id=shop.id,
        amount=amount,
        method=method,
        plan=plan,
        days=days,
        note=request.form.get("note", "").strip()[:255] or None,
        created_by=_admin_name()
    ))
    return amount


def _shop_state(shop, sub, today):
    """returns (state, days_left)"""
    if shop.approval_status == "SUSPENDED":
        return "suspended", None

    days_left = None
    if sub and sub.expiry_date:
        days_left = (sub.expiry_date - today).days
        if days_left < 0:
            return "expired", days_left
        if days_left <= 7:
            return "expiring", days_left

    return "active", days_left


def _not_cancelled():
    return or_(Invoice.payment_status.is_(None), Invoice.payment_status != "CANCELLED")


@superadmin_bp.context_processor
def inject_sidebar():
    try:
        pending = Shop.query.filter(Shop.approval_status == "PENDING").count()
    except Exception:
        pending = 0
    return {"pending_count": pending, "admin_name": _admin_name()}


# ---------------------------------------------------------------
# auth
# ---------------------------------------------------------------

@superadmin_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        if session.get("superadmin_id"):
            return redirect("/superadmin/approvals")
        return render_template("superadmin_login.html", csrf_token=_csrf(), error=None)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not _csrf_ok():
        return render_template(
            "superadmin_login.html",
            csrf_token=_csrf(),
            error="Session expired. Please try again."
        )

    if _is_blocked(username):
        return render_template(
            "superadmin_login.html",
            csrf_token=_csrf(),
            error="Too many attempts. Try again after 15 minutes."
        ), 429

    admin = SuperAdmin.query.filter_by(username=username).first()

    if admin and check_password_hash(admin.password, password):
        SA_ATTEMPTS.pop(_key(username), None)

        admin.last_login = datetime.utcnow()
        db.session.commit()

        session.clear()
        session["superadmin_id"] = admin.id
        session["superadmin_name"] = admin.username
        session["sa_csrf"] = os.urandom(32).hex()

        return redirect("/superadmin/approvals")

    _record_fail(username)

    return render_template(
        "superadmin_login.html",
        csrf_token=_csrf(),
        error="Invalid username or password."
    )


@superadmin_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/superadmin/login")


@superadmin_bp.route("/")
@superadmin_required
def index():
    return redirect("/superadmin/approvals")


# ---------------------------------------------------------------
# approvals
# ---------------------------------------------------------------

@superadmin_bp.route("/approvals")
@superadmin_required
def approvals():

    status = request.args.get("status", "PENDING").upper()
    if status not in STATUSES:
        status = "PENDING"

    counts = {
        s: Shop.query.filter(Shop.approval_status == s).count()
        for s in STATUSES
    }

    shops = (
        Shop.query
        .filter(Shop.approval_status == status)
        .order_by(Shop.created_at.desc())
        .all()
    )

    subs = {}
    if shops:
        for sub in Subscription.query.filter(
            Subscription.shop_id.in_([s.id for s in shops])
        ).all():
            subs[sub.shop_id] = sub

    return render_template(
        "superadmin_approvals.html",
        active="approvals",
        shops=shops,
        subs=subs,
        status=status,
        counts=counts,
        csrf_token=_csrf()
    )


@superadmin_bp.route("/approve/<int:shop_id>", methods=["POST"])
@superadmin_required
def approve(shop_id):

    if not _csrf_ok():
        abort(400)

    shop = _get_shop_or_404(shop_id)

    plan = request.form.get("plan", "Basic")
    if plan not in PLANS:
        plan = "Basic"

    days = _read_days(30)
    today = _today()

    sub = _get_or_create_sub(shop)
    sub.plan = plan
    sub.start_date = today
    sub.expiry_date = today + timedelta(days=days)
    sub.status = "Active"
    sub.reminder_sent = False

    shop.approval_status = "APPROVED"
    shop.approved_at = datetime.utcnow()
    shop.rejection_reason = None

    paid = _record_payment(shop, plan, days)

    _log(shop, "APPROVE_SHOP",
         f"Approved by {_admin_name()}: plan={plan}, days={days}, paid={paid}")

    db.session.commit()

    flash(f"✅ {shop.shop_name} approved ({plan}, {days} days).", "ok")
    return redirect("/superadmin/approvals?status=PENDING")


@superadmin_bp.route("/reject/<int:shop_id>", methods=["POST"])
@superadmin_required
def reject(shop_id):

    if not _csrf_ok():
        abort(400)

    shop = _get_shop_or_404(shop_id)

    reason = request.form.get("reason", "").strip()[:255]

    shop.approval_status = "REJECTED"
    shop.approved_at = None
    shop.rejection_reason = reason or None

    _log(shop, "REJECT_SHOP",
         f"Rejected by {_admin_name()}: {reason or 'no reason given'}")

    db.session.commit()

    flash(f"❌ {shop.shop_name} rejected.", "bad")
    return redirect("/superadmin/approvals?status=PENDING")


# ---------------------------------------------------------------
# customers (approved + suspended shops)
# ---------------------------------------------------------------

@superadmin_bp.route("/customers")
@superadmin_required
def customers():

    q = request.args.get("q", "").strip()
    flt = request.args.get("filter", "all").lower()
    if flt not in FILTERS:
        flt = "all"

    today = _today()

    shops = (
        Shop.query
        .filter(Shop.approval_status.in_(("APPROVED", "SUSPENDED")))
        .order_by(Shop.created_at.desc())
        .all()
    )

    ids = [s.id for s in shops]
    subs = {}
    usage = {}

    if ids:
        for sub in Subscription.query.filter(Subscription.shop_id.in_(ids)).all():
            subs[sub.shop_id] = sub

        for shop_id, cnt, total in (
            db.session.query(
                Invoice.shop_id,
                func.count(Invoice.id),
                func.coalesce(func.sum(Invoice.total_amount), 0)
            )
            .filter(Invoice.shop_id.in_(ids), _not_cancelled())
            .group_by(Invoice.shop_id)
            .all()
        ):
            usage[shop_id] = (cnt, float(total or 0))

    rows = []
    counts = {"all": 0, "active": 0, "expiring": 0, "expired": 0, "suspended": 0}

    for shop in shops:
        sub = subs.get(shop.id)
        state, days_left = _shop_state(shop, sub, today)
        bills, billed = usage.get(shop.id, (0, 0.0))

        counts["all"] += 1
        counts[state] += 1
        if state == "expiring":
            counts["active"] += 1   # still running, only close to expiry

        rows.append({
            "shop": shop,
            "sub": sub,
            "state": state,
            "days_left": days_left,
            "bills": bills,
            "billed": billed
        })

    if flt == "active":
        rows = [r for r in rows if r["state"] in ("active", "expiring")]
    elif flt != "all":
        rows = [r for r in rows if r["state"] == flt]

    if q:
        needle = q.lower()
        rows = [
            r for r in rows
            if needle in (r["shop"].shop_name or "").lower()
            or needle in (r["shop"].username or "").lower()
            or needle in (r["shop"].phone or "").lower()
        ]

    return render_template(
        "superadmin_customers.html",
        active="customers",
        rows=rows,
        counts=counts,
        flt=flt,
        q=q
    )


@superadmin_bp.route("/customers/<int:shop_id>")
@superadmin_required
def customer_detail(shop_id):

    shop = _get_shop_or_404(shop_id)
    today = _today()

    sub = Subscription.query.filter_by(shop_id=shop.id).first()
    state, days_left = _shop_state(shop, sub, today)

    invoice_count, billed = (
        db.session.query(
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total_amount), 0)
        )
        .filter(Invoice.shop_id == shop.id, _not_cancelled())
        .first()
    )

    last_invoice = (
        Invoice.query
        .filter_by(shop_id=shop.id)
        .order_by(Invoice.created_at.desc())
        .first()
    )

    since = datetime.utcnow() - timedelta(days=30)
    bills_30 = Invoice.query.filter(
        Invoice.shop_id == shop.id,
        Invoice.created_at >= since
    ).count()

    stats = {
        "bills": invoice_count or 0,
        "billed": float(billed or 0),
        "bills_30": bills_30,
        "customers": Customer.query.filter_by(shop_id=shop.id).count(),
        "products": Product.query.filter_by(shop_id=shop.id).count(),
        "last_invoice": last_invoice.created_at if last_invoice else None
    }

    payments = (
        SubscriptionPayment.query
        .filter_by(shop_id=shop.id)
        .order_by(SubscriptionPayment.created_at.desc())
        .limit(20)
        .all()
    )
    paid_total = float(
        db.session.query(func.coalesce(func.sum(SubscriptionPayment.amount), 0))
        .filter(SubscriptionPayment.shop_id == shop.id)
        .scalar() or 0
    )

    logs = (
        AuditLog.query
        .filter_by(shop_id=shop.id)
        .order_by(AuditLog.created_at.desc())
        .limit(15)
        .all()
    )

    return render_template(
        "superadmin_customer.html",
        active="customers",
        shop=shop,
        sub=sub,
        state=state,
        days_left=days_left,
        stats=stats,
        payments=payments,
        paid_total=paid_total,
        logs=logs,
        csrf_token=_csrf()
    )


def _back(shop_id):
    return redirect(f"/superadmin/customers/{shop_id}")


@superadmin_bp.route("/customers/<int:shop_id>/plan", methods=["POST"])
@superadmin_required
def change_plan(shop_id):

    if not _csrf_ok():
        abort(400)

    shop = _get_shop_or_404(shop_id)

    plan = request.form.get("plan", "")
    if plan not in PLANS:
        flash("❌ Invalid plan.", "bad")
        return _back(shop.id)

    sub = _get_or_create_sub(shop)
    old_plan = sub.plan
    sub.plan = plan

    _log(shop, "CHANGE_PLAN",
         f"{old_plan} -> {plan} by {_admin_name()}")

    db.session.commit()

    flash(f"✅ Plan changed: {old_plan} → {plan}.", "ok")
    return _back(shop.id)


@superadmin_bp.route("/customers/<int:shop_id>/extend", methods=["POST"])
@superadmin_required
def extend(shop_id):

    if not _csrf_ok():
        abort(400)

    shop = _get_shop_or_404(shop_id)

    days = _read_days(30)
    today = _today()

    sub = _get_or_create_sub(shop)

    # extend from the current expiry if still running, else from today
    base = sub.expiry_date if sub.expiry_date and sub.expiry_date >= today else today

    if not sub.start_date:
        sub.start_date = today

    sub.expiry_date = base + timedelta(days=days)
    sub.status = "Active"
    sub.reminder_sent = False

    paid = _record_payment(shop, sub.plan, days)

    _log(shop, "EXTEND_SUBSCRIPTION",
         f"+{days} days (new expiry {sub.expiry_date}), paid={paid}, by {_admin_name()}")

    db.session.commit()

    flash(f"✅ Extended by {days} days. New expiry: {sub.expiry_date.strftime('%d-%m-%Y')}.", "ok")
    return _back(shop.id)


@superadmin_bp.route("/customers/<int:shop_id>/suspend", methods=["POST"])
@superadmin_required
def suspend(shop_id):

    if not _csrf_ok():
        abort(400)

    shop = _get_shop_or_404(shop_id)

    reason = request.form.get("reason", "").strip()[:255]

    shop.approval_status = "SUSPENDED"
    shop.rejection_reason = reason or None

    _log(shop, "SUSPEND_SHOP",
         f"Suspended by {_admin_name()}: {reason or 'no reason given'}")

    db.session.commit()

    flash(f"⛔ {shop.shop_name} suspended. Login block aagiduchu.", "bad")
    return _back(shop.id)


@superadmin_bp.route("/customers/<int:shop_id>/activate", methods=["POST"])
@superadmin_required
def activate(shop_id):

    if not _csrf_ok():
        abort(400)

    shop = _get_shop_or_404(shop_id)

    shop.approval_status = "APPROVED"
    shop.rejection_reason = None

    _log(shop, "ACTIVATE_SHOP", f"Activated by {_admin_name()}")

    db.session.commit()

    flash(f"✅ {shop.shop_name} activated.", "ok")
    return _back(shop.id)


@superadmin_bp.route("/customers/<int:shop_id>/reset_password", methods=["POST"])
@superadmin_required
def reset_password(shop_id):

    if not _csrf_ok():
        abort(400)

    shop = _get_shop_or_404(shop_id)

    temp_password = "Anfia@" + secrets.token_hex(4)
    shop.password = generate_password_hash(temp_password)

    _log(shop, "RESET_PASSWORD", f"Password reset by {_admin_name()}")

    db.session.commit()

    flash(
        f"🔑 Temporary password for '{shop.username}': {temp_password}  "
        f"(idhu oru thadavai mattum theriyum, owner-ku anuppunga)",
        "ok"
    )
    return _back(shop.id)


# ---------------------------------------------------------------
# revenue
# ---------------------------------------------------------------

def _ist(dt):
    return dt + timedelta(hours=5, minutes=30)


def _month_keys(n=6):
    now = _ist(datetime.utcnow())
    year, month = now.year, now.month
    keys = []
    for _ in range(n):
        keys.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(keys))


def _bars(keys, bucket):
    values = [bucket.get(k, 0) for k in keys]
    top = max(values) or 1
    return [
        {
            "label": f"{MONTH_NAMES[m - 1]} {str(y)[2:]}",
            "value": v,
            "pct": max(round(v / top * 100), 4) if v > 0 else 0
        }
        for (y, m), v in zip(keys, values)
    ]


def _wa_link(shop, text):
    digits = "".join(c for c in (shop.phone or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) < 10:
        return None
    return f"https://wa.me/{digits}?text={quote(text)}"


@superadmin_bp.route("/revenue")
@superadmin_required
def revenue():

    today = _today()
    keys = _month_keys(6)
    this_key, last_key = keys[-1], keys[-2]

    start_utc = datetime(keys[0][0], keys[0][1], 1) - timedelta(hours=5, minutes=30)

    # ---- money received + signups, bucketed per month (IST) ----
    pay_bucket = {}
    for p in SubscriptionPayment.query.filter(
        SubscriptionPayment.created_at >= start_utc
    ).all():
        if p.created_at:
            d = _ist(p.created_at)
            pay_bucket[(d.year, d.month)] = pay_bucket.get((d.year, d.month), 0) + (p.amount or 0)

    signup_bucket = {}
    for s in Shop.query.filter(
        Shop.created_at >= start_utc,
        Shop.approval_status != "REJECTED"
    ).all():
        if s.created_at:
            d = _ist(s.created_at)
            signup_bucket[(d.year, d.month)] = signup_bucket.get((d.year, d.month), 0) + 1

    received_this = pay_bucket.get(this_key, 0)
    received_last = pay_bucket.get(last_key, 0)
    delta = None
    if received_last > 0:
        delta = round((received_this - received_last) / received_last * 100)

    total_received = float(
        db.session.query(func.coalesce(func.sum(SubscriptionPayment.amount), 0)).scalar() or 0
    )

    # ---- subscriptions: MRR, plan split, renewals ----
    shops = Shop.query.filter(Shop.approval_status.in_(("APPROVED", "SUSPENDED"))).all()
    subs = {}
    if shops:
        for sub in Subscription.query.filter(
            Subscription.shop_id.in_([s.id for s in shops])
        ).all():
            subs[sub.shop_id] = sub

    mrr = 0
    active_shops = 0
    plan_count = {"Basic": 0, "Premium": 0}
    renewals = []
    lapsed = []

    for shop in shops:
        sub = subs.get(shop.id)
        state, days_left = _shop_state(shop, sub, today)

        if state in ("active", "expiring"):
            active_shops += 1
            if sub:
                plan = sub.plan if sub.plan in PLAN_PRICES else "Basic"
                plan_count[plan] += 1
                mrr += PLAN_PRICES[plan]

        if sub and days_left is not None:
            plan = sub.plan if sub.plan in PLAN_PRICES else "Basic"
            exp = sub.expiry_date.strftime("%d-%m-%Y")

            if state in ("active", "expiring") and days_left <= 30:
                text = (f"Vanakkam! Unga {shop.shop_name} AI Billing {plan} plan "
                        f"{exp} anru expire aagum. Renew panna ippove reply pannunga. "
                        f"- ANFIA Technology")
                renewals.append({
                    "shop": shop, "plan": plan, "days_left": days_left,
                    "expiry": exp, "price": PLAN_PRICES[plan],
                    "wa": _wa_link(shop, text)
                })

            elif state == "expired" and days_left >= -30:
                text = (f"Vanakkam! Unga {shop.shop_name} AI Billing {plan} plan "
                        f"{exp} anru expire aagiduchu. Marubadiyum use panna reply "
                        f"pannunga. - ANFIA Technology")
                lapsed.append({
                    "shop": shop, "plan": plan, "days_left": days_left,
                    "expiry": exp, "price": PLAN_PRICES[plan],
                    "wa": _wa_link(shop, text)
                })

    renewals.sort(key=lambda r: r["days_left"])
    lapsed.sort(key=lambda r: -r["days_left"])

    renewals_value = sum(r["price"] for r in renewals)

    # ---- recent payments ----
    recent = (
        SubscriptionPayment.query
        .order_by(SubscriptionPayment.created_at.desc())
        .limit(10)
        .all()
    )
    pay_shops = {}
    if recent:
        for s in Shop.query.filter(Shop.id.in_([p.shop_id for p in recent])).all():
            pay_shops[s.id] = s

    # ---- top shops by billing volume ----
    top_rows = (
        db.session.query(
            Invoice.shop_id,
            func.coalesce(func.sum(Invoice.total_amount), 0),
            func.count(Invoice.id)
        )
        .filter(_not_cancelled())
        .group_by(Invoice.shop_id)
        .order_by(func.sum(Invoice.total_amount).desc())
        .limit(5)
        .all()
    )
    top_shops = []
    if top_rows:
        names = {
            s.id: s for s in
            Shop.query.filter(Shop.id.in_([r[0] for r in top_rows])).all()
        }
        for shop_id, total, cnt in top_rows:
            if shop_id in names:
                top_shops.append({"shop": names[shop_id], "billed": float(total or 0), "bills": cnt})

    pending_total = Shop.query.filter(Shop.approval_status == "PENDING").count()

    products = [
        {"name": "AI Billing", "live": True, "active": active_shops,
         "mrr": mrr, "received": total_received},
        {"name": "HELIOGRID", "live": False},
    ]

    return render_template(
        "superadmin_revenue.html",
        active="revenue",
        received_this=received_this,
        received_last=received_last,
        delta=delta,
        total_received=total_received,
        mrr=mrr,
        active_shops=active_shops,
        signups_this=signup_bucket.get(this_key, 0),
        pending_total=pending_total,
        pay_bars=_bars(keys, pay_bucket),
        signup_bars=_bars(keys, signup_bucket),
        plan_count=plan_count,
        plan_prices=PLAN_PRICES,
        renewals=renewals,
        renewals_value=renewals_value,
        lapsed=lapsed,
        recent=recent,
        pay_shops=pay_shops,
        top_shops=top_shops,
        products=products
    )
