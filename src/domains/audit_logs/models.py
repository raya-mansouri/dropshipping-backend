"""
Audit Logs Domain Models
========================
Entity change audit trail
"""

from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """
    Audit log

    Tracks all entity changes for compliance and debugging
    """

    __tablename__ = "audit_logs"

    entity_type = Column(String(50), nullable=False)  # order, product, shop, payment
    entity_id = Column(UUID(as_uuid=True), nullable=False)

    action = Column(String(50), nullable=False)  # created, updated, deleted, status_changed
    actor_type = Column(String(20), nullable=False)  # user, system, admin
    actor_id = Column(UUID(as_uuid=True))

    old_value = Column(JSONB, default=dict)
    new_value = Column(JSONB, default=dict)
    reason = Column(String(500))

    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_audit_logs_entity", "entity_type", "entity_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_actor", "actor_type", "actor_id"),
        Index("idx_audit_logs_created", "created_at"),
    )
