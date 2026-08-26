from datetime import datetime
from app import db

class Invoice(db.Model):
    __tablename__ = 'invoice'
    
    id = db.Column(db.Integer, primary_key=True)
    
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False
    )
    
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey('customer.id')
    )
    
    invoice_number = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )
    
    subtotal = db.Column(
        db.Float,
        default=0
    )
    
    discount_amount = db.Column(
        db.Float,
        default=0
    )
    
    discount_percent = db.Column(
        db.Float,
        default=0
    )
    
    tax_amount = db.Column(
        db.Float,
        default=0
    )
    
    tax_percent = db.Column(
        db.Float,
        default=0
    )
    
    total_amount = db.Column(
        db.Float,
        nullable=False
    )
    
    payment_method = db.Column(
        db.String(50)
    )
    # CASH, UPI, CARD, CHEQUE, CREDIT
    
    payment_status = db.Column(
        db.String(50),
        default='PAID'
    )
    # PAID, PENDING, PARTIAL, CANCELLED
    
    notes = db.Column(
        db.Text
    )
    
    created_by = db.Column(
        db.Integer,
        db.ForeignKey('user.id')
    )
    
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class InvoiceItem(db.Model):
    __tablename__ = 'invoice_item'
    
    id = db.Column(db.Integer, primary_key=True)
    
    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey('invoice.id'),
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
    
    price = db.Column(
        db.Float,
        nullable=False
    )
    
    discount = db.Column(
        db.Float,
        default=0
    )
    
    total = db.Column(
        db.Float,
        nullable=False
    )