from datetime import datetime
from app import db

class Product(db.Model):
    __tablename__ = 'product'
    
    id = db.Column(db.Integer, primary_key=True)
    
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False
    )
    
    category_id = db.Column(
        db.Integer,
        db.ForeignKey('category.id')
    )
    
    name = db.Column(
        db.String(100),
        nullable=False
    )
    
    description = db.Column(
        db.Text
    )
    
    sku = db.Column(
        db.String(100)
    )
    
    barcode = db.Column(
        db.String(100)
    )
    
    price_sell = db.Column(
        db.Float,
        nullable=False
    )
    
    price_cost = db.Column(
        db.Float
    )
    
    stock = db.Column(
        db.Integer,
        default=0
    )
    
    min_stock = db.Column(
        db.Integer,
        default=10
    )
    
    max_stock = db.Column(
        db.Integer
    )
    
    is_active = db.Column(
        db.Boolean,
        default=True
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