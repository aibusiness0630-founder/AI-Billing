"""
Founder AI Agent - brain (rule-based, no external API, no cost).

answer(question, data) -> {"text": str, "cards": [...], "chips": [...]}

`data` is plain python (built by app/routes/agent.py from the database),
so this file has no database code and is easy to test.

data = {
  "today": date,
  "pending": int,
  "shops": [ {id, name, phone, status, plan, expiry(date|None),
              state('active'|'expiring'|'expired'|'suspended'), days_left(int|None)} ],
  "pay_this": float, "pay_last": float, "pay_total": float, "pay_today": float,
  "signups_this": int, "signups_last": int,
  "recent_payments": [ {shop, amount, method, plan, when} ],
  "prices": {"Basic": 499, "Premium": 999},
  "wa": callable(shop_dict, text) -> url or None,
}
"""
import re

STOP = {
    "the", "a", "an", "of", "is", "are", "me", "my", "show", "tell", "give", "list",
    "shop", "shops", "details", "detail", "find", "search", "about", "for", "please",
    "enna", "yaar", "evlo", "epdi", "iruku", "irukku", "pannu", "sollu", "kaattu",
    "kaatu", "and", "to", "in", "on", "what", "who", "how", "much", "many", "status",
}

CHIPS = [
    "Daily brief",
    "Indha maasam revenue evlo?",
    "Expiring shops",
    "Pending approvals",
    "Reminder drafts",
    "Recent payments",
]


def money(v):
    v = float(v or 0)
    if v == int(v):
        return "₹{:,}".format(int(v))
    return "₹{:,.2f}".format(v)


def _has(q, *words):
    return any(w in q for w in words)


def _num_days(q, default):
    m = re.search(r"(\d+)\s*(day|days|naal|nal|din)", q)
    if m:
        return max(1, min(int(m.group(1)), 365))
    if _has(q, "week", "vaaram", "varam"):
        return 7
    if _has(q, "month", "maasam", "masam"):
        return 30
    return default


def _fmt_date(d):
    return d.strftime("%d-%m-%Y") if d else "-"


def _shop_card(s, wa_text=None, data=None):
    bits = [s["plan"] or "-"]
    if s["state"] == "suspended":
        bits.append("suspended")
    elif s["expiry"]:
        if s["days_left"] is not None and s["days_left"] < 0:
            bits.append("expired %s (%d days ago)" % (_fmt_date(s["expiry"]), -s["days_left"]))
        else:
            bits.append("expires %s (%s days left)" % (_fmt_date(s["expiry"]), s["days_left"]))
    else:
        bits.append("no expiry date")

    card = {
        "title": s["name"],
        "sub": " • ".join(bits),
        "url": "/superadmin/customers/%d" % s["id"],
        "wa": None,
        "wa_label": None,
    }
    if wa_text and data and data.get("wa"):
        card["wa"] = data["wa"](s, wa_text)
        card["wa_label"] = "WhatsApp reminder" if card["wa"] else "No phone number"
    return card


def _expiring(data, days):
    out = [s for s in data["shops"]
           if s["state"] in ("active", "expiring")
           and s["days_left"] is not None and 0 <= s["days_left"] <= days]
    out.sort(key=lambda s: s["days_left"])
    return out


def _expired(data, within=30):
    out = [s for s in data["shops"]
           if s["state"] == "expired" and s["days_left"] is not None
           and s["days_left"] >= -within]
    out.sort(key=lambda s: -s["days_left"])
    return out


def _price(data, s):
    return data["prices"].get(s["plan"], data["prices"]["Basic"])


def _remind_text(s, expired):
    exp = _fmt_date(s["expiry"])
    if expired:
        return ("Vanakkam! Unga %s AI Billing %s plan %s anru expire aagiduchu. "
                "Marubadiyum use panna reply pannunga. - ANFIA Technology"
                % (s["name"], s["plan"], exp))
    return ("Vanakkam! Unga %s AI Billing %s plan %s anru expire aagum. "
            "Renew panna ippove reply pannunga. - ANFIA Technology"
            % (s["name"], s["plan"], exp))


def _active_stats(data):
    act = [s for s in data["shops"] if s["state"] in ("active", "expiring")]
    mrr = sum(_price(data, s) for s in act)
    basic = sum(1 for s in act if s["plan"] == "Basic")
    prem = sum(1 for s in act if s["plan"] == "Premium")
    return act, mrr, basic, prem


def _delta_text(this, last):
    if last > 0:
        pct = round((this - last) / last * 100)
        arrow = "up" if pct >= 0 else "down"
        return " (%s %d%% vs last month %s)" % (arrow, abs(pct), money(last))
    return " (last month %s)" % money(last)


# ------------------------------------------------------------------
# intents
# ------------------------------------------------------------------

def _brief(data):
    act, mrr, basic, prem = _active_stats(data)
    exp7 = _expiring(data, 7)
    lapsed = _expired(data, 30)
    risk = sum(_price(data, s) for s in exp7)

    lines = [
        "Daily brief – %s" % data["today"].strftime("%d %b %Y"),
        "• Pending approvals: %d" % data["pending"],
        "• Revenue this month: %s%s" % (money(data["pay_this"]),
                                           _delta_text(data["pay_this"], data["pay_last"])),
        "• Received today: %s" % money(data["pay_today"]),
        "• Active shops: %d (Basic %d, Premium %d) • MRR %s" % (len(act), basic, prem, money(mrr)),
        "• Expiring in 7 days: %d shops (%s at stake)" % (len(exp7), money(risk)),
        "• Lapsed in last 30 days: %d shops" % len(lapsed),
        "• New signups this month: %d" % data["signups_this"],
    ]

    todo = []
    if data["pending"]:
        todo.append("%d shop(s) approval ku wait panraanga" % data["pending"])
    if exp7:
        todo.append("%d shop renewal reminder anuppanum" % len(exp7))
    if lapsed:
        todo.append("%d lapsed shop-ku win-back message" % len(lapsed))
    if todo:
        lines.append("")
        lines.append("Today to-do: " + "; ".join(todo) + ".")
    else:
        lines.append("")
        lines.append("Ippo urgent ah edhuvum illa.")

    return {"text": "\n".join(lines), "cards": [], "chips": ["Reminder drafts", "Expiring shops"]}


def _revenue(q, data):
    if _has(q, "last month", "kadantha", "previous", "pona maasam", "last maasam"):
        return {"text": "Last month vandha payment: %s" % money(data["pay_last"]),
                "cards": [], "chips": ["Indha maasam revenue evlo?"]}
    if _has(q, "total", "overall", "ellam", "all time", "motham"):
        return {"text": "Ippo varai ANFIA ku vandha total: %s" % money(data["pay_total"]),
                "cards": [], "chips": ["Daily brief"]}
    if _has(q, "today", "inniku", "indru"):
        return {"text": "Inniku vandha payment: %s" % money(data["pay_today"]),
                "cards": [], "chips": ["Recent payments"]}
    return {
        "text": "Indha maasam vandha payment: %s%s\nTotal (all time): %s"
                % (money(data["pay_this"]), _delta_text(data["pay_this"], data["pay_last"]),
                   money(data["pay_total"])),
        "cards": [], "chips": ["Recent payments", "Expiring shops"],
    }


def _mrr(data):
    act, mrr, basic, prem = _active_stats(data)
    return {"text": "MRR (active plans): %s\nActive shops: %d – Basic %d x %s, Premium %d x %s"
                    % (money(mrr), len(act), basic, money(data["prices"]["Basic"]),
                       prem, money(data["prices"]["Premium"])),
            "cards": [], "chips": ["Daily brief"]}


def _expiring_answer(q, data):
    days = _num_days(q, 7)
    shops = _expiring(data, days)
    if not shops:
        return {"text": "Next %d days la expire aagura shop illa." % days,
                "cards": [], "chips": ["Expiring in 30 days", "Reminder drafts"]}
    risk = sum(_price(data, s) for s in shops)
    cards = [_shop_card(s, _remind_text(s, False), data) for s in shops]
    return {"text": "Next %d days la %d shop expire aagum (renewal value %s):"
                    % (days, len(shops), money(risk)),
            "cards": cards, "chips": ["Expired shops", "Daily brief"]}


def _expired_answer(data):
    shops = _expired(data, 30)
    if not shops:
        return {"text": "Last 30 days la expire aana shop illa.",
                "cards": [], "chips": ["Expiring shops"]}
    cards = [_shop_card(s, _remind_text(s, True), data) for s in shops]
    return {"text": "%d shop plan expire aagi irukku (last 30 days):" % len(shops),
            "cards": cards, "chips": ["Expiring shops", "Daily brief"]}


def _reminders(data):
    soon = _expiring(data, 7)
    lapsed = _expired(data, 30)
    if not soon and not lapsed:
        return {"text": "Reminder anuppa vendiya shop ippo illa.", "cards": [], "chips": ["Daily brief"]}
    cards = [_shop_card(s, _remind_text(s, False), data) for s in soon]
    cards += [_shop_card(s, _remind_text(s, True), data) for s in lapsed]
    return {"text": "WhatsApp reminder drafts ready: %d expiring + %d lapsed. "
                    "Button click pannina WhatsApp open aagum, neenga Send mattum press pannunga."
                    % (len(soon), len(lapsed)),
            "cards": cards, "chips": ["Daily brief"]}


def _pending(data):
    n = data["pending"]
    if n == 0:
        return {"text": "Pending approval edhuvum illa.", "cards": [], "chips": ["Daily brief"]}
    return {"text": "%d shop approval ku wait panraanga." % n,
            "cards": [{"title": "Approvals page ku po", "sub": "%d pending" % n,
                       "url": "/superadmin/approvals?status=PENDING", "wa": None, "wa_label": None}],
            "chips": ["Daily brief"]}


def _payments(data):
    rows = data["recent_payments"]
    if not rows:
        return {"text": "Innum payment edhuvum record aagala.", "cards": [], "chips": []}
    cards = [{"title": "%s – %s" % (r["shop"], money(r["amount"])),
              "sub": "%s • %s • %s" % (r["method"] or "-", r["plan"] or "-", r["when"]),
              "url": None, "wa": None, "wa_label": None} for r in rows]
    return {"text": "Last %d payments:" % len(rows), "cards": cards,
            "chips": ["Indha maasam revenue evlo?"]}


def _counts(q, data):
    act, mrr, basic, prem = _active_stats(data)
    total = len(data["shops"])
    susp = sum(1 for s in data["shops"] if s["state"] == "suspended")
    exp = sum(1 for s in data["shops"] if s["state"] == "expired")

    if _has(q, "premium") and not _has(q, "basic"):
        return {"text": "Premium active shops: %d" % prem, "cards": [], "chips": ["Daily brief"]}
    if _has(q, "basic") and not _has(q, "premium"):
        return {"text": "Basic active shops: %d" % basic, "cards": [], "chips": ["Daily brief"]}

    return {"text": "Approved shops: %d\n• Active: %d (Basic %d, Premium %d)\n"
                    "• Expired: %d\n• Suspended: %d\n• Pending approval: %d"
                    % (total, len(act), basic, prem, exp, susp, data["pending"]),
            "cards": [], "chips": ["Daily brief", "MRR"]}


def _signups(data):
    return {"text": "New signups – indha maasam: %d, last month: %d"
                    % (data["signups_this"], data["signups_last"]),
            "cards": [], "chips": ["Pending approvals"]}


def _find_shop(q, data):
    words = [w for w in re.findall(r"[a-z0-9]+", q) if len(w) >= 3 and w not in STOP]
    if not words:
        return None
    hits = []
    for s in data["shops"]:
        name = (s["name"] or "").lower()
        if all(w in name for w in words) or any(w in name for w in words):
            hits.append(s)
    if not hits:
        return None
    hits.sort(key=lambda s: -sum(1 for w in words if w in (s["name"] or "").lower()))
    hits = hits[:8]
    return {"text": "%d shop kidaichuchu:" % len(hits),
            "cards": [_shop_card(s) for s in hits], "chips": ["Daily brief"]}


def _help():
    return {
        "text": ("Naan ungal ANFIA business assistant. Ithellam kekkalam:\n"
                 "• Daily brief / inniku status\n"
                 "• Indha maasam revenue evlo? / total revenue\n"
                 "• Expiring shops / 30 days la expire aagura shops\n"
                 "• Expired shops\n"
                 "• Reminder drafts (WhatsApp)\n"
                 "• Pending approvals\n"
                 "• Recent payments\n"
                 "• MRR, Premium evlo shops, signups\n"
                 "• Shop peru type pannina avanga details"),
        "cards": [], "chips": CHIPS,
    }


def answer(question, data):
    q = (question or "").strip().lower()
    if not q:
        return _help()

    if _has(q, "help", "udhavi", "what can you", "enna panna mudiyum"):
        return _help()

    # "shop xyz", "find xyz" -> search by name first
    if q.startswith(("shop ", "find ", "details ", "detail ", "search ")):
        found = _find_shop(q, data)
        if found:
            return found

    if _has(q, "reminder", "remind", "whatsapp", "message draft", "draft", "win back", "winback"):
        return _reminders(data)

    if _has(q, "expired", "mudinjidu", "mudinjuduchu", "mudinjathu", "lapsed", "mudinja"):
        return _expired_answer(data)

    if _has(q, "expir", "mudiya", "renew", "renewal", "due"):
        return _expiring_answer(q, data)

    if _has(q, "pending", "approval", "approve", "wait panra"):
        return _pending(data)

    if _has(q, "recent payment", "last payment", "latest payment", "payments list",
            "payment list", "yaar pay", "who paid"):
        return _payments(data)

    if _has(q, "mrr", "recurring"):
        return _mrr(data)

    if _has(q, "revenue", "income", "earning", "earn", "paisa", "panam", "vandha",
            "vandhuruku", "collection", "received", "payment"):
        return _revenue(q, data)

    if _has(q, "signup", "sign up", "new shop", "register", "pudhu shop", "puthu shop"):
        return _signups(data)

    if _has(q, "brief", "summary", "today", "inniku", "status", "overview", "dashboard", "report"):
        return _brief(data)

    if _has(q, "how many", "evlo shop", "ethana", "count", "customers", "shops", "premium", "basic", "active"):
        return _counts(q, data)

    found = _find_shop(q, data)
    if found:
        return found

    res = _help()
    res["text"] = "Idhu puriyala bro. " + res["text"]
    return res