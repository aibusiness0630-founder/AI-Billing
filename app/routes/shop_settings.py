from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session
)

from werkzeug.security import generate_password_hash
import os

from app import db
from app.models import Shop
from app.utils.decorators import login_required

shop_settings_bp = Blueprint('shop_settings', __name__)


@shop_settings_bp.route("/shop-settings", methods=["GET", "POST"])
@login_required
def shop_settings():

    shop = Shop.query.filter_by(
        id=session["shop_id"]
    ).first_or_404()

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        shop_name = request.form.get("shop_name")
        address = request.form.get("address")
        phone = request.form.get("phone")
        shop_type = request.form.get("shop_type")

        if not shop_name:
            return "Shop name required"

        shop.shop_name = shop_name
        shop.address = address
        shop.phone = phone
        shop.shop_type = shop_type

        db.session.commit()

        return redirect("/shop-settings")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "shop_settings.html",
        shop=shop,
        csrf_token=session.get("csrf_token")
    )


@shop_settings_bp.route("/shop", methods=["GET", "POST"])
def shop():

    if request.method == "GET":

        if "shop_id" in session:

            shop = Shop.query.filter_by(
                id=session["shop_id"]
            ).first()

            session["csrf_token"] = os.urandom(32).hex()

            return render_template(
                "shop.html",
                shop=shop,
                csrf_token=session.get("csrf_token")
            )

        session["csrf_token"] = os.urandom(32).hex()

        return render_template(
            "shop.html",
            shop=None,
            csrf_token=session.get("csrf_token")
        )

    shop_id = session.get("shop_id")

    if shop_id:
        shop = Shop.query.filter_by(id=shop_id).first_or_404()
    else:
        shop = None

    shop_name = request.form.get("shop_name")
    address = request.form.get("address")
    phone = request.form.get("phone")
    shop_type = request.form.get("shop_type")
    username = request.form.get("username")
    password = request.form.get("password")

    if not shop_name:
        return "Shop name required"

    csrf_token = request.form.get("csrf_token", "")
    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    if shop is None:

        if not username or not password:
            return "Username and Password required for new shop"

        existing_username = Shop.query.filter_by(username=username).first()

        if existing_username:
            return "❌ Username already exists"

        shop = Shop(
            shop_name=shop_name,
            address=address,
            phone=phone,
            shop_type=shop_type,
            username=username,
            password=generate_password_hash(password)
        )

        db.session.add(shop)
        db.session.commit()

        from app.models import Subscription
        from datetime import datetime, timedelta

        subscription = Subscription(
            shop_id=shop.id,
            plan="Monthly",
            start_date=datetime.now().date(),
            expiry_date=(datetime.now() + timedelta(days=30)).date(),
            status="Active"
        )

        db.session.add(subscription)
        db.session.commit()

        session.clear()
        session["shop_id"] = shop.id

        return redirect("/")

    shop.shop_name = shop_name
    shop.address = address
    shop.phone = phone
    shop.shop_type = shop_type

    if username:

        existing_username = Shop.query.filter(
            Shop.username == username,
            Shop.id != shop.id
        ).first()

        if existing_username:
            return "❌ Username already exists"

        shop.username = username

    if password:
        shop.password = generate_password_hash(password)

    db.session.commit()

    return redirect("/shop")