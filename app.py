from flask import Flask,render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///billing.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    mobile = db.Column(db.String(20))
    product = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    total = db.Column(db.Float)


class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(100))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    shop_type = db.Column(db.String(50))

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":

        customer_name = request.form.get("customer_name")
        mobile = request.form.get("mobile")

        products = request.form.getlist("product[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("price[]")

        grand_total = 0

        for product, quantity, price in zip(products, quantities, prices):

            if product.strip() == "" or quantity.strip() == "" or price.strip() == "":
                continue

            quantity = int(quantity)
            price = float(price)
            total = quantity * price
            grand_total += total

            new_bill = Bill(
                customer_name=customer_name,
                mobile=mobile,
                product=product,
                quantity=quantity,
                price=price,
                total=total
            )

            db.session.add(new_bill)

        db.session.commit()

        shop = Shop.query.first()
        current_time = datetime.now().strftime("%d-%m-%Y %I:%M %p")

        return render_template(
            "bill.html",
            shop=shop,
            customer_name=customer_name,
            mobile=mobile,
            products=products,
            quantities=quantities,
            prices=prices,
            grand_total=grand_total,
            current_time=current_time
        )

    return render_template("index.html")
@app.route("/history")
def history():
    bills = Bill.query.all()
    return render_template("history.html", bills=bills)

@app.route("/shop", methods=["GET", "POST"])
def shop():
    if request.method == "POST":
        shop = Shop(
            shop_name=request.form.get("shop_name"),
            address=request.form.get("address"),
            phone=request.form.get("phone"),
            shop_type=request.form.get("shop_type")
        )

        db.session.add(shop)
        db.session.commit()

        return redirect("/")

    return render_template("shop.html")

@app.route("/search", methods=["GET", "POST"])
def search():
    bills = []

    if request.method == "POST":
        customer = request.form.get("customer")
        bills = Bill.query.filter(
            Bill.customer_name.ilike(f"%{customer}%")
        ).all()

    return render_template("search.html", bills=bills)
@app.route("/delete/<int:id>")
def delete(id):
    bill = Bill.query.get_or_404(id)
    db.session.delete(bill)
    db.session.commit()
    return redirect("/history")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)