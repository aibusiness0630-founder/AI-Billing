from datetime import datetime
from app import db

class StockMovement(db.Model):
    __tablename__ = 'stock_movement'
    
    id = db.Column(db.Integer, primary_key=True)
    
    product_id = db.Column(
        db.Integer,
        db.ForeignKey('product.id'),
        nullable=False
    )
    
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False
    )
    
    quantity_change = db.Column(
        db.Integer,
        nullable=False
    )
    
    reason = db.Column(
        db.String(50),
        nullable=False
    )
    # SALE, PURCHASE, ADJUSTMENT, DAMAGE, RETURN, OTHER
    
    reference_id = db.Column(
        db.String(100)
    )
    
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
    
    def __repr__(self):
        return f'<StockMovement {self.product_id} {self.quantity_change}>'