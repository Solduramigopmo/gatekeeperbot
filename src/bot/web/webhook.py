from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from aiohttp import web

from ..logger import log
from ..services.cryptobot import verify_webhook_signature

WebhookHandler = Callable[[dict], Awaitable[None]]


def build_webhook_app(
    *,
    token: str,
    path: str,
    handler: WebhookHandler,
) -> web.Application:
    app = web.Application()
    app["cryptobot_token"] = token
    app["payment_handler"] = handler

    async def handle_payment(request: web.Request) -> web.Response:
        body = await request.read()
        signature = request.headers.get("crypto-pay-api-signature")
        if not verify_webhook_signature(token, body, signature):
            log.warning("cryptobot.webhook.bad_signature", path=path)
            return web.Response(status=401, text="invalid signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return web.Response(status=400, text="invalid json")

        update_type = payload.get("update_type")
        update_payload = payload.get("payload") or {}
        if update_type == "invoice_paid":
            try:
                await handler(update_payload)
            except Exception:
                log.exception("cryptobot.webhook.handler_failed")
                return web.Response(status=500, text="handler error")
        else:
            log.info("cryptobot.webhook.ignored", update_type=update_type)
        return web.Response(text="ok")

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_post(path, handle_payment)
    app.router.add_get("/health", health)
    return app


async def run_webhook_server(
    app: web.Application,
    *,
    host: str,
    port: int,
) -> tuple[web.AppRunner, web.TCPSite]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    log.info("webhook.started", host=host, port=port)
    return runner, site
