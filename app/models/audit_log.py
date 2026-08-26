from datetime import datetime
from app import db

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    
    id = db.Column(db.Integer, primary_key=True)
    
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False
    )
    
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id')
    )
    
    action = db.Column(
        db.String(100),
        nullable=False
    )
    # CREATE, UPDATE, DELETE, LOGIN, etc.
    
    entity_type = db.Column(
        db.String(50)
    )
    # INVOICE, PRODUCT, CUSTOMER, etc.
    
    entity_id = db.Column(
        db.Integer
    )
    
    details = db.Column(
        db.Text
    )
    
    ip_address = db.Column(
        db.String(50)
    )
    
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )
    
    def __repr__(self):
        return f'<AuditLog {self.action} {self.entity_type}>'