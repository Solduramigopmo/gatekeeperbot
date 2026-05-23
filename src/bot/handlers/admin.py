from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import texts
from ..config import Settings
from ..database.repository import (
    PaymentRepository,
    SubscriptionRepository,
    UserRepository,
)
from ..keyboards.admin import (
    admin_menu,
    back_to_admin,
    cancel_price_edit,
    pricing_menu,
)
from ..keyboards.callbacks import Admin, AdminPrice
from ..services.pricing import PricingService
from ..states import PricingStates

router = Router(name="admin")


# ── /admin command ──────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def admin_command(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    if message.from_user is None or not settings.is_admin(message.from_user.id):
        await message.answer(texts.ADMIN_FORBIDDEN)
        return
    await state.clear()
    body = await _build_summary(session)
    await message.answer(body, reply_markup=admin_menu())


# ── main panel ─────────────────────────────────────────────────────────────
@router.callback_query(Admin.filter(F.action == "refresh"))
async def admin_refresh(
    call: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _guard(call, settings):
        await call.answer(texts.ADMIN_FORBIDDEN, show_alert=True)
        return
    await state.clear()
    body = await _build_summary(session)
    await _safe_edit(call, body, admin_menu())
    await call.answer("Обновлено")


@router.callback_query(Admin.filter(F.action == "plans"))
async def admin_plans(
    call: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _guard(call, settings):
        await call.answer(texts.ADMIN_FORBIDDEN, show_alert=True)
        return
    rows = await PaymentRepository(session).stats_by_plan()
    if not rows:
        body = texts.ADMIN_STATS_BY_PLAN_HEADER + "Покупок пока не было."
    else:
        lines = [texts.ADMIN_STATS_BY_PLAN_HEADER]
        for plan_id, count, asset, total in rows:
            plan = settings.plan_by_id(plan_id)
            title = plan.title if plan else plan_id
            lines.append(
                texts.ADMIN_STATS_BY_PLAN_ROW.format(
                    title=f"{title} ({asset})",
                    count=count,
                    revenue=texts.format_amount(total, asset),
                )
            )
        body = "".join(lines)
    await _safe_edit(call, body, back_to_admin())
    await call.answer()


@router.callback_query(Admin.filter(F.action == "recent"))
async def admin_recent(
    call: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _guard(call, settings):
        await call.answer(texts.ADMIN_FORBIDDEN, show_alert=True)
        return
    subs = await SubscriptionRepository(session).recent(20)
    if not subs:
        body = texts.ADMIN_RECENT_HEADER + "Подписок пока нет."
    else:
        lines = [texts.ADMIN_RECENT_HEADER]
        for sub in subs:
            plan = settings.plan_by_id(sub.plan_id)
            lines.append(
                texts.ADMIN_RECENT_ROW.format(
                    user_id=sub.user_id,
                    title=plan.title if plan else sub.plan_id,
                    until=sub.expires_at.strftime("%d.%m.%Y"),
                )
            )
        body = "".join(lines)
    await _safe_edit(call, body, back_to_admin())
    await call.answer()


@router.callback_query(Admin.filter(F.action == "close"))
async def admin_close(
    call: CallbackQuery, settings: Settings, state: FSMContext
) -> None:
    if not _guard(call, settings):
        await call.answer(texts.ADMIN_FORBIDDEN, show_alert=True)
        return
    await state.clear()
    if call.message:
        with contextlib.suppress(TelegramBadRequest):
            await call.message.delete()
    await call.answer()


# ── pricing ────────────────────────────────────────────────────────────────
@router.callback_query(Admin.filter(F.action == "pricing"))
async def admin_pricing(
    call: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    pricing: PricingService,
    state: FSMContext,
) -> None:
    if not _guard(call, settings):
        await call.answer(texts.ADMIN_FORBIDDEN, show_alert=True)
        return
    await state.clear()
    plans = await pricing.effective_plans(session)
    overridden = {
        p.id for p in plans
        if (default := settings.plan_by_id(p.id)) is not None and default.price != p.price
    }
    await _safe_edit(call, texts.ADMIN_PRICING_HEADER, pricing_menu(plans, overridden))
    await call.answer()


@router.callback_query(AdminPrice.filter(F.action == "edit"))
async def admin_price_edit(
    call: CallbackQuery,
    callback_data: AdminPrice,
    session: AsyncSession,
    settings: Settings,
    pricing: PricingService,
    state: FSMContext,
) -> None:
    if not _guard(call, settings):
        await call.answer(texts.ADMIN_FORBIDDEN, show_alert=True)
        return
    plan = await pricing.effective_plan(session, callback_data.plan_id)
    default = settings.plan_by_id(callback_data.plan_id)
    if plan is None or default is None:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        return

    await state.set_state(PricingStates.waiting_for_price)
    await state.update_data(plan_id=plan.id)

    body = texts.ADMIN_PRICING_ENTER_NEW.format(
        title=plan.title,
        days=plan.days,
        price=_fmt_price(plan.price),
        default=_fmt_price(default.price),
    )
    await _safe_edit(call, body, cancel_price_edit())
    await call.answer()


@router.callback_query(AdminPrice.filter(F.action == "reset"))
async def admin_price_reset(
    call: CallbackQuery,
    callback_data: AdminPrice,
    session: AsyncSession,
    settings: Settings,
    pricing: PricingService,
    state: FSMContext,
) -> None:
    if not _guard(call, settings):
        await call.answer(texts.ADMIN_FORBIDDEN, show_alert=True)
        return
    plan = await pricing.reset_price(session, callback_data.plan_id)
    if plan is None:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        return

    plans = await pricing.effective_plans(session)
    overridden = {
        p.id for p in plans
        if (default := settings.plan_by_id(p.id)) is not None and default.price != p.price
    }
    body = texts.ADMIN_PRICING_RESET.format(title=plan.title, price=_fmt_price(plan.price))
    body += "\n\n" + texts.ADMIN_PRICING_HEADER
    await _safe_edit(call, body, pricing_menu(plans, overridden))
    await state.clear()
    await call.answer("Сброшено")


@router.message(StateFilter(PricingStates.waiting_for_price))
async def admin_price_input(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    pricing: PricingService,
    state: FSMContext,
) -> None:
    if message.from_user is None or not settings.is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    plan_id = data.get("plan_id")
    if not isinstance(plan_id, str):
        await state.clear()
        await message.answer(texts.GENERIC_ERROR)
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        price = Decimal(raw)
    except InvalidOperation:
        await message.answer(texts.ADMIN_PRICING_BAD_INPUT)
        return
    if price <= 0:
        await message.answer(texts.ADMIN_PRICING_BAD_INPUT)
        return

    try:
        plan = await pricing.set_price(session, plan_id, price)
    except ValueError:
        await state.clear()
        await message.answer(texts.GENERIC_ERROR)
        return

    await state.clear()
    confirmation = texts.ADMIN_PRICING_SAVED.format(
        title=plan.title, price=_fmt_price(plan.price)
    )

    plans = await pricing.effective_plans(session)
    overridden = {
        p.id for p in plans
        if (default := settings.plan_by_id(p.id)) is not None and default.price != p.price
    }
    await message.answer(
        confirmation + "\n\n" + texts.ADMIN_PRICING_HEADER,
        reply_markup=pricing_menu(plans, overridden),
    )


# ── helpers ────────────────────────────────────────────────────────────────
def _guard(call: CallbackQuery, settings: Settings) -> bool:
    return call.from_user is not None and settings.is_admin(call.from_user.id)


def _fmt_price(value: Decimal) -> str:
    if value % 1 == 0:
        return f"{value.quantize(Decimal('1'))}"
    return format(value.normalize(), "f")


async def _build_summary(session: AsyncSession) -> str:
    users = UserRepository(session)
    subs = SubscriptionRepository(session)
    payments = PaymentRepository(session)

    users_count = await users.count()
    active = await subs.count_active()
    paid = await payments.count_paid()
    revenue = await payments.revenue_by_asset()
    recent = await payments.count_paid_since(
        datetime.now(UTC) - timedelta(days=30)
    )
    revenue_str = (
        ", ".join(texts.format_amount(amount, asset) for asset, amount in revenue.items())
        if revenue
        else "—"
    )
    return texts.ADMIN_MENU.format(
        users=users_count,
        active=active,
        paid=paid,
        revenue=revenue_str,
        recent=recent,
    )


async def _safe_edit(call: CallbackQuery, text: str, keyboard) -> None:
    message = call.message
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=keyboard)
