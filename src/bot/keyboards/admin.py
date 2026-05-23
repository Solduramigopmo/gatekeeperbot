from __future__ import annotations

from decimal import Decimal

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import texts
from ..config import Plan
from .callbacks import Admin, AdminPrice


def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.ADMIN_BTN_REFRESH, callback_data=Admin(action="обновить").pack())
    kb.button(text=texts.ADMIN_BTN_STATS_BY_PLAN, callback_data=Admin(action="планы").pack())
    kb.button(text=texts.ADMIN_BTN_LIST_USERS, callback_data=Admin(action="недавние").pack())
    kb.button(text=texts.ADMIN_BTN_PRICING, callback_data=Admin(action="ценообразование").pack())
    kb.button(text=texts.ADMIN_BTN_CLOSE, callback_data=Admin(action="закрыть").pack())
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def back_to_admin() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.ADMIN_BTN_REFRESH, callback_data=Admin(action="обновить").pack())
    return kb.as_markup()


def pricing_menu(plans: list[Plan], overridden: set[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for plan in plans:
        marker = " ✏️" if plan.id in overridden else ""
        kb.button(
            text=f"{plan.title} — {_fmt(plan.price)}{marker}",
            callback_data=AdminPrice(action="изменить", plan_id=plan.id).pack(),
        )
    kb.button(text=texts.ADMIN_BTN_BACK, callback_data=Admin(action="обновить").pack())
    kb.adjust(1)
    return kb.as_markup()


def pricing_edit_menu(plan_id: str, *, has_override: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_override:
        kb.button(
            text=texts.ADMIN_BTN_RESET_PRICE,
            callback_data=AdminPrice(action="сбросить", plan_id=plan_id).pack(),
        )
    kb.button(
        text=texts.ADMIN_BTN_BACK,
        callback_data=Admin(action="ценообразование").pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def cancel_price_edit() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts.ADMIN_BTN_CANCEL_EDIT,
        callback_data=Admin(action="ценообразование").pack(),
    )
    return kb.as_markup()


def _fmt(value: Decimal) -> str:
    if value % 1 == 0:
        return f"{value.quantize(Decimal('1'))}"
    return format(value.normalize(), "f")
