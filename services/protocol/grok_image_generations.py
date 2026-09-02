from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from curl_cffi import requests

from services.config import _is_valid_http_url, config
from services.protocol.conversation import format_image_result
from utils.log import logger

GROK_IMAGE_MODELS = {"grok-imagine-image-2.0", "grok-imagine-image"}
GROK_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_grok_image_model(model: object) -> bool:
    return str(model or "").strip() in GROK_IMAGE_MODELS


def is_grok_configured() -> bool:
    settings = config.grok_image
    return bool(
        settings.get("enabled")
        and str(settings.get("api_key") or "").strip()
        and _is_valid_http_url(settings.get("base_url"))
    )


def _resolve_media_url(url: str, base_url: str) -> str:
    parsed = urlsplit(url)
    upstream = urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        return urlunsplit((upstream.scheme, upstream.netloc, parsed.path, parsed.query, parsed.fragment))
    if (parsed.hostname or "").lower().rstrip(".") not in GROK_LOCAL_HOSTS:
        return url
    return urlunsplit((upstream.scheme, upstream.netloc, parsed.path, parsed.query, parsed.fragment))


def _build_edit_request(body: dict[str, Any], images: list[tuple[bytes, str, str]]) -> dict[str, Any]:
    if not images:
        raise ValueError("Grok 图生图至少需要一张参考图")
    if body.get("mask"):
        raise ValueError("Grok 图生图暂不支持 mask 局部编辑")
    references = [
        {
            "url": f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
        }
        for data, _filename, mime_type in images
    ]
    request: dict[str, Any] = {
        "model": str(body.get("model") or "grok-imagine-image-2.0").strip(),
        "prompt": str(body.get("prompt") or "").strip(),
        "n": 1,
        "quality": str(body.get("quality") or "medium").strip().lower(),
        "response_format": "b64_json",
        "stream": False,
    }
    request["image"] = references[0] if len(references) == 1 else references
    size = str(body.get("size") or "").strip().lower()
    size_match = re.fullmatch(r"grok:(1k|2k):(1:1|16:9|9:16|4:3|3:4|3:2|2:3)", size)
    if size_match:
        request["resolution"] = size_match.group(1)
        request["aspect_ratio"] = size_match.group(2)
    return request


def _request_images(body: dict[str, Any], *, endpoint: str, request_body: dict[str, Any]) -> dict[str, Any]:
    settings = config.grok_image
    if not is_grok_configured():
        raise ValueError("Grok 图片生成尚未完成系统配置，请先设置 API Key 和 Base URL")
    base_url = str(settings["base_url"]).rstrip("/")
    model = str(request_body.get("model") or "grok-imagine-image-2.0").strip()
    if not is_grok_image_model(model):
        raise ValueError("不支持的 Grok 图片模型")
    prompt = str(request_body.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    quality = str(request_body.get("quality") or "medium").strip().lower()
    if quality not in {"low", "medium"}:
        quality = "medium"
    response_format = str(body.get("response_format") or "url").strip().lower()
    if response_format not in {"url", "b64_json"}:
        raise ValueError("Grok response_format 只支持 url 或 b64_json")
    if bool(body.get("stream")):
        raise ValueError("Grok 图片任务暂不支持 stream=true，请使用 stream=false")
    request_body["quality"] = quality
    target_url = f"{base_url}/{endpoint}"
    logger.info({"event": "grok_image_upstream_request", "target_url": target_url})
    try:
        response = requests.post(
            target_url,
            headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"},
            json=request_body,
            timeout=120,
        )
    except Exception as exc:
        raise ValueError(f"Grok 上游连接失败（目标地址：{target_url}）：{exc}") from exc
    if response.status_code >= 400:
        try:
            upstream_error = response.text.strip()
        except Exception:
            upstream_error = ""
        api_key = str(settings.get("api_key") or "").strip()
        if api_key:
            upstream_error = upstream_error.replace(api_key, "[REDACTED]")
        if len(upstream_error) > 1000:
            upstream_error = upstream_error[:1000] + "..."
        detail = f"：{upstream_error}" if upstream_error else ""
        raise ValueError(f"Grok 图片生成失败（HTTP {response.status_code}）{detail}")
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
        media_url = _resolve_media_url(url, base_url)
        if media_url != url:
            logger.info({"event": "grok_image_media_url_rewritten", "target_url": media_url})
        media_headers = {"Authorization": f"Bearer {settings['api_key']}"} if media_url != url else None
        image_response = requests.get(media_url, headers=media_headers, timeout=120)
        if image_response.status_code >= 400:
            raise ValueError("Grok 图片下载失败")
        image_items.append({"b64_json": base64.b64encode(image_response.content).decode("ascii")})
    if not image_items:
        raise ValueError("Grok 未返回有效图片")
    return format_image_result(
        image_items,
        prompt,
        response_format,
        str(body.get("base_url") or ""),
        0,
        requested_size=body.get("size"),
        owner_id=str(body.get("_owner_id") or ""),
        model=model,
    )


def handle(body: dict[str, Any]) -> dict[str, Any]:
    size = str(body.get("size") or "").strip().lower()
    size_match = re.fullmatch(r"grok:(1k|2k):(1:1|16:9|9:16|4:3|3:4|3:2|2:3)", size)
    request_body = {
        "model": str(body.get("model") or "grok-imagine-image-2.0").strip(),
        "prompt": str(body.get("prompt") or "").strip(),
        "n": 1,
        "aspect_ratio": size_match.group(2) if size_match else "1:1",
        "resolution": size_match.group(1) if size_match else "1k",
        "quality": str(body.get("quality") or "medium").strip().lower(),
        # Fetch bytes directly so Grok2API's container-local media URL
        # never becomes a cross-container dependency.
        "response_format": "b64_json",
        "stream": False,
    }
    return _request_images(body, endpoint="images/generations", request_body=request_body)


def handle_edit(body: dict[str, Any]) -> dict[str, Any]:
    images = body.get("images") or []
    if not isinstance(images, list):
        raise ValueError("Grok 图生图参考图格式无效")
    return _request_images(
        body,
        endpoint="images/edits",
        request_body=_build_edit_request(body, images),
    )
