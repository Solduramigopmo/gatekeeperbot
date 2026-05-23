from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import aiohttp


class CryptoBotError(RuntimeError):
"""Возникает, когда Crypto Pay API возвращает ошибку или неожиданную полезную нагрузку."""

    def __init__(self, code: int | str, name: str) -> None:
        super().__init__(f"Crypto Pay error {code}: {name}")
        self.code = code
        self.name = name


@dataclass(slots=True)
class Invoice:
    invoice_id: int
    status: str
    asset: str
    amount: Decimal
    pay_url: str
    bot_invoice_url: str | None
    mini_app_invoice_url: str | None
    web_app_invoice_url: str | None
    payload: str | None
    created_at: datetime | None
    paid_at: datetime | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Invoice:
        return cls(
            invoice_id=int(data["invoice_id"]),
            status=str(data.get("status", "")),
            asset=str(data.get("asset", "")),
            amount=Decimal(str(data.get("amount", "0"))),
            pay_url=str(data.get("pay_url") or data.get("bot_invoice_url") or ""),
            bot_invoice_url=data.get("bot_invoice_url"),
            mini_app_invoice_url=data.get("mini_app_invoice_url"),
            web_app_invoice_url=data.get("web_app_invoice_url"),
            payload=data.get("payload"),
            created_at=_parse_dt(data.get("created_at")),
            paid_at=_parse_dt(data.get("paid_at")),
        )

    @property
    def is_paid(self) -> bool:
        return self.status == "paid"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class CryptoPay:
    """Минимальный асинхронный клиент для Crypto Pay API.

    Docs: https://help.crypt.bot/crypto-pay-api
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://pay.crypt.bot",
        session: aiohttp.ClientSession | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> CryptoPay:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, **params: Any) -> Any:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._owns_session = True

        url = f"{self._base_url}/api/{method}"
        headers = {"Crypto-Pay-API-Token": self._token}
        cleaned = {k: v for k, v in params.items() if v is not None}
        async with self._session.post(url, json=cleaned, headers=headers) as resp:
            payload = await resp.json(content_type=None)
        if not payload.get("ok"):
            err = payload.get("error", {})
            raise CryptoBotError(err.get("code", resp.status), err.get("name", "unknown"))
        return payload["result"]

    async def get_me(self) -> dict[str, Any]:
        return await self._request("getMe")

    async def create_invoice(
        self,
        *,
        asset: str,
        amount: Decimal,
        description: str | None = None,
        payload: str | None = None,
        hidden_message: str | None = None,
        expires_in: int | None = 1800,
        allow_anonymous: bool = False,
        allow_comments: bool = False,
    ) -> Invoice:
        data = await self._request(
            "createInvoice",
            asset=asset,
            amount=str(amount),
            description=description,
            payload=payload,
            hidden_message=hidden_message,
            expires_in=expires_in,
            allow_anonymous=allow_anonymous,
            allow_comments=allow_comments,
        )
        return Invoice.from_api(data)

    async def get_invoice(self, invoice_id: int) -> Invoice | None:
        data = await self._request("getInvoices", invoice_ids=[invoice_id])
        items = data.get("items") or []
        if not items:
            return None
        return Invoice.from_api(items[0])

    async def delete_invoice(self, invoice_id: int) -> bool:
        return bool(await self._request("deleteInvoice", invoice_id=invoice_id))


def verify_webhook_signature(token: str, body: bytes, signature: str | None) -> bool:
"""Проверьте заголовок `crypto-pay-api-signature".

 В документах Crypto Pay подпись будет `HMAC_SHA256(SHA256(токен), raw_body)`.
 """
    if not signature:
        return False
    secret = hashlib.sha256(token.encode("utf-8")).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())
