import uuid
from datetime import datetime, timezone
from app.extensions import db

class Tenant(db.Model):
    __tablename__ = 'tenants'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_name = db.Column(db.String(150), nullable=False)
    tax_id = db.Column(db.String(50), nullable=True) # NIT / RUC / RFC / CIF
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    currency_symbol = db.Column(db.String(5), nullable=False, default='$')
    status = db.Column(db.String(20), nullable=False, default='ACTIVE')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones
    users = db.relationship('User', backref='tenant', lazy='dynamic', cascade='all, delete-orphan')
    products = db.relationship('Product', backref='tenant', lazy='dynamic', cascade='all, delete-orphan')
    sales = db.relationship('Sale', backref='tenant', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'business_name': self.business_name,
            'tax_id': self.tax_id,
            'phone': self.phone,
            'email': self.email,
            'address': self.address,
            'currency_symbol': self.currency_symbol,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
