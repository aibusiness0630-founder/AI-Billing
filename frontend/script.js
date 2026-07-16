let total = 0;
let products =[];
function addProduct() {
    let price = Number(document.getElementById("price").value);
    let quantity = Number(document.getElementById("quantity").value);
    total = total + (price * quantity);
    products.push({
    name: document.getElementById("product").value,
    price: price,
    quantity: quantity
});
    document.getElementById("total").innerText = "Total : ₹" + total;
    let list = document.getElementById("billList");
let item = document.createElement("li");
let amount = price * quantity;
item.innerHTML =
document.getElementById("product").value +
" - ₹" + amount +
` <button onclick="deleteItem(this, ${amount})">❌</button>`;
list.appendChild(item);
    document.getElementById("product").value = "";
    document.getElementById("price").value = "";
    document.getElementById("quantity").value = "";
}
function deleteItem(button, amount) {
    total = total - amount;
    document.getElementById("total").innerText = "Total : ₹" + total;
    button.parentElement.remove();
}