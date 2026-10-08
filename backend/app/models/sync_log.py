import uuid
from datetime import datetime, timezone
from app.extensions import db

class SyncAuditLog(db.Model):
    __tablename__ = 'sync_audit_log'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    client_sync_id = db.Column(db.String(64), nullable=False)
    device_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False) # SUCCESS, ALREADY_SYNCED, CONFLICT, ERROR
    details = db.Column(db.Text, nullable=True)
    synced_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'client_sync_id': self.client_sync_id,
            'device_id': self.device_id,
            'status': self.status,
            'details': self.details,
            'synced_at': self.synced_at.isoformat() if self.synced_at else None
        }
