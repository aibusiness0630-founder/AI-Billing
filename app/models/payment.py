from datetime import datetime
from app import db

class Payment(db.Model):
    __tablename__ = 'payment'
    
    id = db.Column(db.Integer, primary_key=True)
    
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False
    )
    
    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey('invoice.id')
    )
    
    amount = db.Column(
        db.Float,
        nullable=False
    )
    
    method = db.Column(
        db.String(50),
        nullable=False
    )
    # CASH, UPI, CARD, CHEQUE, BANK_TRANSFER
    
    reference_number = db.Column(
        db.String(100)
    )
    
    notes = db.Column(
        db.Text
    )
    
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )