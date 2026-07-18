from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.db.models import Permission, Role, RolePermission
from fincore.domain.permissions import PERMISSIONS, ROLE_PERMISSIONS


def ensure_rbac(db: Session) -> None:
    permissions: dict[str, Permission] = {}
    for code in sorted(PERMISSIONS):
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code, description=code.replace(".", " ").title())
            db.add(permission)
            db.flush()
        permissions[code] = permission
    for name, codes in ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name, description=name.replace("_", " ").title())
            db.add(role)
            db.flush()
        existing = set(
            db.scalars(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            ).all()
        )
        for code in codes - existing:
            db.add(RolePermission(role_id=role.id, permission_id=permissions[code].id))
    db.flush()
