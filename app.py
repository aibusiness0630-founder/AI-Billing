from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy

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

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        customer_name = request.form.get("customer_name")
        mobile = request.form.get("mobile")
        product = request.form.get("product")

        quantity = int(request.form.get("quantity"))
        price = float(request.form.get("price"))
        total = quantity * price

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

        return f"""
        <h2>Bill</h2>
        Customer: {customer_name}<br>
        Mobile: {mobile}<br>
        Product: {product}<br>
        Quantity: {quantity}<br>
        Price: ₹{price}<br>
        <h3>Total: ₹{total}</h3>
        """
       

    return render_template("index.html")
@app.route("/history")
def history():
    bills = Bill.query.all()
    return render_template("history.html", bills=bills)

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