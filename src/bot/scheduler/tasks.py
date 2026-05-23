from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import texts
from ..config import Settings
from ..database.models import Payment, PaymentStatus
from ..database.repository import SubscriptionRepository
from ..database.session import SessionFactory, open_session
from ..logger import log
from ..services.channel import ChannelService
from ..services.subscription import SubscriptionService


class SchedulerService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        bot: Bot,
        channel: ChannelService,
        subscriptions: SubscriptionService,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.bot = bot
        self.channel = channel
        self.subscriptions = subscriptions
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        self.scheduler.add_job(
            self._send_reminders, "interval", minutes=30, id="reminders",
            replace_existing=True, coalesce=True, max_instances=1,
        )
        self.scheduler.add_job(
            self._kick_expired, "interval", minutes=15, id="kick_expired",
            replace_existing=True, coalesce=True, max_instances=1,
        )
        if not self.settings.webhook_enabled:
            self.scheduler.add_job(
                self._poll_pending_invoices,
                "interval",
                seconds=self.settings.poll_interval_seconds,
                id="poll_invoices",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )
        self.scheduler.start()
        log.info("scheduler.started", jobs=[j.id for j in self.scheduler.get_jobs()])

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    # ── jobs ─────────────────────────────────────────────────────────────────
    async def _send_reminders(self) -> None:
        async with open_session(self.session_factory) as session:
            await self._send_reminders_inner(session)

    async def _send_reminders_inner(self, session: AsyncSession) -> None:
        subs_repo = SubscriptionRepository(session)
        now = datetime.now(UTC)
        sorted_days = sorted(self.settings.reminder_days, reverse=True)
        for idx, day in enumerate(sorted_days):
            next_smaller = sorted_days[idx + 1] if idx + 1 < len(sorted_days) else 0
            expiring = await subs_repo.list_expiring(day)
            for sub in expiring:
                if day in sub.notified_days():
                    continue
                seconds_left = (sub.expires_at - now).total_seconds()
# Если вложенный текст уже находится в меньшем окне напоминания, позвольте
# этой итерации отобразить его — в противном случае мы бы использовали неправильную копию.
                if seconds_left <= next_smaller * 86400:
                    continue
                template = (
                    texts.REMINDER_LAST_DAY if day <= 1 else texts.REMINDER_BEFORE
                )
                body = template.format(
                    days=day,
                    until=sub.expires_at.strftime("%d.%m.%Y %H:%M UTC"),
                )
                if await self._notify(sub.user_id, body):
                    sub.mark_notified(day)

    async def _kick_expired(self) -> None:
        async with open_session(self.session_factory) as session:
            subs_repo = SubscriptionRepository(session)
            expired = await subs_repo.list_expired()
            for sub in expired:
                ok = await self.channel.remove_member(sub.user_id)
                if ok:
                    sub.kicked_at = datetime.now(UTC)
                    await self._notify(sub.user_id, texts.SUBSCRIPTION_ENDED)
                else:
                    log.warning("scheduler.kick_skipped", user_id=sub.user_id)

    async def _poll_pending_invoices(self) -> None:
        async with open_session(self.session_factory) as session:
            pending = await session.scalars(
                select(Payment).where(Payment.status == PaymentStatus.pending).limit(50)
            )
            for payment in pending.all():
                if not payment.invoice_id:
                    continue
                try:
                    await self.subscriptions.reconcile_invoice(session, payment.invoice_id)
                except Exception:
                    log.exception(
                        "scheduler.poll_failed", invoice_id=payment.invoice_id
                    )

    async def _notify(self, user_id: int, text: str) -> bool:
        try:
            await self.bot.send_message(user_id, text, disable_web_page_preview=True)
            return True
        except TelegramAPIError as exc:
            log.warning("scheduler.notify_failed", user_id=user_id, error=str(exc))
            return False


