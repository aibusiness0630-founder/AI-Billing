from datetime import datetime
from app import db

class Shop(db.Model):
    __tablename__ = 'shop'
    
    id = db.Column(db.Integer, primary_key=True)
    
    shop_name = db.Column(
        db.String(100),
        nullable=False
    )
    
    address = db.Column(
        db.String(200)
    )
    
    phone = db.Column(
        db.String(20)
    )
    
    shop_type = db.Column(
        db.String(50)
    )
    
    username = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )
    
    password = db.Column(
        db.String(255),
        nullable=False
    )
    
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    
    def __repr__(self):
        return f'<Shop {self.shop_name}>'