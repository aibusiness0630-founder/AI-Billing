from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        customer_name = request.form.get("customer_name")
        mobile = request.form.get("mobile")
        product = request.form.get("product")

        quantity = int(request.form.get("quantity"))
        price = float(request.form.get("price"))

        total = quantity * price

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

if __name__ == "__main__":
    app.run(debug=True)