from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    jsonify,
    session
)

import os
import pandas as pd

from app import db
from app.models import Product
from app.utils.decorators import login_required
from app.utils.units import (
    UNITS, normalize_unit, unit_choices, entry_units, fmt_qty, fmt_qty_unit
)

products_bp = Blueprint('products', __name__)


# Jinja filters usable in ALL templates:  {{ item.quantity|qty_unit(item.unit) }}
@products_bp.app_template_filter("qty")
def _qty_filter(q):
    return fmt_qty(q)


@products_bp.app_template_filter("qty_unit")
def _qty_unit_filter(q, unit):
    return fmt_qty_unit(q, unit)


def parse_stock(raw, unit):
    """Stock text -> float. pcs / packet must be whole numbers, others may be decimal."""
    stock = round(float(raw), 3)
    if stock != stock or stock < 0 or stock > 1000000:
        raise ValueError("Stock must be 0 or more")
    if UNITS[unit]["whole_only"] and stock != int(stock):
        raise ValueError("%s stock must be a whole number" % UNITS[unit]["label"])
    return stock


@products_bp.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():

    shop_id = session["shop_id"]

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        product_name = request.form.get("product_name", "").strip()
        price = request.form.get("price")
        stock = request.form.get("stock")
        barcode = request.form.get("barcode", "").strip()
        unit = normalize_unit(request.form.get("unit"))

        if not product_name or not price or not stock:
            return "All fields required"

        try:
            price = float(price)
            stock = parse_stock(stock, unit)
        except ValueError as e:
            return "❌ Invalid price or stock: %s" % e

        if price < 0:
            return "❌ Price cannot be negative"

        existing = Product.query.filter_by(
            name=product_name,
            shop_id=shop_id
        ).first()

        if existing:
            return "❌ Product already exists"

        if barcode:

            existing_barcode = Product.query.filter_by(
                barcode=barcode,
                shop_id=shop_id
            ).first()

            if existing_barcode:
                return "❌ This barcode is already assigned to another product"

        new_product = Product(
            name=product_name,
            price_sell=price,
            stock=stock,
            unit=unit,
            barcode=barcode if barcode else None,
            shop_id=shop_id
        )

        db.session.add(new_product)
        db.session.commit()

        return redirect("/products")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "add_product.html",
        units=unit_choices(),
        csrf_token=session.get("csrf_token")
    )


@products_bp.route("/products")
@login_required
def products():

    shop_id = session["shop_id"]

    all_products = Product.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Product.name
    ).all()

    return render_template(
        "products.html",
        products=all_products
    )


@products_bp.route("/import_products", methods=["GET", "POST"])
@login_required
def import_products():

    shop_id = session["shop_id"]

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        file = request.files.get("file")

        if not file or file.filename == "":
            return "❌ No File Selected"

        try:

            if file.filename.endswith(".csv"):
                df = pd.read_csv(file)
            elif file.filename.endswith(".xlsx"):
                df = pd.read_excel(file)
            else:
                return "❌ Only CSV or Excel Files Supported"

            df.columns = df.columns.str.strip()
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

            df.rename(
                columns={
                    "product Name": "Product Name",
                    "product name": "Product Name",
                    "PRODUCT NAME": "Product Name"
                },
                inplace=True
            )

            required_columns = ["Product Name", "Price", "Stock"]

            for column in required_columns:
                if column not in df.columns:
                    return f"❌ Missing Column : {column}"

            has_barcode_column = "Barcode" in df.columns
            has_unit_column = "Unit" in df.columns

            keep_columns = required_columns + (["Barcode"] if has_barcode_column else []) + (["Unit"] if has_unit_column else [])

            df = df[keep_columns]
            df = df.dropna(subset=required_columns)

            imported_count = 0
            skipped_count = 0

            for _, row in df.iterrows():

                product_name = str(row["Product Name"]).strip()

                existing = Product.query.filter_by(
                    name=product_name,
                    shop_id=shop_id
                ).first()

                if existing:
                    skipped_count += 1
                    continue

                barcode_value = None

                if has_barcode_column and pd.notna(row.get("Barcode")):
                    barcode_value = str(row["Barcode"]).strip()

                unit_value = normalize_unit(row.get("Unit")) if has_unit_column and pd.notna(row.get("Unit")) else "pcs"

                try:
                    stock_value = parse_stock(row["Stock"], unit_value)
                except ValueError:
                    skipped_count += 1
                    continue

                product = Product(
                    shop_id=shop_id,
                    name=product_name,
                    price_sell=float(row["Price"]),
                    stock=stock_value,
                    unit=unit_value,
                    barcode=barcode_value
                )

                db.session.add(product)
                imported_count += 1

            db.session.commit()

            return f"""
            ✅ Imported : {imported_count}<br>
            ⚠️ Skipped : {skipped_count}<br><br>
            <a href='/products'>⬅ Back to Products</a>
            """

        except Exception as e:
            db.session.rollback()
            return f"❌ Import Error : {str(e)}"

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "import_products.html",
        csrf_token=session.get("csrf_token")
    )


@products_bp.route("/get_price/<int:product_id>")
@login_required
def get_price(product_id):

    product = Product.query.filter_by(
        id=product_id,
        shop_id=session["shop_id"]
    ).first_or_404()

    unit = normalize_unit(product.unit)

    return jsonify({
        "price": product.price_sell,
        "unit": unit,
        "entry_units": entry_units(unit),
        "stock": product.stock
    })


@products_bp.route("/search_products")
@login_required
def search_products():

    shop_id = session["shop_id"]
    keyword = request.args.get("q", "").strip()

    products = Product.query.filter(
        Product.shop_id == shop_id,
        Product.name.ilike(f"%{keyword}%")
    ).all()

    return jsonify([
        {"id": p.id, "name": p.name, "price": p.price_sell, "unit": normalize_unit(p.unit)}
        for p in products
    ])


@products_bp.route("/get_product_by_barcode/<barcode>")
@login_required
def get_product_by_barcode(barcode):

    shop_id = session["shop_id"]

    product = Product.query.filter_by(
        barcode=barcode,
        shop_id=shop_id
    ).first()

    if not product:
        return jsonify({"found": False}), 404

    return jsonify({
        "found": True,
        "id": product.id,
        "name": product.name,
        "price": product.price_sell,
        "stock": product.stock,
        "unit": normalize_unit(product.unit)
    })


@products_bp.route("/edit_product/<int:id>", methods=["GET", "POST"])
@login_required
def edit_product(id):

    shop_id = session["shop_id"]

    product = Product.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        product_name = request.form.get("product_name")
        price = request.form.get("price")
        stock = request.form.get("stock")
        barcode = request.form.get("barcode", "").strip()
        unit = normalize_unit(request.form.get("unit"))

        if not product_name or not price or not stock:
            return "All fields required"

        try:
            price = float(price)
            stock = parse_stock(stock, unit)
        except ValueError as e:
            return "❌ Invalid price or stock: %s" % e

        if price < 0:
            return "❌ Price cannot be negative"

        if barcode:

            existing_barcode = Product.query.filter(
                Product.barcode == barcode,
                Product.shop_id == shop_id,
                Product.id != product.id
            ).first()

            if existing_barcode:
                return "❌ This barcode is already assigned to another product"

        product.name = product_name
        product.price_sell = price
        product.stock = stock
        product.unit = unit
        product.barcode = barcode if barcode else None

        db.session.commit()

        return redirect("/products")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "edit_product.html",
        product=product,
        units=unit_choices(),
        csrf_token=session.get("csrf_token")
    )


@products_bp.route("/delete_product/<int:id>")
@login_required
def delete_product(id):

    shop_id = session["shop_id"]

    product = Product.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    db.session.delete(product)
    db.session.commit()

    return redirect("/products")