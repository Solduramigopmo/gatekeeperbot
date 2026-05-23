from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_settings
from .database import create_engine_and_session, dispose_engine
from .handlers import register_routers
from .logger import log, setup_logging
from .middlewares import DatabaseMiddleware, ThrottlingMiddleware
from .scheduler import SchedulerService
from .services import ChannelService, CryptoPay, PricingService, SubscriptionService
from .web import build_webhook_app, run_webhook_server


async def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    log.info("bot.starting", channel_id=settings.channel_id, plans=len(settings.subscription_plans))

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    engine, session_factory = await create_engine_and_session(
        settings.database_url, create_tables=True
    )

    crypto = CryptoPay(settings.crypto_pay_token, base_url=str(settings.crypto_pay_base_url))
    channel = ChannelService(bot, settings.channel_id)
    pricing = PricingService(settings)
    subscriptions = SubscriptionService(settings=settings, crypto=crypto, channel=channel)
    scheduler = SchedulerService(
        settings=settings,
        session_factory=session_factory,
        bot=bot,
        channel=channel,
        subscriptions=subscriptions,
    )

    dp.update.middleware(ThrottlingMiddleware(settings))
    dp.update.middleware(DatabaseMiddleware(session_factory))
    register_routers(dp)

    workflow: dict[str, Any] = {
        "settings": settings,
        "subscriptions": subscriptions,
        "pricing": pricing,
        "channel": channel,
        "scheduler": scheduler,
    }

    webhook_runner = None
    if settings.webhook_enabled:
        app = build_webhook_app(
            token=settings.crypto_pay_token,
            path=settings.webhook_path,
            handler=lambda payload: _on_webhook_payment(payload, session_factory, subscriptions, bot),
        )
        webhook_runner, _ = await run_webhook_server(
            app, host=settings.webhook_host, port=settings.webhook_port
        )

    scheduler.start()

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            **workflow,
        )
    finally:
        log.info("bot.stopping")
        await scheduler.shutdown()
        if webhook_runner is not None:
            with contextlib.suppress(Exception):
                await webhook_runner.cleanup()
        await crypto.close()
        await bot.session.close()
        await dispose_engine(engine)


async def _on_webhook_payment(
    payload: dict[str, Any],
    session_factory,
    subscriptions: SubscriptionService,
    bot: Bot,
) -> None:
    from . import texts
    from .database.session import open_session

    invoice_id = int(payload.get("invoice_id", 0) or 0)
    if not invoice_id:
        return
    async with open_session(session_factory) as session:
        result = await subscriptions.activate_paid_invoice(session, invoice_id)
        if result is None:
            return
        if result.was_extension:
            body = texts.PAYMENT_RECEIVED_EXTENDED.format(
                until=result.subscription.expires_at.strftime("%d.%m.%Y %H:%M UTC")
            )
        elif result.invite_link:
            body = texts.PAYMENT_RECEIVED.format(
                until=result.subscription.expires_at.strftime("%d.%m.%Y %H:%M UTC"),
                link=result.invite_link,
            )
        else:
            body = texts.INVITE_LINK_FAILED
        try:
            await bot.send_message(
                result.payment.user_id, body, disable_web_page_preview=True
            )
        except Exception:
            log.exception("webhook.notify_failed", user_id=result.payment.user_id)


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        log.info("bot.interrupted")


if __name__ == "__main__":
    main()
