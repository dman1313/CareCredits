from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models.account import Account
from models.profile import AccountProfile
from models.audit import AuditLog


AUDIT_HIDDEN = {"notes", "password", "password_hash", "token", "secret", "api_key"}


class UserRepository:
    """
    Sole owner of user-centric operations across Account + AccountProfile.
    Handles the join logic internally; callers never see raw tables.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_profile(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Joins Account + AccountProfile to return unified profile."""
        result = (
            self.db.query(Account, AccountProfile)
            .outerjoin(AccountProfile, Account.id == AccountProfile.account_id)
            .filter(Account.id == account_id)
            .first()
        )
        if not result or not result[0]:
            return None
        
        account, profile = result
        data = {
            "id": account.id,
            "email": account.email,
            "is_active": account.is_active,
        }
        
        if profile:
            data.update({
                "name": profile.name,
                "role": profile.role,
                "city": profile.city,
                "bio": profile.bio,
                "public_enabled": profile.public_enabled,
                "public_slug": profile.public_slug,
                "latitude": getattr(profile, "latitude", None),
                "longitude": getattr(profile, "longitude", None),
                "location_consent_at": getattr(profile, "location_consent_at", None),
                "created_at": getattr(account, "created_at", None),
            })
        else:
            data.update({
                "name": "", "role": None, "city": "Kuala Lumpur", 
                "bio": "", "public_enabled": False, "public_slug": None,
                "latitude": None, "longitude": None, 
                "location_consent_at": None, "created_at": None,
            })
        return data

    def update_profile(self, account_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates AccountProfile and creates audit log atomically."""
        profile = (
            self.db.query(AccountProfile)
            .filter_by(account_id=account_id)
            .first()
        )
        if not profile:
            raise ValueError("User profile not found.")
        
        profile_fields = {k: v for k, v in updates.items() 
                         if hasattr(AccountProfile, k)}
        for key, value in profile_fields.items():
            setattr(profile, key, value)
        
        self.db.add(AuditLog(
            account_id=account_id,
            action="profile_changed",
            entity_id=account_id,
            changed={"public_enabled": updates.get("public_enabled")}
        ))
        return self.get_profile(account_id)


    def get_audit_paginated(
        self, account_id: str, page: int, page_size: int
    ) -> Dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 50:
            raise ValueError("Invalid pagination parameters.")
        
        query = self.db.query(AuditLog).filter_by(account_id=account_id)
        total = query.count()
        rows = (
            query.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [self._serialize_audit(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _serialize_audit(row: AuditLog) -> Dict[str, Any]:
        changed = row.changed if isinstance(row.changed, dict) else {}
        return {
            "id": row.id,
            "action": row.action,
            "entity_id": row.entity_id,
            "changed": {k: v for k, v in changed.items() if k not in AUDIT_HIDDEN},
            "at": row.created_at,
        }