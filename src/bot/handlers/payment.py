from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from .. import texts
from ..database.models import PaymentStatus
from ..database.repository import PaymentRepository
from ..keyboards.callbacks import Invoice as InvoiceCb
from ..keyboards.user import back_to_menu
from ..services.cryptobot import CryptoBotError
from ..services.subscription import SubscriptionService

router = Router(name="payment")


@router.callback_query(InvoiceCb.filter(F.action == "check"))
async def check_payment(
    call: CallbackQuery,
    callback_data: InvoiceCb,
    session: AsyncSession,
    subscriptions: SubscriptionService,
) -> None:
    if call.from_user is None or call.message is None:
        await call.answer()
        return

    payments = PaymentRepository(session)
    payment = await payments.get_by_invoice(callback_data.invoice_id)
    if payment is None or payment.user_id != call.from_user.id:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        return

    if payment.status == PaymentStatus.paid:
        await call.answer("✅ Уже оплачено.", show_alert=False)
        return

    try:
        result = await subscriptions.reconcile_invoice(session, callback_data.invoice_id)
    except CryptoBotError:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        raise

    if result is None:
        await call.answer(texts.INVOICE_NOT_PAID, show_alert=False)
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

    await _safe_edit(call, body, back_to_menu())
    await call.answer("✅ Оплата получена")


@router.callback_query(InvoiceCb.filter(F.action == "cancel"))
async def cancel_invoice(
    call: CallbackQuery,
    callback_data: InvoiceCb,
    session: AsyncSession,
    subscriptions: SubscriptionService,
) -> None:
    if call.from_user is None or call.message is None:
        await call.answer()
        return

    payments = PaymentRepository(session)
    payment = await payments.get_by_invoice(callback_data.invoice_id)
    if payment is None or payment.user_id != call.from_user.id:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        return

    if payment.status == PaymentStatus.pending:
        with contextlib.suppress(CryptoBotError):
            await subscriptions.crypto.delete_invoice(callback_data.invoice_id)
        await payments.mark_status(payment, PaymentStatus.cancelled)

    await _safe_edit(call, texts.INVOICE_CANCELLED, back_to_menu())
    await call.answer()


async def _safe_edit(call: CallbackQuery, text: str, keyboard) -> None:
    message = call.message
    if message is None:
        return
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=keyboard)
        else:
            await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
