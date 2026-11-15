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
    # price for ONE unit (e.g. Rs.220 per kg)
    
    price_cost = db.Column(
        db.Float
    )
    
    unit = db.Column(
        db.String(20),
        default='pcs'
    )
    # pcs, dozen, packet, kg, litre
    
    stock = db.Column(
        db.Float,
        default=0
    )
    # in the product's unit (e.g. 12.5 kg)
    
    min_stock = db.Column(
        db.Float,
        default=10
    )
    
    max_stock = db.Column(
        db.Float
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