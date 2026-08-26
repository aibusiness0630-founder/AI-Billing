from datetime import datetime
from app import db

class Subscription(db.Model):
    __tablename__ = 'subscription'
    
    id = db.Column(db.Integer, primary_key=True)
    
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False
    )
    
    plan = db.Column(
        db.String(50),
        default='Monthly'
    )
    
    start_date = db.Column(
        db.Date,
        default=lambda: datetime.utcnow().date()
    )
    
    expiry_date = db.Column(
        db.Date
    )
    
    status = db.Column(
        db.String(20),
        default='Active'
    )
    
    reminder_sent = db.Column(
        db.Boolean,
        default=False
    )
    
    def __repr__(self):
        return f'<Subscription {self.shop_id} {self.plan}>'