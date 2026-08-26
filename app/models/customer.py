from datetime import datetime
from app import db

class Customer(db.Model):
    __tablename__ = 'customer'
    
    id = db.Column(db.Integer, primary_key=True)
    
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False
    )
    
    name = db.Column(
        db.String(100),
        nullable=False
    )
    
    mobile = db.Column(
        db.String(20),
        nullable=False
    )
    
    email = db.Column(
        db.String(100)
    )
    
    address = db.Column(
        db.String(200)
    )
    
    city = db.Column(
        db.String(100)
    )
    
    state = db.Column(
        db.String(100)
    )
    
    pincode = db.Column(
        db.String(10)
    )
    
    total_spent = db.Column(
        db.Float,
        default=0
    )
    
    total_transactions = db.Column(
        db.Integer,
        default=0
    )
    
    last_purchase_date = db.Column(
        db.DateTime
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
    
    def __repr__(self):
        return f'<Customer {self.name}>'