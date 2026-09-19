from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session
)

import os

from app import db
from app.models import Supplier
from app.utils.decorators import login_required, premium_required

suppliers_bp = Blueprint('suppliers', __name__)


@suppliers_bp.route("/suppliers")
@login_required
@premium_required
def suppliers():

    shop_id = session["shop_id"]

    all_suppliers = Supplier.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Supplier.name
    ).all()

    return render_template(
        "suppliers.html",
        suppliers=all_suppliers
    )


@suppliers_bp.route("/add_supplier", methods=["GET", "POST"])
@login_required
@premium_required
def add_supplier():

    shop_id = session["shop_id"]

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        contact_person = request.form.get("contact_person", "").strip()

        if not name:
            return "❌ Supplier name is required"

        new_supplier = Supplier(
            shop_id=shop_id,
            name=name,
            mobile=mobile,
            email=email,
            address=address,
            contact_person=contact_person
        )

        db.session.add(new_supplier)
        db.session.commit()

        return redirect("/suppliers")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "add_supplier.html",
        csrf_token=session.get("csrf_token")
    )


@suppliers_bp.route("/edit_supplier/<int:id>", methods=["GET", "POST"])
@login_required
@premium_required
def edit_supplier(id):

    shop_id = session["shop_id"]

    supplier = Supplier.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        contact_person = request.form.get("contact_person", "").strip()

        if not name:
            return "❌ Supplier name is required"

        supplier.name = name
        supplier.mobile = mobile
        supplier.email = email
        supplier.address = address
        supplier.contact_person = contact_person

        db.session.commit()

        return redirect("/suppliers")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "edit_supplier.html",
        supplier=supplier,
        csrf_token=session.get("csrf_token")
    )


@suppliers_bp.route("/delete_supplier/<int:id>")
@login_required
@premium_required
def delete_supplier(id):

    shop_id = session["shop_id"]

    supplier = Supplier.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    db.session.delete(supplier)
    db.session.commit()

    return redirect("/suppliers")