let billNumber = 1;
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
function updateDateTime() {
    let now = new Date();
    document.getElementById("date").innerText =
        "Date : " + now.toLocaleDateString();
    document.getElementById("time").innerText =
        "Time : " + now.toLocaleTimeString();
}
setInterval(updateDateTime, 1000);
updateDateTime();
function nextBill() {
    billNumber++;
    document.getElementById("billNo").innerText =
        "Bill No : BILL" + String(billNumber).padStart(3, "0");
}
function clearBill() {
    document.getElementById("billList").innerHTML = "";
    total = 0;
    document.getElementById("total").innerText = "Total : ₹0";
    document.getElementById("customer").value = "";
    document.getElementById("product").value = "";
    document.getElementById("price").value = "";
    document.getElementById("quantity").value = "";
    nextBill();
}