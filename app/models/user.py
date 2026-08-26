from datetime import datetime
from app import db

class User(db.Model):
    __tablename__ = 'user'
    
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
    
    username = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )
    
    password = db.Column(
        db.String(255),
        nullable=False
    )
    
    email = db.Column(
        db.String(100)
    )
    
    role = db.Column(
        db.String(50),
        default='CASHIER'
    )
    # Roles: OWNER, ADMIN, CASHIER, STAFF
    
    is_active = db.Column(
        db.Boolean,
        default=True
    )
    
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    
    def __repr__(self):
        return f'<User {self.username}>'