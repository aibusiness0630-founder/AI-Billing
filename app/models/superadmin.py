from datetime import datetime
from app import db


class SuperAdmin(db.Model):
    """ANFIA owner account. Completely separate from shop logins."""
    __tablename__ = 'super_admin'

    id = db.Column(db.Integer, primary_key=True)

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

    last_login = db.Column(
        db.DateTime
    )

    def __repr__(self):
        return f'<SuperAdmin {self.username}>'
