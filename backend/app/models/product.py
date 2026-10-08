import uuid
from datetime import datetime, timezone
from app.extensions import db

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    products = db.relationship('Product', backref='category', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    category_id = db.Column(db.String(36), db.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True, index=True)
    barcode = db.Column(db.String(64), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    sale_price = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    stock = db.Column(db.Integer, nullable=False, default=0)
    min_stock = db.Column(db.Integer, nullable=False, default=5)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('idx_products_tenant_active', 'tenant_id', 'is_active'),
        db.Index('idx_products_barcode', 'tenant_id', 'barcode'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else 'General',
            'barcode': self.barcode,
            'name': self.name,
            'cost_price': float(self.cost_price or 0.0),
            'sale_price': float(self.sale_price or 0.0),
            'stock': self.stock,
            'min_stock': self.min_stock,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
