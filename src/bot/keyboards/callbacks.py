from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class Menu(CallbackData, prefix="menu"):
    action: str  # buy | info | support | my | back


class BuyPlan(CallbackData, prefix="buy"):
    plan_id: str


class BuyAsset(CallbackData, prefix="asset"):
    plan_id: str
    asset: str


class Invoice(CallbackData, prefix="inv"):
    action: str  # check | cancel
    invoice_id: int


class Admin(CallbackData, prefix="adm"):
    action: str  # refresh | plans | recent | pricing | close


class AdminPrice(CallbackData, prefix="apr"):
    action: str  # edit | reset | back
    plan_id: str = ""
