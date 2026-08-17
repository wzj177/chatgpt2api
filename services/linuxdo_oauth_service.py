from __future__ import annotations

import json
import hashlib
import secrets
import threading
import time
from collections.abc import Mapping
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.auth_service import auth_service
from services.config import config
from utils.log import logger


class LinuxDoOAuthError(ValueError):
    pass


class LinuxDoOAuthService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, tuple[float, str]] = {}
        self._exchange_codes: dict[str, tuple[float, dict[str, object], str]] = {}

    @staticmethod
    def _endpoint(value: object, field: str) -> str:
        endpoint = str(value or "").strip()
        if not endpoint.startswith("https://"):
            raise LinuxDoOAuthError(f"Linux.do {field} 必须使用 HTTPS 地址")
        return endpoint

    def _settings(self) -> dict[str, object]:
        oauth = config.get_oauth_settings()
        linuxdo = oauth.get("linuxdo") if isinstance(oauth.get("linuxdo"), Mapping) else {}
        if not bool(linuxdo.get("enabled")):
            raise LinuxDoOAuthError("Linux.do 登录尚未启用")
        client_id = str(linuxdo.get("client_id") or "").strip()
        client_secret = str(linuxdo.get("client_secret") or "").strip()
        if not client_id or not client_secret:
            raise LinuxDoOAuthError("Linux.do OAuth 配置不完整")
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "authorization_endpoint": self._endpoint(linuxdo.get("authorization_endpoint"), "授权地址"),
            "token_endpoint": self._endpoint(linuxdo.get("token_endpoint"), "Token 地址"),
            "user_endpoint": self._endpoint(linuxdo.get("user_endpoint"), "用户信息地址"),
        }

    def is_enabled(self) -> bool:
        try:
            self._settings()
            return True
        except LinuxDoOAuthError:
            return False

    def start(self, redirect_uri: str) -> str:
        try:
            settings = self._settings()
        except LinuxDoOAuthError as exc:
            logger.warning({
                "event": "linuxdo_oauth_start_failed",
                "stage": "settings",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            raise
        state = secrets.token_urlsafe(32)
        with self._lock:
            self._prune_locked()
            self._states[state] = (time.time() + 600, redirect_uri)
        query = urlencode({
            'response_type': 'code',
            'client_id': settings['client_id'],
            'redirect_uri': redirect_uri,
            'scope': 'openid profile email',
            'state': state,
        })
        logger.info({
            "event": "linuxdo_oauth_start",
            "redirect_uri": redirect_uri.split("?", 1)[0],
        })
        return f"{settings['authorization_endpoint']}?{query}"

    def callback(self, *, code: str, state: str, redirect_uri: str) -> str:
        logger.info({
            "event": "linuxdo_oauth_callback_received",
            "has_code": bool(code.strip()),
            "has_state": bool(state.strip()),
            "redirect_uri": redirect_uri.split("?", 1)[0],
        })
        try:
            settings = self._settings()
        except LinuxDoOAuthError as exc:
            logger.warning({
                "event": "linuxdo_oauth_callback_failed",
                "stage": "settings",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            raise
        with self._lock:
            self._prune_locked()
            state_record = self._states.pop(state, None)
        if state_record is None or state_record[1] != redirect_uri:
            logger.warning({
                "event": "linuxdo_oauth_callback_failed",
                "stage": "state",
                "error": "OAuth 状态已失效或回调地址不一致",
            })
            raise LinuxDoOAuthError("OAuth 状态已失效，请重新登录")
        if not code.strip():
            logger.warning({
                "event": "linuxdo_oauth_callback_failed",
                "stage": "authorization_code",
                "error": "Linux.do 未返回授权码",
            })
            raise LinuxDoOAuthError("Linux.do 未返回授权码")

        try:
            token_payload = self._request_json(
                settings["token_endpoint"],
                method="POST",
                form={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": settings["client_id"],
                    "client_secret": settings["client_secret"],
                },
            )
        except LinuxDoOAuthError as exc:
            logger.warning({
                "event": "linuxdo_oauth_callback_failed",
                "stage": "token",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            raise
        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            logger.warning({
                "event": "linuxdo_oauth_callback_failed",
                "stage": "token_response",
                "error": "Linux.do Token 响应缺少 access_token",
            })
            raise LinuxDoOAuthError("Linux.do Token 响应缺少 access_token")
        try:
            user_payload = self._request_json(
                settings["user_endpoint"],
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except LinuxDoOAuthError as exc:
            logger.warning({
                "event": "linuxdo_oauth_callback_failed",
                "stage": "user",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            raise
        subject = str(user_payload.get("sub") or user_payload.get("id") or user_payload.get("user_id") or "").strip()
        email = str(user_payload.get("email") or user_payload.get("email_address") or "").strip().lower()
        username = str(
            user_payload.get("username")
            or user_payload.get("preferred_username")
            or user_payload.get("name")
            or email.split("@", 1)[0]
            or "Linux.do 用户"
        ).strip()
        if not subject:
            logger.warning({
                "event": "linuxdo_oauth_callback_failed",
                "stage": "user_response",
                "error": "Linux.do 用户信息缺少账号标识",
            })
            raise LinuxDoOAuthError("Linux.do 用户信息缺少账号标识")
        if not email:
            email = f"linuxdo_{hashlib.sha256(subject.encode()).hexdigest()[:20]}@oauth.local"
        try:
            identity, raw_key = auth_service.authenticate_oauth_user(
                provider="linuxdo",
                subject=subject,
                email=email,
                username=username,
            )
        except Exception as exc:
            logger.error({
                "event": "linuxdo_oauth_callback_failed",
                "stage": "user_persist",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            raise
        exchange_code = secrets.token_urlsafe(32)
        with self._lock:
            self._prune_locked()
            self._exchange_codes[exchange_code] = (time.time() + 60, identity, raw_key)
        logger.info({
            "event": "linuxdo_oauth_callback_succeeded",
            "stage": "exchange_code",
            "user_id": identity.get("id"),
        })
        return exchange_code

    def exchange(self, code: str) -> tuple[dict[str, object], str]:
        with self._lock:
            self._prune_locked()
            record = self._exchange_codes.pop(code.strip(), None)
        if record is None:
            logger.warning({
                "event": "linuxdo_oauth_exchange_failed",
                "error": "OAuth 登录凭证已失效，请重新登录",
            })
            raise LinuxDoOAuthError("OAuth 登录凭证已失效，请重新登录")
        logger.info({
            "event": "linuxdo_oauth_exchange_succeeded",
            "user_id": record[1].get("id"),
        })
        return record[1], record[2]

    def _prune_locked(self) -> None:
        now = time.time()
        self._states = {key: value for key, value in self._states.items() if value[0] > now}
        self._exchange_codes = {key: value for key, value in self._exchange_codes.items() if value[0] > now}

    @staticmethod
    def _request_json(
        url: str,
        *,
        method: str = "GET",
        form: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        body = None
        request_headers = {"Accept": "application/json"}
        if form is not None:
            body = urlencode({key: str(value) for key, value in form.items()}).encode()
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request_headers.update(headers or {})
        try:
            request = Request(url, data=body, headers=request_headers, method=method)
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
        except HTTPError as exc:
            logger.warning({
                "event": "linuxdo_oauth_http_failed",
                "endpoint": urlsplit(url).path,
                "status_code": exc.code,
                "error_type": type(exc).__name__,
            })
            raise LinuxDoOAuthError("Linux.do 授权请求失败") from exc
        except Exception as exc:
            logger.warning({
                "event": "linuxdo_oauth_http_failed",
                "endpoint": urlsplit(url).path,
                "error_type": type(exc).__name__,
            })
            raise LinuxDoOAuthError("Linux.do 授权请求失败") from exc
        if not isinstance(payload, dict):
            raise LinuxDoOAuthError("Linux.do 返回了无效响应")
        return payload


linuxdo_oauth_service = LinuxDoOAuthService()
