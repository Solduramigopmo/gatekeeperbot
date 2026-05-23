from __future__ import annotations

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from .. import texts
from ..config import Settings
from ..database.repository import SubscriptionRepository
from ..keyboards.callbacks import BuyAsset, BuyPlan, Menu
from ..keyboards.user import assets_keyboard, back_to_menu, invoice_keyboard, plans_keyboard
from ..services.pricing import PricingService
from ..services.subscription import SubscriptionService

router = Router(name="подписка")


@router.callback_query(Menu.filter(F.action == "купить"))
async def show_plans(
    call: CallbackQuery,
    session: AsyncSession,
    pricing: PricingService,
) -> None:
    if call.message is None:
        await call.answer()
        return
    plans = await pricing.effective_plans(session)
    await _safe_edit(call, texts.CHOOSE_PLAN, plans_keyboard(plans))
    await call.answer()


@router.callback_query(BuyPlan.filter())
async def choose_asset(
    call: CallbackQuery,
    callback_data: BuyPlan,
    session: AsyncSession,
    settings: Settings,
    pricing: PricingService,
) -> None:
    plan = await pricing.effective_plan(session, callback_data.plan_id)
    if plan is None or call.message is None:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        return
    asset_for_display = "USDT" if "USDT" in settings.crypto_pay_assets else settings.crypto_pay_assets[0]
    price = texts.format_amount(plan.price, asset_for_display)
    body = texts.CHOOSE_ASSET.format(title=plan.title, days=plan.days, price=price)
    await _safe_edit(call, body, assets_keyboard(plan.id, settings.crypto_pay_assets))
    await call.answer()


@router.callback_query(BuyAsset.filter())
async def create_invoice(
    call: CallbackQuery,
    callback_data: BuyAsset,
    session: AsyncSession,
    settings: Settings,
    pricing: PricingService,
    subscriptions: SubscriptionService,
) -> None:
    if call.message is None or call.from_user is None:
        await call.answer()
        return
    plan = await pricing.effective_plan(session, callback_data.plan_id)
    if plan is None or callback_data.asset not in settings.crypto_pay_assets:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        return

    try:
        result = await subscriptions.create_checkout(
            session,
            user_id=call.from_user.id,
            plan=plan,
            asset=callback_data.asset,
        )
    except Exception:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        raise

    amount_str = texts.format_amount(result.invoice.amount, result.invoice.asset).rsplit(" ", 1)[0]
    body = texts.INVOICE_CREATED.format(
        title=plan.title,
        days=plan.days,
        amount=amount_str,
        asset=result.invoice.asset,
    )
    kb = invoice_keyboard(
        result.invoice.invoice_id,
        bot_invoice_url=result.invoice.bot_invoice_url or result.invoice.pay_url,
        mini_app_invoice_url=result.invoice.mini_app_invoice_url
        or result.invoice.web_app_invoice_url,
    )
    await _safe_edit(call, body, kb)
    await call.answer()


@router.callback_query(Menu.filter(F.action == "my/мой"))
async def my_subscription(
    call: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if call.message is None or call.from_user is None:
        await call.answer()
        return
    sub = await SubscriptionRepository(session).get_for_user(call.from_user.id)
    now = datetime.now(UTC)

    if sub is None:
        body = texts.NO_SUBSCRIPTION
    elif sub.expires_at > now:
        days_left = max(1, (sub.expires_at - now).days)
        body = texts.ACTIVE_SUBSCRIPTION.format(
            until=sub.expires_at.strftime("%d.%m.%Y %H:%M UTC"),
            days=days_left,
        )
    else:
        body = texts.EXPIRED_SUBSCRIPTION.format(
            when=sub.expires_at.strftime("%d.%m.%Y")
        )

    _ = settings
    await _safe_edit(call, body, back_to_menu())
    await call.answer()


async def _safe_edit(call: CallbackQuery, text: str, keyboard) -> None:
    message = call.message
    if message is None:
        return
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=keyboard)
        else:
            await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=keyboard)
