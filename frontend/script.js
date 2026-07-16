let total = 0;
function addProduct() {
    let price = Number(document.getElementById("price").value);
    let quantity = Number(document.getElementById("quantity").value);
    total = total + (price * quantity);
    document.getElementById("total").innerText = "Total : ₹" + total;
    let list = document.getElementById("billList");
let item = document.createElement("li");
item.innerHTML =
document.getElementById("product").value +
" - ₹" + (price * quantity) +
' <button onclick="this.parentElement.remove()">❌</button>';
list.appendChild(item);
    document.getElementById("product").value = "";
    document.getElementById("price").value = "";
    document.getElementById("quantity").value = "";
}