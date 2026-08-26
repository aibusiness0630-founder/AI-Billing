from datetime import datetime
from app import db

class Category(db.Model):
    __tablename__ = 'category'
    
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
    
    description = db.Column(
        db.Text
    )
    
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    
    def __repr__(self):
        return f'<Category {self.name}>'