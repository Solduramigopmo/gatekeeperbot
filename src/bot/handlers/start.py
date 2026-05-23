from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import texts
from ..config import Settings
from ..keyboards.callbacks import Menu
from ..keyboards.user import back_to_menu, main_menu
from ..services.subscription import SubscriptionService

router = Router(name="начать")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    subscriptions: SubscriptionService,
) -> None:
    if message.from_user is None:
        return
    await subscriptions.ensure_user(
        session,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        language_code=message.from_user.language_code,
    )
    await _send_welcome(message, settings)


@router.callback_query(Menu.filter(F.action == "вернуться"))
async def handle_back(call: CallbackQuery, settings: Settings) -> None:
    if call.message is None:
        await call.answer()
        return
    await _replace_with_welcome(call, settings)
    await call.answer()


@router.callback_query(Menu.filter(F.action == "информация"))
async def handle_info(call: CallbackQuery) -> None:
    if call.message is None:
        await call.answer()
        return
    await call.message.edit_text(
        texts.INFO, reply_markup=back_to_menu(), disable_web_page_preview=True
    )
    await call.answer()


@router.callback_query(Menu.filter(F.action == "поддержка"))
async def handle_support(call: CallbackQuery) -> None:
    if call.message is None:
        await call.answer()
        return
    await call.message.edit_text(
        "Свяжись с поддержкой: укажи свой ID и подробно опиши проблему.",
        reply_markup=back_to_menu(),
    )
    await call.answer()


# ── helpers ──────────────────────────────────────────────────────────────────


async def _send_welcome(message: Message, settings: Settings) -> None:
    text = _format_welcome(message)
    keyboard = main_menu(settings)
    photo = _welcome_photo(settings.welcome_image)
    if photo is not None:
        await message.answer_photo(photo=photo, caption=text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


async def _replace_with_welcome(call: CallbackQuery, settings: Settings) -> None:
    message = call.message
    if message is None:
        return
    text = _format_welcome(message)
    keyboard = main_menu(settings)
    if message.photo:
        try:
            await message.edit_caption(caption=text, reply_markup=keyboard)
            return
        except Exception:
            pass
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await message.answer(text, reply_markup=keyboard)


def _format_welcome(message: Message) -> str:
    name = (message.from_user.first_name if message.from_user else None) or "друг"
    return texts.WELCOME.format(name=name)


def _welcome_photo(path: Path | None) -> FSInputFile | None:
    if path is None:
        return None
    if not path.exists():
        return None
    return FSInputFile(str(path))
