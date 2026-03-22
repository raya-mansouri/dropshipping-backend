"""
Accounts Domain Models
=====================
User accounts, roles, and authentication
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid


class User(Base, UUIDMixin, TimestampMixin):
    """System users"""
    __tablename__ = "users"
    
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    role = Column(String(20), default="user")  # user, admin, super_admin
    
    # Relationships
    accounts = relationship("Account", back_populates="owner")
    notifications = relationship("Notification", back_populates="user")


class Account(Base, UUIDMixin, TimestampMixin):
    """
    Account - can be supplier, seller, or hybrid
    
    A user can have multiple accounts (e.g., a supplier who also sells)
    """
    __tablename__ = "accounts"
    
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    account_type = Column(String(20), nullable=False)  # supplier, seller, hybrid
    business_name = Column(String(255))
    business_id = Column(String(50))  # Business registration number
    status = Column(String(20), default="active")  # active, suspended, closed
    
    # Relationships
    owner = relationship("User", back_populates="accounts")
    shops = relationship("Shop", back_populates="account")


# Association table for account roles
account_roles = Table(
    'account_roles',
    Base.metadata,
    Column('account_id', UUID(as_uuid=True), ForeignKey('accounts.id')),
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id'))
)


class Role(Base, UUIDMixin, TimestampMixin):
    """Roles for access control"""
    __tablename__ = "roles"
    
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    permissions = Column(JSONB, default=list)  # List of permission strings
    
    # Relationships
    users = relationship("User", secondary="user_roles", back_populates="roles")


class UserRole(Base, UUIDMixin, TimestampMixin):
    """User-Role association"""
    __tablename__ = "user_roles"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)


# Add relationship to User
User.roles = relationship("Role", secondary="user_roles", back_populates="users")
