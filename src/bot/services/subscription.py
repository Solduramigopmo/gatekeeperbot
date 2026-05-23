from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Plan, Settings
from ..database.models import Payment, PaymentStatus, Subscription
from ..database.repository import PaymentRepository, SubscriptionRepository, UserRepository
from ..logger import log
from .channel import ChannelService
from .cryptobot import CryptoPay, Invoice


@dataclass(slots=True)
class CheckoutResult:
    payment: Payment
    invoice: Invoice
    plan: Plan


@dataclass(slots=True)
class ActivationResult:
    subscription: Subscription
    payment: Payment
    invite_link: str | None
    was_extension: bool


def _new_payload() -> str:
    return secrets.token_urlsafe(16)


class SubscriptionService:
"""Координирует Crypto Pay, базу данных и сервис каналов.

 Все, что касается денежных потоков, проходит здесь, так что обработчики остаются
неизменными и та же логика повторно используется webhook и
средством согласования опросов.
 """

    def __init__(
        self,
        *,
        settings: Settings,
        crypto: CryptoPay,
        channel: ChannelService,
    ) -> None:
        self.settings = settings
        self.crypto = crypto
        self.channel = channel

    # ── checkout ─────────────────────────────────────────────────────────────
    async def create_checkout(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        plan: Plan,
        asset: str,
    ) -> CheckoutResult:
        if self.settings.plan_by_id(plan.id) is None:
            raise ValueError(f"unknown plan: {plan.id}")
        asset = asset.upper()
        if asset not in self.settings.crypto_pay_assets:
            raise ValueError(f"unsupported asset: {asset}")

        payload = _new_payload()
        amount = self._amount_for(plan, asset)
        description = f"{plan.title} — доступ в закрытый канал"

        invoice = await self.crypto.create_invoice(
            asset=asset,
            amount=amount,
            description=description,
            payload=payload,
            hidden_message="Подписка активирована. Ссылка на канал придёт в боте.",
            expires_in=1800,
            allow_anonymous=False,
        )

        payments = PaymentRepository(session)
        payment = await payments.create_pending(
            user_id=user_id,
            plan_id=plan.id,
            asset=asset,
            amount=amount,
            invoice_id=invoice.invoice_id,
            payload=payload,
        )
        log.info(
            "subscription.checkout_created",
            user_id=user_id,
            plan_id=plan.id,
            asset=asset,
            invoice_id=invoice.invoice_id,
        )
        return CheckoutResult(payment=payment, invoice=invoice, plan=plan)

    def _amount_for(self, plan: Plan, asset: str) -> Decimal:
        # Currently the same nominal price is used for every supported asset.
        # If you ever want to charge a different amount per asset, replace this
        # with a lookup into a per-asset price map.
        del asset
        return plan.price

    # ── activation ───────────────────────────────────────────────────────────
    async def activate_paid_invoice(
        self,
        session: AsyncSession,
        invoice_id: int,
        *,
        paid_at: datetime | None = None,
    ) -> ActivationResult | None:
        payments = PaymentRepository(session)
        payment = await payments.get_by_invoice(invoice_id)
        if payment is None:
            log.warning("subscription.activation.unknown_invoice", invoice_id=invoice_id)
            return None
        if payment.status == PaymentStatus.paid:
            return None  # idempotency — already processed

        plan = self.settings.plan_by_id(payment.plan_id)
        if plan is None:
            log.error("subscription.activation.missing_plan", plan_id=payment.plan_id)
            return None

        payment.paid_at = paid_at or datetime.now(UTC)
        await payments.mark_paid(payment)

        subs = SubscriptionRepository(session)
        subscription, was_extension = await subs.upsert_extension(
            user_id=payment.user_id,
            plan_id=plan.id,
            days=plan.days,
        )

        invite_link: str | None = None
        if not was_extension:
            try:
                invite_link = await self.channel.create_one_time_invite(
                    name=f"sub:{payment.user_id}"
                )
            except Exception:
                log.exception(
                    "subscription.invite_link.failed", user_id=payment.user_id
                )
                invite_link = None

        log.info(
            "subscription.activated",
            user_id=payment.user_id,
            plan_id=plan.id,
            extension=was_extension,
            expires_at=subscription.expires_at.isoformat(),
        )
        return ActivationResult(
            subscription=subscription,
            payment=payment,
            invite_link=invite_link,
            was_extension=was_extension,
        )

    # ── reconciler ───────────────────────────────────────────────────────────
    async def reconcile_invoice(
        self, session: AsyncSession, invoice_id: int
    ) -> ActivationResult | None:
        """Pulls an invoice from Crypto Pay and applies its status locally.

        Used both by the manual "check payment" button and by the polling job
        when no webhook is configured.
        """
        invoice = await self.crypto.get_invoice(invoice_id)
        if invoice is None:
            return None
        if invoice.is_paid:
            return await self.activate_paid_invoice(
                session, invoice.invoice_id, paid_at=invoice.paid_at
            )
        if invoice.status in {"expired", "cancelled"}:
            payments = PaymentRepository(session)
            payment = await payments.get_by_invoice(invoice.invoice_id)
            if payment and payment.status == PaymentStatus.pending:
                await payments.mark_status(
                    payment,
                    PaymentStatus.expired if invoice.status == "expired" else PaymentStatus.cancelled,
                )
        return None

    # ── user-facing helpers used by handlers ─────────────────────────────────
    async def ensure_user(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        username: str | None,
        first_name: str | None,
        language_code: str | None,
    ) -> None:
        await UserRepository(session).upsert(
            user_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
        )
