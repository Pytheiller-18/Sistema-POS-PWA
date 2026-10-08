import uuid
from datetime import datetime, timezone
from app.extensions import db

class Sale(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    client_sync_id = db.Column(db.String(64), nullable=False) # Clave de idempotencia offline
    invoice_number = db.Column(db.String(30), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    tax = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    discount = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    payment_method = db.Column(db.String(20), nullable=False, default='CASH') # CASH, CARD, TRANSFER, OTHER
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    change_due = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    sync_status = db.Column(db.String(20), nullable=False, default='ONLINE') # ONLINE, SYNCED_OFFLINE
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'client_sync_id', name='uk_tenant_client_sync'),
    )

    items = db.relationship('SaleItem', backref='sale', lazy='joined', cascade='all, delete-orphan')
    user = db.relationship('User', backref='sales', lazy='joined')

    def to_dict(self, include_items=True):
        data = {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'user_id': self.user_id,
            'cashier_name': self.user.full_name if self.user else 'Cajero',
            'client_sync_id': self.client_sync_id,
            'invoice_number': self.invoice_number,
            'subtotal': float(self.subtotal or 0.0),
            'tax': float(self.tax or 0.0),
            'discount': float(self.discount or 0.0),
            'total': float(self.total or 0.0),
            'payment_method': self.payment_method,
            'amount_paid': float(self.amount_paid or 0.0),
            'change_due': float(self.change_due or 0.0),
            'sync_status': self.sync_status,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_items:
            data['items'] = [item.to_dict() for item in self.items]
            data['items_count'] = sum(item.quantity for item in self.items)
        return data

class SaleItem(db.Model):
    __tablename__ = 'sale_items'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    sale_id = db.Column(db.String(36), db.ForeignKey('sales.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.String(36), db.ForeignKey('products.id'), nullable=False, index=True)
    product_name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)

    product = db.relationship('Product', backref='sale_items', lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'unit_cost': float(self.unit_cost or 0.0),
            'unit_price': float(self.unit_price or 0.0),
            'subtotal': float(self.subtotal or 0.0),
            'total': float(self.total or 0.0)
        }
