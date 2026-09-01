from __future__ import annotations

import base64
import re
from math import gcd
from typing import Any

from curl_cffi import requests

from services.config import config
from services.protocol.conversation import format_image_result

GROK_IMAGE_MODELS = {"grok-imagine-image-2.0", "grok-imagine-image"}


def is_grok_image_model(model: object) -> bool:
    return str(model or "").strip() in GROK_IMAGE_MODELS


def handle(body: dict[str, Any]) -> dict[str, Any]:
    settings = config.grok_image
    if not settings.get("enabled") or not str(settings.get("api_key") or "").strip():
        raise ValueError("Grok 图片生成尚未配置 API Key")
    model = str(body.get("model") or "grok-imagine-image-2.0").strip()
    if not is_grok_image_model(model):
        raise ValueError("不支持的 Grok 图片模型")
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    size = str(body.get("size") or "").strip().lower()
    ratio: str | None = None
    match = re.fullmatch(r"(\d+)\s*x\s*(\d+)", size)
    if match:
        width, height = int(match.group(1)), int(match.group(2))
        divisor = gcd(width, height)
        ratio = f"{width // divisor}:{height // divisor}"
    response = requests.post(
        f"{str(settings['base_url']).rstrip('/')}/images/generations",
        headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"},
        json={
            "model": model,
            "prompt": prompt,
            "n": 1,
            "quality": str(body.get("quality") or "medium"),
            **({"aspect_ratio": ratio} if ratio else {}),
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise ValueError(f"Grok 图片生成失败（HTTP {response.status_code}）")
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data:
        raise ValueError("Grok 未返回图片")
    image_items: list[dict[str, str]] = []
    for item in data[:1]:
        if not isinstance(item, dict):
            continue
        if str(item.get("b64_json") or "").strip():
            image_items.append({"b64_json": str(item["b64_json"])})
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        image_response = requests.get(url, timeout=120)
        if image_response.status_code >= 400:
            raise ValueError("Grok 图片下载失败")
        image_items.append({"b64_json": base64.b64encode(image_response.content).decode("ascii")})
    if not image_items:
        raise ValueError("Grok 未返回有效图片")
    return format_image_result(
        image_items,
        prompt,
        "url",
        str(body.get("base_url") or ""),
        0,
        requested_size=body.get("size"),
        owner_id=str(body.get("_owner_id") or ""),
        model=model,
    )
