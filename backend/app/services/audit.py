from fastapi import Request
from sqlalchemy.orm import Session

from app.core.rate_limit import client_ip
from app.models import AuditLog


def audit(
    db: Session,
    action: str,
    entity: str,
    entity_id: object | None = None,
    user_id: int | None = None,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    """Record a sensitive action. Added to the current transaction (commit with the change)."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details or {},
            ip_address=client_ip(request) if request else None,
        )
    )
