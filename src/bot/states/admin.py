from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class PricingStates(StatesGroup):
    waiting_for_price = State()
