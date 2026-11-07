"""OpenRouter provider: verified zero-cost models only.

The Holding runs its AI on OpenRouter's free tier. "Free" is not taken on
trust: before any request is sent the model's *published price* is fetched and
checked, and after a request returns the *actual* model OpenRouter used and the
*reported* cost are checked again. Any model that is not provably zero-cost is
refused, and the provider never falls back to a paid model -- it either answers
on a verified-free model or degrades to the deterministic provider upstream.

Two subtleties drive the design:

* ``openrouter/free`` is a *router*: it picks a free model at random per
  request. It is safe as a default precisely because the response names the
  model it chose, so the check is applied to the concrete model rather than to
  the router id.
* Discovery is a network call. If it fails, the provider cannot prove a model is
  free, so it refuses to call it at all -- failing closed rather than risking a
  charge.

The HTTP client is deliberately built on the standard library (``urllib``) so
the default deployment needs no extra dependency, and so the whole path can be
exercised against a local server in tests.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.ai.base import AIAnswer, PaidModelError, ProviderError

logger = logging.getLogger("safir.ai")

# OpenRouter's free-model router. It only ever selects zero-cost models.
FREE_ROUTER_ID = "openrouter/free"

# Pricing keys that must all be zero for a model to count as free. OpenRouter
# publishes at least ``prompt`` and ``completion`` for every model, so their
# absence means "price unknown", which is treated as *not* free.
_REQUIRED_PRICE_KEYS = ("prompt", "completion")


@dataclass(slots=True)
class FreeModel:
    """A model that has been verified as zero-cost."""

    id: str
    name: str
    context_length: int | None = None
    description: str = ""


def pricing_is_zero(pricing) -> bool:
    """True only when every published price is exactly zero.

    A missing or malformed pricing block is *not* free: an unknown price must be
    treated as a potential charge, so this returns ``False`` unless the two
    required keys are present and every value parses to zero.
    """
    if not isinstance(pricing, dict):
        return False
    if any(key not in pricing for key in _REQUIRED_PRICE_KEYS):
        return False
    for value in pricing.values():
        try:
            if Decimal(str(value if value is not None else 0)) != 0:
                return False
        except (InvalidOperation, ValueError):
            return False
    return True


def is_router(model_id: str) -> bool:
    """True for a routing model whose concrete choice must be verified later."""
    return model_id == FREE_ROUTER_ID


class OpenRouterClient:
    """Thin OpenRouter HTTP client with a short-lived model catalogue cache.

    Only three endpoints are used: ``GET /models`` (discovery and price
    verification) and ``POST /chat/completions`` (inference). The API key is
    never logged and never placed anywhere but the Authorization header.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 30.0,
        cache_ttl_seconds: float = 300.0,
        site_url: str = "",
        app_title: str = "Safir Holding 2027",
        transport=None,
    ) -> None:
        if not api_key:
            raise ProviderError("OPENROUTER_API_KEY is required for the OpenRouter provider.")
        if not base_url:
            raise ProviderError("OPENROUTER_BASE_URL is required for the OpenRouter provider.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._cache_ttl = cache_ttl_seconds
        self._site_url = site_url
        self._app_title = app_title
        # Injectable transport (method, url, headers, body, timeout) -> parsed
        # JSON. Defaults to the urllib implementation below.
        self._transport = transport or self._http_json
        self._lock = threading.Lock()
        self._cache: list[dict] = []
        self._cache_at: float = 0.0

    # -- transport ---------------------------------------------------------
    def _http_json(self, method: str, url: str, headers: dict, body: bytes | None, timeout: float):
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 429 is worth distinguishing: the caller rate-limits rather than
            # treating it as a hard outage.
            raise ProviderError(f"OpenRouter returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ProviderError("OpenRouter is currently unavailable.") from exc

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        # OpenRouter's optional attribution headers; not secrets.
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._app_title:
            headers["X-Title"] = self._app_title
        return headers

    # -- discovery ---------------------------------------------------------
    def catalogue(self, *, force: bool = False) -> list[dict]:
        """Every model OpenRouter advertises, cached for ``cache_ttl_seconds``."""
        now = time.monotonic()
        with self._lock:
            fresh = self._cache and (now - self._cache_at) < self._cache_ttl
            if fresh and not force:
                return list(self._cache)
        payload = self._transport(
            "GET",
            f"{self._base_url}/models",
            {"Accept": "application/json", "Authorization": f"Bearer {self._api_key}"},
            None,
            self._timeout,
        )
        models = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise ProviderError("OpenRouter returned an unexpected model catalogue.")
        with self._lock:
            self._cache = models
            self._cache_at = time.monotonic()
        return list(models)

    def free_models(self, *, force: bool = False) -> list[FreeModel]:
        """Models whose published pricing is verified zero across the board."""
        result: list[FreeModel] = []
        for model in self.catalogue(force=force):
            model_id = model.get("id")
            if not model_id:
                continue
            # The router itself advertises zero pricing and always routes to a
            # free model, so it is listed as available for selection.
            if model_id == FREE_ROUTER_ID or pricing_is_zero(model.get("pricing")):
                result.append(
                    FreeModel(
                        id=model_id,
                        name=model.get("name") or model_id,
                        context_length=model.get("context_length"),
                        description=(model.get("description") or "").strip(),
                    )
                )
        return result

    def is_verified_free(self, model_id: str, *, force: bool = False) -> bool:
        """Whether ``model_id`` is provably zero-cost right now."""
        if model_id == FREE_ROUTER_ID:
            return True
        for model in self.catalogue(force=force):
            if model.get("id") == model_id:
                return pricing_is_zero(model.get("pricing"))
        return False

    def complete(self, *, model: str, messages: list[dict], temperature: float = 0.2):
        """Send one chat completion and return the parsed response body."""
        payload = {"model": model, "temperature": temperature, "messages": messages}
        return self._transport(
            "POST",
            f"{self._base_url}/chat/completions",
            self._headers(),
            json.dumps(payload).encode("utf-8"),
            self._timeout,
        )


_SYSTEM_PROMPT = (
    "أنت مساعد ذكاء أعمال واستثمار لمجموعة قابضة. تجيب بالعربية الفصحى بإيجاز "
    "تنفيذي. القاعدة المطلقة: لا تذكر أي رقم غير موجود في البيانات المرفقة. "
    "إذا لم تتوفر بيانات كافية، قل ذلك صراحةً بدل التخمين. "
    "You are a business & investment intelligence assistant for a holding "
    "company. Answer in concise executive Arabic. Never state a figure that is "
    "not present in the supplied data; say the data is unavailable instead."
)


class OpenRouterProvider:
    """Answers on OpenRouter using verified zero-cost models only.

    Never falls back to a paid model. If no verified-free model is usable the
    provider raises, and the caller degrades to the deterministic provider.
    """

    name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        fallback_models: list[str] | None = None,
        timeout: float = 30.0,
        max_cost_usd: float = 0.0,
        client: OpenRouterClient | None = None,
        site_url: str = "",
        app_title: str = "Safir Holding 2027",
    ) -> None:
        self._model = model or FREE_ROUTER_ID
        self._fallbacks = [m for m in (fallback_models or []) if m]
        self._max_cost = Decimal(str(max_cost_usd or 0))
        self._client = client or OpenRouterClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            site_url=site_url,
            app_title=app_title,
        )

    # -- public helpers (used by the admin panel) --------------------------
    def free_models(self, *, force: bool = False) -> list[FreeModel]:
        return self._client.free_models(force=force)

    def is_verified_free(self, model_id: str) -> bool:
        return self._client.is_verified_free(model_id)

    @property
    def configured_model(self) -> str:
        return self._model

    @property
    def configured_fallbacks(self) -> list[str]:
        return list(self._fallbacks)

    # -- inference ---------------------------------------------------------
    def candidate_models(self) -> list[str]:
        """Requested model first, then configured fallbacks, de-duplicated."""
        seen: set[str] = set()
        ordered: list[str] = []
        for model in [self._model, *self._fallbacks]:
            if model and model not in seen:
                seen.add(model)
                ordered.append(model)
        return ordered

    def answer(self, *, question: str, context: dict) -> AIAnswer:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "بيانات النظام (مصدر الحقيقة الوحيد):\n"
                    + json.dumps(context, ensure_ascii=False, default=str)
                    + f"\n\nسؤال المستخدم: {question}"
                ),
            },
        ]

        last_error: Exception | None = None
        for model in self.candidate_models():
            # 1) Refuse to *send* a request to a model that is not verified
            #    free. A paid model is skipped, never used.
            try:
                if not self._client.is_verified_free(model):
                    raise PaidModelError(
                        f"Model {model!r} is not a verified zero-cost model; refusing to use it."
                    )
            except PaidModelError as exc:
                logger.warning("OpenRouter refused a non-free model: %s", model)
                last_error = exc
                continue
            except ProviderError as exc:
                # Discovery failed: cannot prove it is free -> fail closed.
                last_error = exc
                break

            # 2) Call it, then verify the *actual* model and reported cost.
            try:
                return self._complete(model, messages)
            except PaidModelError as exc:
                logger.warning("OpenRouter cost breaker fired: %s", exc)
                last_error = exc
                continue
            except ProviderError as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error
        raise ProviderError("No verified zero-cost OpenRouter model is available.")

    def _complete(self, requested_model: str, messages: list[dict]) -> AIAnswer:
        started = time.monotonic()
        body = self._client.complete(model=requested_model, messages=messages)
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            text = body["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenRouter returned an unexpected response.") from exc

        # The concrete model OpenRouter actually used. For the router this is a
        # specific free model; for a direct call it echoes the request.
        actual_model = body.get("model") or requested_model

        # Post-hoc verification: whichever model actually ran must itself be
        # provably zero-cost. This is the second half of the guarantee -- the
        # pre-call check verified what we *asked for*, this verifies what we
        # *got*, so a router cannot smuggle in a paid model. An unknown model id
        # is treated as not-free (fail closed).
        if not self._client.is_verified_free(actual_model):
            raise PaidModelError(
                f"OpenRouter answered with {actual_model!r}, which is not verified "
                "zero-cost; discarding the answer."
            )

        usage = body.get("usage") or {}
        cost = self._reported_cost(usage)
        if cost > self._max_cost:
            raise PaidModelError(
                f"OpenRouter reported a cost of ${cost} for a supposedly free model; "
                "discarding the answer."
            )

        return AIAnswer(
            text=text,
            provider=self.name,
            tokens_used=usage.get("total_tokens"),
            model=actual_model,
            cost_usd=float(cost),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _reported_cost(usage: dict) -> Decimal:
        """The call cost OpenRouter reports, tolerating the several shapes it uses."""
        for key in ("cost", "total_cost", "cost_usd"):
            if key in usage and usage[key] is not None:
                try:
                    return Decimal(str(usage[key]))
                except (InvalidOperation, ValueError):
                    return Decimal(0)
        return Decimal(0)
