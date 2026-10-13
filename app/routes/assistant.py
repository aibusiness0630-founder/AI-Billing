import re
import math
import difflib
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, session
from sqlalchemy import func, or_

from app import db
from app.models import Product, Invoice, InvoiceItem, Customer, Supplier
from app.utils.decorators import login_required, premium_required

assistant_bp = Blueprint("assistant", __name__)

IST = timedelta(hours=5, minutes=30)


# =========================================================
# HELPERS
# =========================================================

def money(v):
    return "₹{:,.0f}".format(v or 0)


def day_start_utc(days_ago=0):
    """Start of an IST day, expressed in UTC (DB stores utcnow)."""
    now_ist = datetime.utcnow() + IST
    start_ist = datetime(now_ist.year, now_ist.month, now_ist.day) - timedelta(days=days_ago)
    return start_ist - IST


def valid_invoice():
    return or_(Invoice.payment_status.is_(None), Invoice.payment_status != "CANCELLED")


def active_products(shop_id):
    return Product.query.filter(
        Product.shop_id == shop_id,
        or_(Product.is_active.is_(None), Product.is_active == True)  # noqa: E712
    ).all()


def sales_between(shop_id, start, end):
    total, bills = db.session.query(
        func.coalesce(func.sum(Invoice.total_amount), 0),
        func.count(Invoice.id)
    ).filter(
        Invoice.shop_id == shop_id,
        Invoice.created_at >= start,
        Invoice.created_at < end,
        valid_invoice()
    ).one()
    return float(total or 0), int(bills or 0)


def sold_products(shop_id, start, end):
    rows = db.session.query(
        Product.id,
        Product.name,
        func.sum(InvoiceItem.quantity),
        func.sum(InvoiceItem.total),
        func.sum(InvoiceItem.quantity * func.coalesce(Product.price_cost, 0))
    ).join(
        InvoiceItem, InvoiceItem.product_id == Product.id
    ).join(
        Invoice, Invoice.id == InvoiceItem.invoice_id
    ).filter(
        Invoice.shop_id == shop_id,
        Product.shop_id == shop_id,
        Invoice.created_at >= start,
        Invoice.created_at < end,
        valid_invoice()
    ).group_by(Product.id, Product.name).all()

    return [{
        "id": r[0],
        "name": r[1],
        "qty": int(r[2] or 0),
        "revenue": float(r[3] or 0),
        "cost": float(r[4] or 0)
    } for r in rows]


def top_customers(shop_id, start, end, limit=3):
    rows = db.session.query(
        Customer.name,
        func.sum(Invoice.total_amount)
    ).join(
        Invoice, Invoice.customer_id == Customer.id
    ).filter(
        Invoice.shop_id == shop_id,
        Customer.shop_id == shop_id,
        Invoice.created_at >= start,
        Invoice.created_at < end,
        valid_invoice(),
        ~Customer.name.ilike("walk%")
    ).group_by(Customer.id, Customer.name).order_by(
        func.sum(Invoice.total_amount).desc()
    ).limit(limit).all()
    return [(r[0], float(r[1] or 0)) for r in rows]


def pending_invoices(shop_id):
    count, total = db.session.query(
        func.count(Invoice.id),
        func.coalesce(func.sum(Invoice.total_amount), 0)
    ).filter(
        Invoice.shop_id == shop_id,
        Invoice.payment_status.in_(["PENDING", "PARTIAL"])
    ).one()
    return int(count or 0), float(total or 0)


def supplier_dues(shop_id):
    return Supplier.query.filter(
        Supplier.shop_id == shop_id,
        Supplier.outstanding_amount > 0
    ).order_by(Supplier.outstanding_amount.desc()).all()


# =========================================================
# SMART INSIGHTS
# =========================================================

LEVEL_ORDER = {"danger": 0, "warning": 1, "info": 2, "success": 3}


def build_insights(shop_id):

    out = []

    def add(level, icon, title, detail, url=None, link_text=None):
        out.append({
            "level": level, "icon": icon, "title": title,
            "detail": detail, "url": url, "link_text": link_text
        })

    products = active_products(shop_id)

    today_start = day_start_utc(0)
    tomorrow = today_start + timedelta(days=1)
    yesterday_start = day_start_utc(1)

    # ---- Today vs yesterday (same time of day, so it is fair) ----
    t_total, t_bills = sales_between(shop_id, today_start, tomorrow)
    elapsed = datetime.utcnow() - today_start
    y_total, _ = sales_between(shop_id, yesterday_start, yesterday_start + elapsed)

    if t_total == 0 and y_total == 0:
        add("info", "🧾", "Innaiku innum bill illa",
            "Bill generate pannina insights update aagum.", "/", "New Bill")
    elif y_total > 0:
        pct = (t_total - y_total) / y_total * 100
        if pct <= -15:
            add("warning", "📉", f"Innaiku sales {abs(pct):.0f}% kuraivu",
                f"Ippa varai {money(t_total)}. Neththu idhe neram {money(y_total)} irundhuchu.")
        elif pct >= 15:
            add("success", "📈", f"Innaiku sales {pct:.0f}% adhigam",
                f"Ippa varai {money(t_total)}. Neththu idhe neram {money(y_total)}.")
        else:
            add("info", "🧾", f"Innaiku ippa varai {money(t_total)}",
                f"{t_bills} bills. Neththu idhe neram {money(y_total)}, kiTTa kiTTa same.")
    else:
        add("success", "📈", f"Innaiku {money(t_total)} sales",
            f"{t_bills} bills. Neththu idhe neram sales illa.")

    # ---- Weekly trend ----
    w1, _ = sales_between(shop_id, day_start_utc(6), tomorrow)
    w0, _ = sales_between(shop_id, day_start_utc(13), day_start_utc(6))
    if w0 > 0:
        pct = (w1 - w0) / w0 * 100
        if pct <= -15:
            add("warning", "📉", f"Intha vaaram sales {abs(pct):.0f}% kuraivu",
                f"Last 7 days {money(w1)}, mun 7 days {money(w0)}.", "/reports?period=weekly", "Report paarunga")
        elif pct >= 15:
            add("success", "📈", f"Intha vaaram sales {pct:.0f}% adhigam",
                f"Last 7 days {money(w1)}, mun 7 days {money(w0)}.", "/reports?period=weekly", "Report paarunga")

    # ---- Stock: out / low ----
    out_of_stock = [p for p in products if (p.stock or 0) <= 0]
    low_stock = [
        p for p in products
        if 0 < (p.stock or 0) <= (p.min_stock if p.min_stock is not None else 10)
    ]

    if out_of_stock:
        names = ", ".join(p.name for p in out_of_stock[:5])
        extra = f" (+{len(out_of_stock) - 5} more)" if len(out_of_stock) > 5 else ""
        add("danger", "⛔", f"{len(out_of_stock)} product stock-la illa",
            f"{names}{extra}. Sales miss aagum, udane purchase pannunga.", "/add_purchase", "Purchase order")

    # ---- Days-of-stock-left prediction (last 14 days sales rate) ----
    sold14 = sold_products(shop_id, day_start_utc(13), tomorrow)
    rate = {r["id"]: r["qty"] / 14.0 for r in sold14}

    reorders = []
    for p in products:
        stock = p.stock or 0
        r = rate.get(p.id, 0)
        if stock > 0 and r > 0:
            days_left = stock / r
            if days_left <= 7:
                reorders.append((days_left, p, r))
    reorders.sort(key=lambda x: x[0])

    reorder_ids = set()
    for days_left, p, r in reorders[:4]:
        reorder_ids.add(p.id)
        need = max(1, int(math.ceil(r * 14 - (p.stock or 0))))
        days = max(1, int(math.ceil(days_left)))
        add("warning", "⏳", f"{p.name} stock {days} naal-la mudiyum",
            f"Ippo {p.stock} irukku, thinamum approx {r:.1f} vikkudhu. 2 vaaram-ku {need} order pannunga.",
            "/add_purchase", "Purchase order")

    remaining_low = [p for p in low_stock if p.id not in reorder_ids]
    if remaining_low:
        names = ", ".join(f"{p.name} ({p.stock})" for p in remaining_low[:5])
        add("warning", "📦", f"{len(remaining_low)} product stock kammi",
            names, "/products", "Products paarunga")

    # ---- Margin check ----
    loss, thin = [], []
    for p in products:
        cost = p.price_cost or 0
        sell = p.price_sell or 0
        if cost > 0 and sell > 0:
            m = (sell - cost) / sell * 100
            if sell < cost:
                loss.append(p)
            elif m < 10:
                thin.append((m, p))

    if loss:
        add("danger", "💸", f"{len(loss)} product nashtathula vikkudhu",
            ", ".join(p.name for p in loss[:4]) + ". Selling price < cost price, price maathunga.",
            "/products", "Price maathunga")

    thin.sort(key=lambda x: x[0])
    for m, p in thin[:3]:
        add("warning", "🏷", f"{p.name} margin {m:.0f}% mattum",
            f"Cost {money(p.price_cost)}, selling {money(p.price_sell)}. Price check pannunga.",
            "/products", "Price check")

    no_cost = [p for p in products if not p.price_cost]
    if no_cost:
        add("info", "ℹ️", f"{len(no_cost)} product-ku cost price illa",
            "Cost price illana profit report correct-a varaadhu. Purchase pannina auto-update aagum.")

    # ---- Supplier dues ----
    dues = supplier_dues(shop_id)
    if dues:
        total_due = sum(s.outstanding_amount or 0 for s in dues)
        for s in dues[:3]:
            add("warning", "🏭", f"{s.name}-ku {money(s.outstanding_amount)} balance pending",
                "Supplier payment kodukkanum.", "/purchases", "Purchases paarunga")
        if len(dues) > 3:
            add("info", "🏭", f"Total supplier dues {money(total_due)}",
                f"{len(dues)} suppliers-ku balance irukku.", "/suppliers", "Suppliers")

    # ---- Customer pending bills ----
    p_count, p_total = pending_invoices(shop_id)
    if p_count:
        add("warning", "🧾", f"{p_count} customer bills pending ({money(p_total)})",
            "Payment vaangalai.", "/history", "History paarunga")

    # ---- Best product & top customer (last 7 / 30 days) ----
    sold7 = sold_products(shop_id, day_start_utc(6), tomorrow)
    if sold7:
        best = max(sold7, key=lambda r: r["qty"])
        add("success", "🏆", f"Intha vaaram top product: {best['name']}",
            f"{best['qty']} sold, {money(best['revenue'])} revenue. Stock kammiya vidaadheenga.")

    tc = top_customers(shop_id, day_start_utc(29), tomorrow, 1)
    if tc:
        add("success", "👑", f"Top customer: {tc[0][0]}",
            f"Last 30 days {money(tc[0][1])} vaangi irukkanga. Oru thanks message anuppalaam.")

    # ---- Dead stock (stock irukku, 30 days sales illa) ----
    sold30 = sold_products(shop_id, day_start_utc(29), tomorrow)
    if sold30:
        sold_ids = {r["id"] for r in sold30}
        dead = [p for p in products if (p.stock or 0) > 0 and p.id not in sold_ids]
        if dead:
            dead.sort(key=lambda p: (p.stock or 0) * (p.price_cost or p.price_sell or 0), reverse=True)
            value = sum((p.stock or 0) * (p.price_cost or p.price_sell or 0) for p in dead)
            add("info", "🐌", f"{len(dead)} product 30 naala vikkala",
                ", ".join(p.name for p in dead[:3]) + f". Approx {money(value)} stock-la mudangi irukku. Discount offer podalaam.")

    out.sort(key=lambda i: LEVEL_ORDER.get(i["level"], 9))

    if not out:
        add("success", "✅", "Ellam nalla irukku", "Ippo edhuvum urgent illa.")

    return out[:12]


# =========================================================
# QUESTION ANSWERING (rule based, Tanglish + English + Tamil)
# =========================================================

P_TODAY = ("today", "innaiku", "inniku", "innaikku", "indru", "இன்று", "இன்னைக்கு")
P_YEST = ("yesterday", "neththu", "nethu", "நேற்று", "நேத்து")
P_WEEK = ("week", "vaaram", "vaarathu", "7 days", "seven days", "வாரம்")
P_MONTH = ("month", "maatham", "matham", "30 days", "மாதம்")

SALES_W = ("sales", "sale", "vitpanai", "விற்பனை", "vyabaram", "business", "collection",
           "revenue", "vikkudhu", "vikka", "sold")
PRICE_W = ("price", "vilai", "rate", "விலை")
TOP_W = ("top", "best", "most", "adhigam", "popular", "fast", "முதல்")
PROFIT_W = ("profit", "laabam", "லாபம்", "earning")
SUGGEST_W = ("suggest", "advice", "idea", "insight", "aalosanai", "ஆலோசனை",
             "enna seyyalam", "what should", "enna pannalam")
HELP_W = ("help", "udhavi", "உதவி", "what can you do", "enna theriyum")
GREET_W = ("hi", "hello", "hey", "vanakkam", "வணக்கம்")

EXAMPLES = [
    "Innaiku sales evlo?",
    "Low stock enna?",
    "Top selling product yaaru?",
    "Top customer yaaru?",
    "Profit evlo?",
    "Pending supplier balance?",
    "Suggestion sollu",
]


def has(text, words):
    return any(w in text for w in words)


def detect_period(text):
    today_start = day_start_utc(0)
    tomorrow = today_start + timedelta(days=1)

    if has(text, P_YEST):
        return "Neththu", day_start_utc(1), today_start
    if has(text, P_WEEK):
        return "Last 7 days", day_start_utc(6), tomorrow
    if has(text, P_MONTH):
        return "Last 30 days", day_start_utc(29), tomorrow
    return "Innaiku", today_start, tomorrow


def match_product(text, products):
    best = None
    for p in products:
        name = (p.name or "").lower().strip()
        if name and name in text:
            if best is None or len(name) > len((best.name or "")):
                best = p
    return best


def reply(text):
    return {"reply": text, "speak": speakable(text)}


def speakable(text):
    text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]", "", text)
    return text.replace("₹", "rupees ")


def answer_question(shop_id, raw):

    t = (raw or "").lower().strip()

    if not t:
        return reply("Edhavadhu kelunga. Udhaa: 'Innaiku sales evlo?'")

    products = active_products(shop_id)

    # ---- specific product ----
    p = match_product(t, products)
    if p:
        if has(t, SALES_W):
            label, start, end = detect_period(t)
            rows = [r for r in sold_products(shop_id, start, end) if r["id"] == p.id]
            if rows:
                r = rows[0]
                return reply(f"{label} {p.name}: {r['qty']} sold, {money(r['revenue'])} revenue.")
            return reply(f"{label} {p.name} edhuvum vikkala.")
        if has(t, PRICE_W):
            return reply(f"{p.name} selling price {money(p.price_sell)}"
                         + (f", cost price {money(p.price_cost)}." if p.price_cost else "."))
        stock = p.stock or 0
        min_stock = p.min_stock if p.min_stock is not None else 10
        note = " Stock kammi, order pannunga." if stock <= min_stock else ""
        return reply(f"{p.name} stock: {stock}.{note}")

    # ---- greeting / help ----
    if t in GREET_W or (has(t, GREET_W) and len(t.split()) <= 2):
        return reply("Vanakkam! Naan ungal business assistant. Sales, stock, profit, supplier balance, top customer ellam kelunga.")

    if has(t, HELP_W):
        return reply("Ippadi kelunga: " + " | ".join(EXAMPLES))

    # ---- suggestions ----
    if has(t, SUGGEST_W):
        items = build_insights(shop_id)[:4]
        return reply("Munnukku mukkiyam: " + " ".join(f"{i+1}. {x['title']}." for i, x in enumerate(items)))

    # ---- profit ----
    if has(t, PROFIT_W):
        label, start, end = detect_period(t)
        rows = sold_products(shop_id, start, end)
        rev = sum(r["revenue"] for r in rows)
        cost = sum(r["cost"] for r in rows)
        note = "" if cost > 0 else " (Cost price illa, adhunaala profit correct-a illa.)"
        return reply(f"{label} estimated profit {money(rev - cost)} (sales {money(rev)}, cost {money(cost)}).{note}")

    # ---- customers ----
    if has(t, ("customer", "வாடிக்கையாளர்")):
        if has(t, ("how many", "evlo", "count", "ethana")) and not has(t, TOP_W + ("yaaru", "who")):
            n = Customer.query.filter_by(shop_id=shop_id).count()
            return reply(f"Total {n} customers irukkanga.")
        label, start, end = detect_period(t)
        if not has(t, P_TODAY + P_YEST + P_WEEK):
            label, start, end = "Last 30 days", day_start_utc(29), day_start_utc(0) + timedelta(days=1)
        tc = top_customers(shop_id, start, end, 3)
        if not tc:
            return reply(f"{label} customer bills illa.")
        parts = ", ".join(f"{n} ({money(a)})" for n, a in tc)
        return reply(f"{label} top customers: {parts}.")

    # ---- low stock ----
    if has(t, ("stock", "ஸ்டாக்", "reorder")) and has(t, ("low", "kammi", "kuraiv", "illa", "out", "enna", "reorder", "mudiy", "kami")):
        out_of = [x for x in products if (x.stock or 0) <= 0]
        low = [x for x in products if 0 < (x.stock or 0) <= (x.min_stock if x.min_stock is not None else 10)]
        if not out_of and not low:
            return reply("Ellam stock-la irukku 👍")
        parts = []
        if out_of:
            parts.append("Stock illa: " + ", ".join(x.name for x in out_of[:6]) + ".")
        if low:
            parts.append("Kammi: " + ", ".join(f"{x.name} ({x.stock})" for x in low[:6]) + ".")
        return reply(" ".join(parts))

    # ---- slow moving ----
    if has(t, ("slow", "dead", "vikkala", "not selling", "vikkaadha")):
        tomorrow = day_start_utc(0) + timedelta(days=1)
        sold_ids = {r["id"] for r in sold_products(shop_id, day_start_utc(29), tomorrow)}
        dead = [x for x in products if (x.stock or 0) > 0 and x.id not in sold_ids]
        if not dead:
            return reply("30 naala vikkaadha product edhuvum illa 👍")
        return reply("30 naala vikkala: " + ", ".join(x.name for x in dead[:6]) + ".")

    # ---- top product ----
    if has(t, TOP_W) or "selling" in t:
        label, start, end = detect_period(t)
        if not has(t, P_TODAY + P_YEST + P_WEEK + P_MONTH):
            label, start, end = "Last 7 days", day_start_utc(6), day_start_utc(0) + timedelta(days=1)
        rows = sorted(sold_products(shop_id, start, end), key=lambda r: r["qty"], reverse=True)[:3]
        if not rows:
            return reply(f"{label} sales data illa.")
        return reply(f"{label} top products: " + ", ".join(f"{r['name']} ({r['qty']})" for r in rows) + ".")

    # ---- supplier / pending ----
    if has(t, ("supplier", "pending", "balance", "baaki", "dues", "kodukkanum", "கடன்")):
        dues = supplier_dues(shop_id)
        c_count, c_total = pending_invoices(shop_id)
        parts = []
        if dues:
            total = sum(s.outstanding_amount or 0 for s in dues)
            parts.append(f"Supplier balance total {money(total)}: " +
                         ", ".join(f"{s.name} ({money(s.outstanding_amount)})" for s in dues[:4]) + ".")
        else:
            parts.append("Supplier balance edhuvum illa.")
        if c_count:
            parts.append(f"Customer pending bills {c_count} ({money(c_total)}).")
        return reply(" ".join(parts))

    # ---- bills count ----
    if has(t, ("bill", "invoice")) and has(t, ("evlo", "how many", "count", "ethana")):
        label, start, end = detect_period(t)
        total, bills = sales_between(shop_id, start, end)
        return reply(f"{label} {bills} bills, total {money(total)}.")

    # ---- sales (default) ----
    if has(t, SALES_W) or has(t, ("evlo", "how much")):
        label, start, end = detect_period(t)
        total, bills = sales_between(shop_id, start, end)
        avg = total / bills if bills else 0
        return reply(f"{label} sales {money(total)}, {bills} bills, average bill {money(avg)}.")

    return reply("Puriyala 🙏 Ippadi kelunga: " + " | ".join(EXAMPLES[:4]))


# =========================================================
# VOICE BILLING PARSER
# =========================================================

NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
    "oru": 1, "onnu": 1, "ondru": 1, "rendu": 2, "irandu": 2, "moonu": 3, "munu": 3,
    "mooru": 3, "naalu": 4, "nalu": 4, "anju": 5, "aaru": 6, "ezhu": 7, "yezhu": 7,
    "ettu": 8, "onbadhu": 9, "pathu": 10, "patthu": 10,
    "ஒன்று": 1, "ஒரு": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5,
    "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10,
}

UNIT_WORDS = {
    "kg", "kgs", "kilo", "kilos", "gram", "grams", "g", "litre", "liter", "litres",
    "l", "packet", "packets", "pack", "piece", "pieces", "pcs", "nos", "unit",
    "units", "bottle", "bottles", "box", "boxes"
}

NOISE_WORDS = {
    "bill", "billing", "pannu", "panni", "podu", "podunga", "add", "venum", "kudu",
    "kudunga", "create", "generate", "new", "and", "mattrum", "aprm", "apram", "then",
    "with", "for", "please", "customer", "mobile", "number", "name", "is", "the", "a",
    "an", "to", "ku", "la", "ah", "oda", "plus", "also", "ok", "okay", "item", "items",
    "product", "products", "me", "my", "i", "want", "need", "send"
}


def parse_voice_bill(shop_id, raw):

    text = (raw or "").lower()

    mobile = None
    m = re.search(r"(?<!\d)(\d{10})(?!\d)", text.replace(" ", "")) if re.search(r"\d{10}", text.replace(" ", "")) else None
    if m:
        mobile = m.group(1)
        text = re.sub(r"(\d[\s-]*){10}", " ", text)

    tokens = re.findall(r"\d+|[a-z\u0b80-\u0bff]+", text)

    products = active_products(shop_id)

    name_tokens = []
    for p in products:
        toks = re.findall(r"[a-z0-9\u0b80-\u0bff]+", (p.name or "").lower())
        if toks:
            name_tokens.append((toks, p))
    name_tokens.sort(key=lambda x: len(x[0]), reverse=True)

    single_names = {toks[0]: p for toks, p in name_tokens if len(toks) == 1}

    def num_at(j):
        tok = tokens[j]
        if tok.isdigit():
            return int(tok)
        return NUM_WORDS.get(tok)

    used = set()
    matched = {}      # product_id -> {"product": p, "qty": n}
    order = []
    consumed = set()

    i = 0
    while i < len(tokens):

        tok = tokens[i]
        hit = None
        length = 1

        for toks, p in name_tokens:
            n = len(toks)
            if tokens[i:i + n] == toks:
                hit, length = p, n
                break

        if hit is None and len(tok) >= 3 and not tok.isdigit() \
                and tok not in NOISE_WORDS and tok not in UNIT_WORDS and tok not in NUM_WORDS:
            close = difflib.get_close_matches(tok, list(single_names.keys()), n=1, cutoff=0.78)
            if close:
                hit = single_names[close[0]]

        if hit is None:
            i += 1
            continue

        for k in range(i, i + length):
            consumed.add(k)

        qty_idx = None

        j = i - 1
        while j >= 0 and tokens[j] in UNIT_WORDS:
            consumed.add(j)
            j -= 1
        if j >= 0 and j not in used and num_at(j) is not None:
            qty_idx = j

        if qty_idx is None:
            j = i + length
            while j < len(tokens) and tokens[j] in UNIT_WORDS:
                consumed.add(j)
                j += 1
            if j < len(tokens) and j not in used and num_at(j) is not None:
                qty_idx = j

        qty = 1
        if qty_idx is not None:
            qty = max(1, num_at(qty_idx))
            used.add(qty_idx)
            consumed.add(qty_idx)

        if hit.id in matched:
            matched[hit.id]["qty"] += qty
        else:
            matched[hit.id] = {"product": hit, "qty": qty}
            order.append(hit.id)

        i += length

    items, warnings = [], []

    for pid in order:
        p = matched[pid]["product"]
        qty = matched[pid]["qty"]
        stock = p.stock or 0
        if qty > stock:
            warnings.append(f"{p.name}: stock {stock} mattum, neenga {qty} sonneenga.")
        items.append({
            "product_id": p.id,
            "name": p.name,
            "quantity": qty,
            "price": float(p.price_sell or 0)
        })

    leftovers = []
    for idx, tok in enumerate(tokens):
        if idx in consumed or tok.isdigit() or tok in NOISE_WORDS \
                or tok in UNIT_WORDS or tok in NUM_WORDS or len(tok) < 3:
            continue
        if tok not in leftovers:
            leftovers.append(tok)

    return {
        "items": items,
        "mobile": mobile,
        "not_found": leftovers[:3],
        "warnings": warnings
    }


# =========================================================
# ROUTES
# =========================================================

def _ajax_ok():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


@assistant_bp.route("/assistant")
@login_required
@premium_required
def assistant_page():

    shop_id = session["shop_id"]

    return render_template(
        "assistant.html",
        insights=build_insights(shop_id),
        examples=EXAMPLES
    )


@assistant_bp.route("/api/insights")
@login_required
@premium_required
def api_insights():

    return jsonify({"insights": build_insights(session["shop_id"])})


@assistant_bp.route("/api/assistant", methods=["POST"])
@login_required
@premium_required
def api_assistant():

    data = request.get_json(silent=True) or {}

    if not _ajax_ok():
        return jsonify({"error": "bad request"}), 400

    message = str(data.get("message", ""))[:300]

    return jsonify(answer_question(session["shop_id"], message))


@assistant_bp.route("/api/voice_bill", methods=["POST"])
@login_required
@premium_required
def api_voice_bill():

    data = request.get_json(silent=True) or {}

    if not _ajax_ok():
        return jsonify({"error": "bad request"}), 400

    text = str(data.get("text", ""))[:300]

    result = parse_voice_bill(session["shop_id"], text)
    result["ok"] = True

    return jsonify(result)