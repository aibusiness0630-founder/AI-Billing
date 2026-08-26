from datetime import datetime
from app import db

class Supplier(db.Model):
    __tablename__ = 'supplier'
    
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
        db.String(20)
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
    
    contact_person = db.Column(
        db.String(100)
    )
    
    total_purchases = db.Column(
        db.Float,
        default=0
    )
    
    outstanding_amount = db.Column(
        db.Float,
        default=0
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
        return f'<Supplier {self.name}>'