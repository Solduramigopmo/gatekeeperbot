from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PaymentStatus(enum.StrEnum):
    pending = "pending"
    paid = "paid"
    cancelled = "cancelled"
    expired = "expired"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_banned: Mapped[bool] = mapped_column(default=False, nullable=False)

    subscription: Mapped[Subscription | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    plan_id: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notified_at_days: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    kicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="subscription")

    __table_args__ = (Index("ix_subscriptions_expires_at", "expires_at"),)

    def notified_days(self) -> set[int]:
        return {int(x) for x in self.notified_at_days.split(",") if x.strip()}

    def mark_notified(self, day: int) -> None:
        current = self.notified_days()
        current.add(day)
        self.notified_at_days = ",".join(str(d) for d in sorted(current, reverse=True))


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[str] = mapped_column(String(32), nullable=False)
    asset: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    invoice_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        default=PaymentStatus.pending,
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped[User] = relationship(back_populates="payments")


class PriceOverride(Base):
    """Переопределение цены для каждого тарифного плана задается в панели администратора.

  Название и продолжительность тарифного плана всегда указываются в конфигурации; только цена
  может быть изменена во время выполнения, поэтому существующие платежи сохраняют свою первоначальную сумму,
  в то время как в новых счетах используется переопределенное значение.
  """

    __tablename__ = "price_overrides"

    plan_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
