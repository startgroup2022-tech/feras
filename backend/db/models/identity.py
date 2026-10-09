"""Identity, role, permission and company-access models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    CompanyHealth,
    CompanyStatus,
    CompanyType,
    RoleCode,
)

if TYPE_CHECKING:
    from backend.db.models.ai import AIConversation
    from backend.db.models.report import MonthlyReport
    from backend.db.models.support import SupportRequest


class Role(Base, TimestampMixin):
    """A named role (the six V1 roles)."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    # ``description`` holds the English text for backwards compatibility; the
    # Arabic counterpart is stored separately so the admin UI can switch
    # languages without a reload.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)

    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles", lazy="selectin"
    )
    users: Mapped[list["User"]] = relationship(back_populates="role")


class Permission(Base, TimestampMixin):
    """A single granular capability, e.g. ``monthly_report.submit``."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    roles: Mapped[list[Role]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )


class RolePermission(Base):
    """Join table granting permissions to roles."""

    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class Company(Base, TimestampMixin):
    """A subsidiary company belonging to the Holding."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(180), nullable=False)
    name_en: Mapped[str] = mapped_column(String(180), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CompanyStatus.ACTIVE.value, index=True
    )
    health: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CompanyHealth.STABLE.value
    )
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ---- Phase 2 administrative fields (all nullable / additive) ----
    legal_name_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    legal_name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=CompanyType.SUBSIDIARY.value
    )
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    commercial_registration: Mapped[str | None] = mapped_column(String(80), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    users: Mapped[list["UserCompanyAccess"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    monthly_reports: Mapped[list["MonthlyReport"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    support_requests: Mapped[list["SupportRequest"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    ai_conversations: Mapped[list["AIConversation"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class User(Base, TimestampMixin):
    """A platform user. Exactly one role per user in V1."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    full_name_ar: Mapped[str] = mapped_column(String(180), nullable=False)
    full_name_en: Mapped[str | None] = mapped_column(String(180), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Optional home department. Company-scoped by construction: the department
    # itself carries the company, so assigning a user to a department also
    # implies the company context for display purposes.
    # ``use_alter`` breaks the users<->departments FK cycle so Alembic can order
    # the CREATE TABLE statements deterministically.
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "departments.id", ondelete="SET NULL", use_alter=True, name="fk_users_department"
        ),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    role: Mapped[Role] = relationship(back_populates="users", lazy="joined")
    company_access: Mapped[list["UserCompanyAccess"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def role_code(self) -> str:
        return self.role.code if self.role else ""

    @property
    def permitted_company_ids(self) -> list[int]:
        """Company ids this user may read.

        Holding Owner (and superusers) are unscoped and represented by an empty
        list combined with :attr:`is_holding_wide`.
        """
        return [a.company_id for a in self.company_access if a.can_read]

    @property
    def is_holding_wide(self) -> bool:
        return self.is_superuser or self.role_code == RoleCode.HOLDING_OWNER.value


class UserCompanyAccess(Base, TimestampMixin):
    """Explicit grant of a user to a company, with per-company flags.

    This is the backbone of company data isolation: a user can only reach a
    company that appears here (or is a holding-wide role).
    """

    __tablename__ = "user_company_access"
    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_company_access_pair"),
        Index("ix_user_company_access_company", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    can_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="company_access")
    company: Mapped[Company] = relationship(back_populates="users")
