from flask import Blueprint, render_template

legal_bp = Blueprint("legal", __name__)

# Edit these values to change the text on all legal pages.
COMPANY = {
    "name": "ANFIA Technology",
    "product": "AI Billing",
    "email": "mohammedalmubris@gmail.com",
    "phone": "+91 9363897197",
    "address": "Theni, Tamil Nadu, India",
    "updated": "24 October 2026",
}


def _page(template):
    return render_template(template, c=COMPANY)


@legal_bp.route("/terms")
def terms():
    return _page("legal_terms.html")


@legal_bp.route("/privacy")
def privacy():
    return _page("legal_privacy.html")


@legal_bp.route("/refund-policy")
def refund_policy():
    return _page("legal_refund.html")


@legal_bp.route("/contact")
def contact():
    return _page("legal_contact.html")
