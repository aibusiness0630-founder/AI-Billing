from datetime import datetime
from app import db


class SubscriptionPayment(db.Model):
    """Money ANFIA received from a shop for its subscription."""
    __tablename__ = 'subscription_payment'

    id = db.Column(db.Integer, primary_key=True)

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False,
        index=True
    )

    amount = db.Column(
        db.Float,
        nullable=False
    )

    method = db.Column(
        db.String(30)
    )
    # Cash, UPI, Bank Transfer, Other

    plan = db.Column(
        db.String(50)
    )

    days = db.Column(
        db.Integer
    )

    note = db.Column(
        db.String(255)
    )

    created_by = db.Column(
        db.String(100)
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    def __repr__(self):
        return f'<SubscriptionPayment {self.shop_id} {self.amount}>'
