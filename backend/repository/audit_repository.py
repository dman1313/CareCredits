from typing import Dict, Any
from sqlalchemy.orm import Session
from models.audit import AuditLog


AUDIT_HIDDEN = {"notes", "password", "password_hash", "token", "secret", "api_key"}


class AuditRepository:
    """
    Sole owner of portal_audit table operations.
    NEVER imports or queries other models. 
    Cross-model data must be provided by caller or separate repositories.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_paginated(
        self, page: int, page_size: int, account_id: str | None = None
    ) -> Dict[str, Any]:
        """
        Returns paginated audit entries.
        If account_id is provided, filters to that user only.
        Validation lives here because it's intrinsic to safe data access.
        """
        if page < 1 or not 1 <= page_size <= 50:
            raise ValueError("Invalid pagination parameters.")

        query = self.db.query(AuditLog)
        if account_id:
            query = query.filter_by(account_id=account_id)

        total = query.count()
        rows = (
            query.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [self._serialize(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _serialize(row: AuditLog) -> Dict[str, Any]:
        """Sanitizes sensitive fields before returning."""
        changed = row.changed if isinstance(row.changed, dict) else {}
        return {
            "id": row.id,
            "action": row.action,
            "entity_id": row.entity_id,
            "changed": {k: v for k, v in changed.items() if k not in AUDIT_HIDDEN},
            "at": row.created_at,
        }