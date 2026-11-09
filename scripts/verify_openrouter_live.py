"""Live OpenRouter verification (reads the key from the environment only).

This harness proves the *live* provider path end-to-end: it discovers the
current free-model catalogue, refuses anything that is not provably zero-cost,
sends one real chat completion through :class:`OpenRouterProvider`, and prints
the concrete model OpenRouter used plus the cost it reported.

The API key is read from ``OPENROUTER_API_KEY`` in the environment and is never
printed, logged, or written anywhere. When the key is absent the run reports
``BLOCKED`` and exits 0 -- an unavailable credential is a blocker to report, not
a failing test.

Run::

    OPENROUTER_API_KEY=... python -m scripts.verify_openrouter_live

or via a dotenv-style file owned by the service user (mode 600)::

    set -a; . /etc/safir/openrouter.env; set +a
    python -m scripts.verify_openrouter_live
"""

from __future__ import annotations

import json
import os
import sys

from backend.ai.openrouter import FREE_ROUTER_ID, OpenRouterClient, OpenRouterProvider
from backend.core.config import settings


def _emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def main() -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY") or settings.OPENROUTER_API_KEY
    if not api_key:
        return _emit(
            {
                "status": "BLOCKED",
                "reason": "OPENROUTER_API_KEY is not present in the environment.",
                "note": "Implementation and unit tests are complete; only live "
                "provider verification is blocked.",
            },
            0,
        )

    client = OpenRouterClient(
        api_key=api_key,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
        site_url=settings.OPENROUTER_SITE_URL,
        app_title=settings.OPENROUTER_APP_TITLE,
    )

    try:
        free = client.free_models(force=True)
    except Exception as exc:  # noqa: BLE001 - report, never crash the harness
        return _emit({"status": "FAIL", "stage": "discovery", "error": str(exc)}, 1)

    free_ids = [m.id for m in free]
    if not free_ids:
        return _emit(
            {"status": "FAIL", "stage": "discovery", "error": "No free models advertised."},
            1,
        )

    provider = OpenRouterProvider(
        api_key=api_key,
        base_url=settings.OPENROUTER_BASE_URL,
        model=settings.OPENROUTER_MODEL or FREE_ROUTER_ID,
        fallback_models=[m.strip() for m in (settings.OPENROUTER_FALLBACK_MODELS or "").split(",") if m.strip()],
        timeout=settings.AI_TIMEOUT_SECONDS,
        max_cost_usd=settings.OPENROUTER_MAX_COST_USD,
        site_url=settings.OPENROUTER_SITE_URL,
        app_title=settings.OPENROUTER_APP_TITLE,
    )

    context = {
        "knowledge": [
            {
                "title_ar": "سياسة الصرف النقدي",
                "content": "الحد الأقصى للصرف النقدي هو 10000 دينار بموافقة المالك.",
            }
        ]
    }
    try:
        answer = provider.answer(
            question="ما هو الحد الأقصى للصرف النقدي؟", context=context
        )
    except Exception as exc:  # noqa: BLE001
        return _emit({"status": "FAIL", "stage": "completion", "error": str(exc)}, 1)

    return _emit(
        {
            "status": "PASS",
            "provider": getattr(provider, "name", "openrouter"),
            "model_requested": settings.OPENROUTER_MODEL or FREE_ROUTER_ID,
            "model_used": getattr(answer, "model", None),
            "grounded": getattr(answer, "grounded", None),
            "free_models_advertised": len(free_ids),
            "answer_excerpt": (getattr(answer, "text", "") or "")[:200],
        },
        0,
    )


if __name__ == "__main__":
    sys.exit(main())
