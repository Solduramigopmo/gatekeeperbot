from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import texts
from ..config import Plan, Settings
from .callbacks import BuyAsset, BuyPlan, Invoice, Menu


def main_menu(settings: Settings) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BUY, callback_data=Menu(action="buy").pack())
    kb.button(text=texts.BTN_MY_SUBSCRIPTION, callback_data=Menu(action="my").pack())
    if settings.info_url:
        kb.button(text=texts.BTN_INFO, url=settings.info_url)
    else:
        kb.button(text=texts.BTN_INFO, callback_data=Menu(action="info").pack())
    if settings.support_url:
        kb.button(text=texts.BTN_SUPPORT, url=settings.support_url)
    else:
        kb.button(text=texts.BTN_SUPPORT, callback_data=Menu(action="support").pack())
    kb.adjust(1, 1, 2)
    return kb.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BACK, callback_data=Menu(action="back").pack())
    return kb.as_markup()


def plans_keyboard(plans: list[Plan]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for plan in plans:
        kb.button(
            text=f"{plan.title} — {_format_price(plan.price)}",
            callback_data=BuyPlan(plan_id=plan.id).pack(),
        )
    kb.button(text=texts.BTN_BACK, callback_data=Menu(action="back").pack())
    kb.adjust(1)
    return kb.as_markup()


def assets_keyboard(plan_id: str, assets: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for asset in assets:
        kb.button(
            text=asset,
            callback_data=BuyAsset(plan_id=plan_id, asset=asset).pack(),
        )
    kb.button(text=texts.BTN_BACK, callback_data=Menu(action="buy").pack())
    kb.adjust(len(assets) if assets else 1, 1)
    return kb.as_markup()


def invoice_keyboard(
    invoice_id: int,
    *,
    bot_invoice_url: str | None,
    mini_app_invoice_url: str | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if bot_invoice_url:
        rows.append([InlineKeyboardButton(text=texts.BTN_PAY_IN_BOT, url=bot_invoice_url)])
    if mini_app_invoice_url:
        rows.append(
            [InlineKeyboardButton(text=texts.BTN_PAY_MINIAPP, url=mini_app_invoice_url)]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BTN_CHECK,
                callback_data=Invoice(action="check", invoice_id=invoice_id).pack(),
            ),
            InlineKeyboardButton(
                text=texts.BTN_CANCEL,
                callback_data=Invoice(action="cancel", invoice_id=invoice_id).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_price(value: object) -> str:
    from decimal import Decimal

    if not isinstance(value, Decimal):
        return str(value)
    if value % 1 == 0:
        return f"{value.quantize(Decimal('1'))}"
    return f"{value.normalize():f}"
