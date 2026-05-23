from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Plan, Settings
from ..database.models import PriceOverride


class PricingService:
"""Определяет эффективную цену для каждого тарифного плана, сочетая настройки по умолчанию
с настройками, установленными в панели администратора."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _overrides(self, session: AsyncSession) -> dict[str, Decimal]:
        rows = await session.scalars(select(PriceOverride))
        return {row.plan_id: row.price for row in rows.all()}

    async def effective_plans(self, session: AsyncSession) -> list[Plan]:
        overrides = await self._overrides(session)
        return [self._apply(plan, overrides) for plan in self.settings.subscription_plans]

    async def effective_plan(self, session: AsyncSession, plan_id: str) -> Plan | None:
        base = self.settings.plan_by_id(plan_id)
        if base is None:
            return None
        overrides = await self._overrides(session)
        return self._apply(base, overrides)

    async def set_price(
        self, session: AsyncSession, plan_id: str, price: Decimal
    ) -> Plan:
        if self.settings.plan_by_id(plan_id) is None:
            raise ValueError(f"unknown plan: {plan_id}")
        if price <= 0:
            raise ValueError("price must be positive")

        existing = await session.get(PriceOverride, plan_id)
        if existing is None:
            session.add(PriceOverride(plan_id=plan_id, price=price))
        else:
            existing.price = price
        await session.flush()
        return (await self.effective_plan(session, plan_id))  # type: ignore[return-value]

    async def reset_price(self, session: AsyncSession, plan_id: str) -> Plan | None:
        existing = await session.get(PriceOverride, plan_id)
        if existing is not None:
            await session.delete(existing)
            await session.flush()
        return await self.effective_plan(session, plan_id)

    def _apply(self, plan: Plan, overrides: dict[str, Decimal]) -> Plan:
        if plan.id not in overrides:
            return plan
        return Plan(id=plan.id, title=plan.title, days=plan.days, price=overrides[plan.id])
