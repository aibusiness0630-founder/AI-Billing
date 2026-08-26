from datetime import datetime
from app import db

class Purchase(db.Model):
    __tablename__ = 'purchase'
    
    id = db.Column(db.Integer, primary_key=True)
    
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False
    )
    
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey('supplier.id'),
        nullable=False
    )
    
    purchase_number = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )
    
    subtotal = db.Column(
        db.Float,
        default=0
    )
    
    tax_amount = db.Column(
        db.Float,
        default=0
    )
    
    total_amount = db.Column(
        db.Float,
        nullable=False
    )
    
    payment_status = db.Column(
        db.String(50),
        default='PENDING'
    )
    # PENDING, PARTIAL, PAID
    
    notes = db.Column(
        db.Text
    )
    
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class PurchaseItem(db.Model):
    __tablename__ = 'purchase_item'
    
    id = db.Column(db.Integer, primary_key=True)
    
    purchase_id = db.Column(
        db.Integer,
        db.ForeignKey('purchase.id'),
        nullable=False
    )
    
    product_id = db.Column(
        db.Integer,
        db.ForeignKey('product.id'),
        nullable=False
    )
    
    quantity = db.Column(
        db.Integer,
        nullable=False
    )
    
    cost_price = db.Column(
        db.Float,
        nullable=False
    )
    
    total = db.Column(
        db.Float,
        nullable=False
    )