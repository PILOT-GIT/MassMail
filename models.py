from datetime import datetime
from typing import List, Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(255))
    # role: owner | admin | user | unauthorized
    role: Mapped[str] = mapped_column(String(50), default="unauthorized", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    gmail_accounts: Mapped[List["GmailAccount"]] = relationship(
        "GmailAccount", back_populates="user", cascade="all, delete-orphan"
    )
    target_lists: Mapped[List["TargetList"]] = relationship(
        "TargetList", back_populates="user", cascade="all, delete-orphan"
    )
    operations: Mapped[List["Operation"]] = relationship(
        "Operation", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_authorized(self) -> bool:
        return self.role in ("owner", "admin", "user")

    @property
    def is_admin_or_above(self) -> bool:
        return self.role in ("owner", "admin")

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="gmail_accounts")
    operation_senders: Mapped[List["OperationSender"]] = relationship(
        "OperationSender", back_populates="gmail_account", cascade="all, delete-orphan"
    )
    sends: Mapped[List["OperationSend"]] = relationship(
        "OperationSend", back_populates="gmail_account", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("user_id", "email", name="uq_user_gmail_email"),)


class TargetList(Base):
    __tablename__ = "target_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="target_lists")
    emails: Mapped[List["TargetEmail"]] = relationship(
        "TargetEmail", back_populates="target_list", cascade="all, delete-orphan"
    )
    operations: Mapped[List["Operation"]] = relationship("Operation", back_populates="target_list")


class TargetEmail(Base):
    __tablename__ = "target_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_lists.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    target_list: Mapped["TargetList"] = relationship("TargetList", back_populates="emails")
    sends: Mapped[List["OperationSend"]] = relationship(
        "OperationSend", back_populates="target_email", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("list_id", "email", name="uq_list_email"),)


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    list_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_lists.id", ondelete="RESTRICT"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # status: pending | sending | completed | failed
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    delay_min: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    delay_max: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="operations")
    target_list: Mapped["TargetList"] = relationship("TargetList", back_populates="operations")
    senders: Mapped[List["OperationSender"]] = relationship(
        "OperationSender", back_populates="operation", cascade="all, delete-orphan"
    )
    sends: Mapped[List["OperationSend"]] = relationship(
        "OperationSend", back_populates="operation", cascade="all, delete-orphan"
    )


class OperationSender(Base):
    """Which Gmail accounts are used as senders for this operation."""
    __tablename__ = "operation_senders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("operations.id", ondelete="CASCADE"), nullable=False
    )
    gmail_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gmail_accounts.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    operation: Mapped["Operation"] = relationship("Operation", back_populates="senders")
    gmail_account: Mapped["GmailAccount"] = relationship("GmailAccount", back_populates="operation_senders")

    __table_args__ = (UniqueConstraint("operation_id", "gmail_account_id", name="uq_operation_sender"),)


class OperationSend(Base):
    """One row per (target_email × gmail_account) send attempt."""
    __tablename__ = "operation_sends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("operations.id", ondelete="CASCADE"), nullable=False
    )
    target_email_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_emails.id", ondelete="CASCADE"), nullable=False
    )
    gmail_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gmail_accounts.id", ondelete="CASCADE"), nullable=False
    )
    # status: pending | sent | failed
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    operation: Mapped["Operation"] = relationship("Operation", back_populates="sends")
    target_email: Mapped["TargetEmail"] = relationship("TargetEmail", back_populates="sends")
    gmail_account: Mapped["GmailAccount"] = relationship("GmailAccount", back_populates="sends")

    __table_args__ = (
        UniqueConstraint(
            "operation_id", "target_email_id", "gmail_account_id", name="uq_operation_send"
        ),
    )
