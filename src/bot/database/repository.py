from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Payment, PaymentStatus, Subscription, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def upsert(
        self,
        user_id: int,
        *,
        username: str | None,
        first_name: str | None,
        language_code: str | None,
    ) -> User:
        user = await self.get(user_id)
        if user is None:
            user = User(
                id=user_id,
                username=username,
                first_name=first_name,
                language_code=language_code,
            )
            self.session.add(user)
            await self.session.flush()
            return user

        changed = False
        if user.username != username:
            user.username = username
            changed = True
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if user.language_code != language_code:
            user.language_code = language_code
            changed = True
        if changed:
            await self.session.flush()
        return user

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(User.id))) or 0)


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_user(self, user_id: int) -> Subscription | None:
        return await self.session.scalar(
            select(Subscription).where(Subscription.user_id == user_id)
        )

    async def upsert_extension(
        self,
        user_id: int,
        plan_id: str,
        days: int,
    ) -> tuple[Subscription, bool]:
        """Либо создает новую подписку, либо расширяет существующую.

        Возвращает `(подписка, was_extension)``.
        """
        now = datetime.now(UTC)
        subscription = await self.get_for_user(user_id)
        extension = subscription is not None and subscription.expires_at > now

        if subscription is None:
            subscription = Subscription(
                user_id=user_id,
                plan_id=plan_id,
                expires_at=now + timedelta(days=days),
            )
            self.session.add(subscription)
        else:
            base = subscription.expires_at if subscription.expires_at > now else now
            subscription.expires_at = base + timedelta(days=days)
            subscription.plan_id = plan_id
            subscription.notified_at_days = ""
            subscription.kicked_at = None

        await self.session.flush()
        return subscription, extension

    async def list_expiring(self, within_days: int) -> Sequence[Subscription]:
        now = datetime.now(UTC)
        upper = now + timedelta(days=within_days, hours=1)
        result = await self.session.scalars(
            select(Subscription).where(
                Subscription.expires_at > now,
                Subscription.expires_at <= upper,
            )
        )
        return result.all()

    async def list_expired(self) -> Sequence[Subscription]:
        now = datetime.now(UTC)
        result = await self.session.scalars(
            select(Subscription).where(
                Subscription.expires_at <= now,
                Subscription.kicked_at.is_(None),
            )
        )
        return result.all()

    async def count_active(self) -> int:
        now = datetime.now(UTC)
        return int(
            await self.session.scalar(
                select(func.count(Subscription.id)).where(Subscription.expires_at > now)
            )
            or 0
        )

    async def recent(self, limit: int = 20) -> Sequence[Subscription]:
        result = await self.session.scalars(
            select(Subscription).order_by(Subscription.updated_at.desc()).limit(limit)
        )
        return result.all()


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_pending(
        self,
        *,
        user_id: int,
        plan_id: str,
        asset: str,
        amount: Decimal,
        invoice_id: int,
        payload: str | None,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            plan_id=plan_id,
            asset=asset,
            amount=amount,
            invoice_id=invoice_id,
            payload=payload,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_invoice(self, invoice_id: int) -> Payment | None:
        return await self.session.scalar(
            select(Payment).where(Payment.invoice_id == invoice_id)
        )

    async def mark_paid(self, payment: Payment) -> None:
        payment.status = PaymentStatus.paid
        payment.paid_at = datetime.now(UTC)
        await self.session.flush()

    async def mark_status(self, payment: Payment, status: PaymentStatus) -> None:
        payment.status = status
        await self.session.flush()

    async def count_paid(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count(Payment.id)).where(Payment.status == PaymentStatus.paid)
            )
            or 0
        )

    async def count_paid_since(self, since: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count(Payment.id)).where(
                    Payment.status == PaymentStatus.paid,
                    Payment.paid_at >= since,
                )
            )
            or 0
        )

    async def revenue_by_asset(self) -> dict[str, Decimal]:
        rows = await self.session.execute(
            select(Payment.asset, func.sum(Payment.amount)).where(
                Payment.status == PaymentStatus.paid
            ).group_by(Payment.asset)
        )
        return {asset: Decimal(amount or 0) for asset, amount in rows.all()}

    async def stats_by_plan(self) -> list[tuple[str, int, str, Decimal]]:
        rows = await self.session.execute(
            select(
                Payment.plan_id,
                Payment.asset,
                func.count(Payment.id),
                func.sum(Payment.amount),
            )
            .where(Payment.status == PaymentStatus.paid)
            .group_by(Payment.plan_id, Payment.asset)
            .order_by(Payment.plan_id)
        )
        return [
            (plan_id, int(count), asset, Decimal(total or 0))
            for plan_id, asset, count, total in rows.all()
        ]
