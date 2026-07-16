let total = 0;
function addProduct() {
    let price = Number(document.getElementById("price").value);
    let quantity = Number(document.getElementById("quantity").value);
    total = total + (price * quantity);
    document.getElementById("total").innerText = "Total : ₹" + total;
    document.getElementById("product").value = "";
    document.getElementById("price").value = "";
    document.getElementById("quantity").value = "";
}