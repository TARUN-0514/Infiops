"""Model gateway: one entry point for every model call.

Local-first: jobs run on the owner's local model by default. A caller may ask for the
cloud for one request; that only happens when cloud is enabled, a key is set, the data
is not secret, and today's cloud token cap is not used up. Every call is logged."""

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import TRANSIENT_ERRORS, AnthropicProvider, LocalProvider, Provider
from app.ai.types import (
    BudgetExceededError,
    Job,
    ModelRefusalError,
    ModelRequest,
    ModelResponse,
    ModelUnavailableError,
    Privacy,
    TextCallback,
)
from app.core.config import Settings, get_settings
from app.core.logging import log
from app.models import ModelUsageLog


class ModelGateway:
    def __init__(self, settings: Settings, providers: dict[str, Provider]) -> None:
        self.settings = settings
        self.providers = providers

    def local_model(self, job: Job) -> str:
        s = self.settings
        return {
            "chat": s.local_model,
            "plan": s.local_model_plan or s.local_model,
            "fast": s.local_model_fast or s.local_model,
        }[job]

    def cloud_model(self, job: Job) -> str:
        s = self.settings
        return {"chat": s.cloud_model_chat, "plan": s.cloud_model_plan, "fast": s.cloud_model_fast}[
            job
        ]

    def cloud_ready(self) -> bool:
        cloud = self.providers.get("anthropic")
        return self.settings.cloud_enabled and cloud is not None and cloud.available()

    def local_ready(self) -> bool:
        local = self.providers.get("local")
        return local is not None and local.available()

    async def status(self) -> dict[str, Any]:
        local = self.providers.get("local")
        reachable = await local.ping() if isinstance(local, LocalProvider) else self.local_ready()
        return {
            "mode": "local-first",
            "local": {
                "enabled": self.local_ready(),
                "reachable": reachable,
                "base_url": self.settings.local_base_url,
                "models": {j: self.local_model(j) for j in ("chat", "plan", "fast")},
            },
            "cloud": {
                "enabled": self.settings.cloud_enabled,
                "configured": bool(
                    self.providers.get("anthropic") and self.providers["anthropic"].available()
                ),
                "ready": self.cloud_ready(),
                "daily_token_budget": self.settings.cloud_daily_token_budget,
                "models": {j: self.cloud_model(j) for j in ("chat", "plan", "fast")},
            },
        }

    async def cloud_tokens_today(self, db: AsyncSession, user_id: uuid.UUID | None) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        q = select(
            func.coalesce(func.sum(ModelUsageLog.input_tokens + ModelUsageLog.output_tokens), 0)
        ).where(ModelUsageLog.at >= start, ModelUsageLog.provider == "anthropic")
        if user_id is not None:
            q = q.where(ModelUsageLog.user_id == user_id)
        return int((await db.execute(q)).scalar_one())

    def _cost(self, model: str, resp: ModelResponse) -> Decimal | None:
        price = self.settings.model_prices.get(model)
        if not price or len(price) != 2:
            return None
        total = resp.input_tokens * price[0] + resp.output_tokens * price[1]
        return Decimal(str(round(total / 1_000_000, 6)))

    async def _pick(
        self,
        db: AsyncSession,
        job: Job,
        user_id: uuid.UUID | None,
        cloud: bool,
        privacy: Privacy,
    ) -> tuple[Provider, str]:
        if cloud and privacy != "secret":
            if not self.cloud_ready():
                raise ModelUnavailableError(
                    "Cloud is off. Set NEXUS_CLOUD_ENABLED=true and an API key to use it."
                )
            if await self.cloud_tokens_today(db, user_id) >= self.settings.cloud_daily_token_budget:
                raise BudgetExceededError("Today's cloud token cap is used up.")
            return self.providers["anthropic"], self.cloud_model(job)
        if not self.local_ready():
            raise ModelUnavailableError("The local model is turned off.")
        return self.providers["local"], self.local_model(job)

    async def complete(
        self,
        db: AsyncSession,
        *,
        job: Job,
        req: ModelRequest,
        user_id: uuid.UUID | None,
        privacy: Privacy = "normal",
        cloud: bool = False,
        on_text: TextCallback | None = None,
    ) -> ModelResponse:
        provider, model = await self._pick(db, job, user_id, cloud, privacy)
        req.model = model
        started = time.perf_counter()

        def usage(resp: ModelResponse | None, status: str) -> ModelUsageLog:
            return ModelUsageLog(
                user_id=user_id,
                job=job,
                provider=provider.name,
                model=resp.model if resp else req.model,
                input_tokens=resp.input_tokens if resp else 0,
                output_tokens=resp.output_tokens if resp else 0,
                cache_read_tokens=resp.cache_read_tokens if resp else 0,
                cache_write_tokens=resp.cache_write_tokens if resp else 0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                cost_usd=self._cost(resp.model, resp) if resp else None,
                status=status,
            )

        try:
            try:
                resp = await provider.complete(req, on_text)
            except TRANSIENT_ERRORS as exc:
                if provider.name != "anthropic" or job == "fast":
                    raise
                # One cloud fallback down the ladder: plan -> chat -> fast.
                log.warning("model_fallback", job=job, error=type(exc).__name__)
                req.model = self.cloud_model("chat" if job == "plan" else "fast")
                resp = await provider.complete(req, on_text)
        except TRANSIENT_ERRORS as exc:
            db.add(usage(None, "error"))
            await db.flush()
            if provider.name == "local":
                raise ModelUnavailableError(
                    f"Can't reach the local model. Start Ollama or LM Studio and load {model}."
                ) from exc
            raise
        except httpx.HTTPStatusError as exc:
            db.add(usage(None, "error"))
            await db.flush()
            raise ModelUnavailableError(
                f"The local model server returned {exc.response.status_code}. "
                f"Check that {model} is downloaded and loaded."
            ) from exc
        except Exception:
            db.add(usage(None, "error"))
            await db.flush()
            raise
        refused = resp.stop_reason == "refusal"
        db.add(usage(resp, "refusal" if refused else "ok"))
        await db.flush()
        if refused:
            raise ModelRefusalError("The model declined this request.")
        return resp


_gateway: ModelGateway | None = None


def get_gateway() -> ModelGateway:
    global _gateway
    if _gateway is None:
        s = get_settings()
        _gateway = ModelGateway(
            s,
            {
                "local": LocalProvider(s.local_base_url, s.local_enabled),
                "anthropic": AnthropicProvider(
                    s.anthropic_api_key.get_secret_value(), s.anthropic_refusal_fallback
                ),
            },
        )
    return _gateway


def set_gateway(gateway: ModelGateway | None) -> None:
    """Swap the gateway (tests use a scripted provider)."""
    global _gateway
    _gateway = gateway
