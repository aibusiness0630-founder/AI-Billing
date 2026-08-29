from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session
)

import os

from app import db
from app.models import Customer, Invoice
from app.utils.decorators import login_required

customers_bp = Blueprint('customers', __name__)


@customers_bp.route("/customers")
@login_required
def customers():

    shop_id = session["shop_id"]

    all_customers = Customer.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Customer.name
    ).all()

    return render_template(
        "customers.html",
        customers=all_customers
    )


@customers_bp.route("/add_customer", methods=["GET", "POST"])
@login_required
def add_customer():

    shop_id = session["shop_id"]

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name or not mobile:
            return "❌ Name and Mobile are required"

        existing = Customer.query.filter_by(
            mobile=mobile,
            shop_id=shop_id
        ).first()

        if existing:
            return "❌ Customer with this mobile already exists"

        new_customer = Customer(
            shop_id=shop_id,
            name=name,
            mobile=mobile,
            email=email,
            address=address
        )

        db.session.add(new_customer)
        db.session.commit()

        return redirect("/customers")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "add_customer.html",
        csrf_token=session.get("csrf_token")
    )


@customers_bp.route("/edit_customer/<int:id>", methods=["GET", "POST"])
@login_required
def edit_customer(id):

    shop_id = session["shop_id"]

    customer = Customer.query.filter_by(
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

        if not name or not mobile:
            return "❌ Name and Mobile are required"

        customer.name = name
        customer.mobile = mobile
        customer.email = email
        customer.address = address

        db.session.commit()

        return redirect("/customers")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "edit_customer.html",
        customer=customer,
        csrf_token=session.get("csrf_token")
    )


@customers_bp.route("/delete_customer/<int:id>")
@login_required
def delete_customer(id):

    shop_id = session["shop_id"]

    customer = Customer.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    db.session.delete(customer)
    db.session.commit()

    return redirect("/customers")


@customers_bp.route("/customer/<int:id>")
@login_required
def customer_profile(id):

    shop_id = session["shop_id"]

    customer = Customer.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    invoices = Invoice.query.filter_by(
        customer_id=customer.id,
        shop_id=shop_id
    ).order_by(
        Invoice.id.desc()
    ).all()

    total_bills = len(invoices)

    total_purchase = sum(inv.total_amount or 0 for inv in invoices)

    average_bill = round(total_purchase / total_bills, 2) if total_bills else 0

    last_purchase = invoices[0] if invoices else None

    return render_template(
        "customer_profile.html",
        customer=customer,
        bills=invoices,
        total_bills=total_bills,
        total_purchase=total_purchase,
        average_bill=average_bill,
        last_purchase=last_purchase
    )