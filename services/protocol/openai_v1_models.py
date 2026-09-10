from __future__ import annotations

from typing import Any

from services.model_catalog_service import get_model_catalog


def _model_item(model: str) -> dict[str, Any]:
    return {
        "id": model,
        "object": "model",
        "created": 0,
        "owned_by": "chatgpt2api",
        "permission": [],
        "root": model,
        "parent": None,
    }


def list_models(identity: dict[str, object] | None = None) -> dict[str, Any]:
    catalog = get_model_catalog(identity)
    return {"object": "list", "data": [_model_item(model) for model in catalog.all_models]}
