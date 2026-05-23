from aiogram import Dispatcher

from . import admin, errors, payment, start, subscription


def register_routers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(subscription.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    dp.include_router(errors.router)


__all__ = ["register_routers"]
