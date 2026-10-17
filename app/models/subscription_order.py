from datetime import datetime
from app import db


class SubscriptionOrder(db.Model):
    """One Razorpay order created when a shop clicks 'Pay'."""
    __tablename__ = 'subscription_order'

    id = db.Column(db.Integer, primary_key=True)

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey('shop.id'),
        nullable=False,
        index=True
    )

    razorpay_order_id = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    razorpay_payment_id = db.Column(
        db.String(100)
    )

    plan = db.Column(
        db.String(50),
        nullable=False
    )

    days = db.Column(
        db.Integer,
        nullable=False
    )

    amount = db.Column(
        db.Float,
        nullable=False
    )
    # rupees

    amount_paise = db.Column(
        db.Integer,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default='CREATED'
    )
    # CREATED, PAID

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    paid_at = db.Column(
        db.DateTime
    )

    def __repr__(self):
        return f'<SubscriptionOrder {self.razorpay_order_id} {self.status}>'
