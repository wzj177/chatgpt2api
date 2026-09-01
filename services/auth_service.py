from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Literal

from services.config import config
from services.storage.base import (
    StorageBackend,
    StorageMutation,
    StorageRevisionConflictError,
)
from utils.timezone import beijing_now

AuthRole = Literal["admin", "user"]
_CAS_ATTEMPTS = 4
_AUTH_SNAPSHOT_REFRESH_INTERVAL_SECONDS = 5.0
_AUTH_SNAPSHOT_MAX_STALE_SECONDS = 30.0


class ImageQuotaExceededError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    return beijing_now().date().isoformat()


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, storage: StorageBackend):
        self.storage = storage
        self._lock = Lock()
        self._snapshot_refresh_lock = Lock()
        self._items: list[dict[str, object]] = []
        self._revision: str | None = None
        self._last_used_flush_at: dict[str, datetime] = {}
        self._image_quota_reservations: dict[str, tuple[str, int]] = {}
        self._grok_quota_reservations: dict[str, tuple[str, int]] = {}
        self._last_snapshot_refresh_attempt_at = 0.0
        self._last_snapshot_refresh_success_at = 0.0
        self._reload_locked(suppress_errors=True)

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _default_name(role: object) -> str:
        return "管理员密钥" if str(role or "").strip().lower() == "admin" else "普通用户"

    def _normalize_item(self, raw: object) -> dict[str, object] | None:
        if not isinstance(raw, dict):
            return None
        role = self._clean(raw.get("role")).lower()
        if role not in {"admin", "user"}:
            return None
        key_hash = self._clean(raw.get("key_hash"))
        if not key_hash:
            return None
        item_id = self._clean(raw.get("id"))
        if not item_id:
            return None
        name = self._clean(raw.get("name")) or self._default_name(role)
        created_at = self._clean(raw.get("created_at")) or _now_iso()
        last_used_at = self._clean(raw.get("last_used_at")) or None
        email = self._clean(raw.get("email")).lower() or None
        oauth_provider = self._clean(raw.get("oauth_provider")).lower() or None
        registration_source = oauth_provider or self._clean(raw.get("registration_source")).lower()
        if not registration_source:
            registration_source = "email" if email else "admin"
        return {
            "id": item_id,
            "name": name,
            "role": role,
            "key_hash": key_hash,
            "enabled": bool(raw.get("enabled", True)),
            "created_at": created_at,
            "last_used_at": last_used_at,
            "email": email,
            "phone": self._clean(raw.get("phone")) or None,
            "password_hash": self._clean(raw.get("password_hash")) or None,
            "terms_accepted_at": self._clean(raw.get("terms_accepted_at")) or None,
            "usage_count": max(0, int(raw.get("usage_count") or 0)),
            "grok_usage_count": max(0, int(raw.get("grok_usage_count") or 0)),
            "daily_image_date": self._clean(raw.get("daily_image_date")) or None,
            "daily_image_count": max(0, int(raw.get("daily_image_count") or 0)),
            "daily_image_bonus": max(0, int(raw.get("daily_image_bonus") or 0)),
            "daily_grok_image_date": self._clean(raw.get("daily_grok_image_date")) or None,
            "daily_grok_image_count": max(0, int(raw.get("daily_grok_image_count") or 0)),
            "daily_grok_image_bonus": max(0, int(raw.get("daily_grok_image_bonus") or 0)),
            "login_count": max(0, int(raw.get("login_count") or 0)),
            "oauth_provider": oauth_provider,
            "oauth_subject": self._clean(raw.get("oauth_subject")) or None,
            "registration_source": registration_source,
        }

    def _load_snapshot(self) -> tuple[list[dict[str, object]], str]:
        snapshot = self.storage.load_auth_keys_snapshot()
        items = snapshot.items if isinstance(snapshot.items, list) else []
        normalized = [
            normalized_item
            for item in items
            if (normalized_item := self._normalize_item(item)) is not None
        ]
        return normalized, snapshot.revision

    def _reload_locked(self, *, suppress_errors: bool = False) -> bool:
        try:
            items, revision = self._load_snapshot()
        except Exception:
            if suppress_errors:
                return False
            raise
        self._items = items
        self._revision = revision
        refreshed_at = monotonic()
        self._last_snapshot_refresh_attempt_at = refreshed_at
        self._last_snapshot_refresh_success_at = refreshed_at
        return True

    def _snapshot_is_usable(self, now: float | None = None) -> bool:
        checked_at = monotonic() if now is None else now
        return (
            self._last_snapshot_refresh_success_at > 0
            and checked_at - self._last_snapshot_refresh_success_at
            <= _AUTH_SNAPSHOT_MAX_STALE_SECONDS
        )

    def _refresh_snapshot_if_due(self) -> bool:
        now = monotonic()
        if (
            now - self._last_snapshot_refresh_attempt_at
            < _AUTH_SNAPSHOT_REFRESH_INTERVAL_SECONDS
        ):
            return self._snapshot_is_usable(now)
        if not self._snapshot_refresh_lock.acquire(blocking=False):
            return self._snapshot_is_usable(now)
        try:
            now = monotonic()
            if (
                now - self._last_snapshot_refresh_attempt_at
                < _AUTH_SNAPSHOT_REFRESH_INTERVAL_SECONDS
            ):
                return self._snapshot_is_usable(now)
            self._last_snapshot_refresh_attempt_at = now
            with self._lock:
                expected_local_revision = self._revision
            try:
                items, revision = self._load_snapshot()
            except Exception:
                return self._snapshot_is_usable()
            with self._lock:
                if self._revision != expected_local_revision:
                    return self._snapshot_is_usable()
                self._items = items
                self._revision = revision
                self._last_snapshot_refresh_success_at = monotonic()
                active_ids = {self._clean(item.get("id")) for item in items}
                self._last_used_flush_at = {
                    item_id: flushed_at
                    for item_id, flushed_at in self._last_used_flush_at.items()
                    if item_id in active_ids
                }
                return True
        finally:
            self._snapshot_refresh_lock.release()

    def _set_cached_item_locked(self, item: dict[str, object], revision: str) -> None:
        item_id = self._clean(item.get("id"))
        self._items = [
            current
            for current in self._items
            if self._clean(current.get("id")) != item_id
        ]
        self._items.append(item)
        self._revision = revision

    def _delete_cached_item_locked(self, item_id: str, revision: str) -> None:
        self._items = [
            item
            for item in self._items
            if self._clean(item.get("id")) != item_id
        ]
        self._revision = revision

    def _find_item_index_locked(
        self,
        item_id: str,
        *,
        role: AuthRole | None = None,
    ) -> int | None:
        for index, item in enumerate(self._items):
            if self._clean(item.get("id")) != item_id:
                continue
            if role is not None and item.get("role") != role:
                return None
            return index
        return None

    def _find_hash_index_locked(self, candidate_hash: str) -> int | None:
        for index, item in enumerate(self._items):
            if not bool(item.get("enabled", True)):
                continue
            stored_hash = self._clean(item.get("key_hash"))
            if stored_hash and hmac.compare_digest(stored_hash, candidate_hash):
                return index
        return None

    @staticmethod
    def _public_item(item: dict[str, object]) -> dict[str, object]:
        daily_image_count = (
            int(item.get("daily_image_count") or 0)
            if str(item.get("daily_image_date") or "") == _today_iso()
            else 0
        )
        daily_image_bonus = (
            max(0, int(item.get("daily_image_bonus") or 0))
            if str(item.get("daily_image_date") or "") == _today_iso()
            else 0
        )
        source = str(item.get("oauth_provider") or item.get("registration_source") or ("email" if item.get("email") else "admin"))
        source_label = {
            "email": "邮箱注册",
            "linuxdo": "Linux.do",
            "admin": "管理员创建",
        }.get(source, source)
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "role": item.get("role"),
            "enabled": bool(item.get("enabled", True)),
            "created_at": item.get("created_at"),
            "last_used_at": item.get("last_used_at"),
            "email": item.get("email"),
            "phone": item.get("phone"),
            "usage_count": int(item.get("usage_count") or 0),
            "grok_usage_count": int(item.get("grok_usage_count") or 0),
            "daily_image_count": daily_image_count,
            "daily_image_bonus": daily_image_bonus,
            "daily_grok_image_count": (
                max(0, int(item.get("daily_grok_image_count") or 0))
                if str(item.get("daily_grok_image_date") or "") == _today_iso() else 0
            ),
            "daily_grok_image_bonus": (
                max(0, int(item.get("daily_grok_image_bonus") or 0))
                if str(item.get("daily_grok_image_date") or "") == _today_iso() else 0
            ),
            "login_count": int(item.get("login_count") or 0),
            "registration_source": source,
            "registration_source_label": source_label,
        }

    def is_grok_eligible(self, user_id: str) -> bool:
        if not self._clean(user_id):
            return False
        from services.protocol.grok_image_generations import is_grok_configured
        if not is_grok_configured():
            return False
        with self._lock:
            users = [
                item
                for item in self._items
                if item.get("role") == "user"
                and item.get("registration_source") == "linuxdo"
                and bool(item.get("enabled", True))
            ]
            users.sort(key=lambda item: max(0, int(item.get("usage_count") or 0)), reverse=True)
            limit = max(0, int(config.grok_image.get("linuxdo_user_limit") or 40))
            allowed = users if limit == 0 else users[:limit]
            return any(self._clean(item.get("id")) == self._clean(user_id) for item in allowed)

    def grok_daily_image_limit(self, user_id: str, configured_limit: int) -> int:
        if not self.is_grok_eligible(user_id):
            return 0
        with self._lock:
            self._reload_locked(suppress_errors=True)
            active_users = sum(
                1
                for candidate in self._items
                if candidate.get("role") == "user"
                and candidate.get("registration_source") == "linuxdo"
                and bool(candidate.get("enabled", True))
                and self._clean(candidate.get("last_used_at"))[:10] == _today_iso()
            )
        normalized = max(2, min(10, int(configured_limit or 10)))
        return max(2, min(10, (normalized * 40) // max(1, active_users)))

    def reserve_grok_images(self, user_id: str, count: int, limit: int) -> str:
        if not self.is_grok_eligible(user_id):
            raise ImageQuotaExceededError("当前账号没有 Grok 图片权限")
        requested = max(1, int(count or 1))
        with self._lock:
            self._reload_locked()
            index = self._find_item_index_locked(user_id, role="user")
            if index is None:
                raise ValueError("用户不存在或已被删除")
            item = self._items[index]
            used = max(0, int(item.get("daily_grok_image_count") or 0)) if self._clean(item.get("daily_grok_image_date")) == _today_iso() else 0
            bonus = max(0, int(item.get("daily_grok_image_bonus") or 0)) if self._clean(item.get("daily_grok_image_date")) == _today_iso() else 0
            reserved = sum(value for uid, value in self._grok_quota_reservations.values() if uid == user_id)
            configured_limit = max(2, min(10, int(limit or 10)))
            active_users = sum(
                1
                for candidate in self._items
                if candidate.get("role") == "user"
                and candidate.get("registration_source") == "linuxdo"
                and bool(candidate.get("enabled", True))
                and self._clean(candidate.get("last_used_at"))[:10] == _today_iso()
            )
            # Treat the configured maximum as a 40-user daily pool. More active
            # Linux.do users therefore reduce each user's dynamic allowance.
            effective = max(2, min(10, (configured_limit * 40) // max(1, active_users)))
            if used + reserved + requested > effective + bonus:
                raise ImageQuotaExceededError(f"今日 Grok 生图额度已用尽（{effective} 张）")
            reservation_id = uuid.uuid4().hex
            self._grok_quota_reservations[reservation_id] = (user_id, requested)
            return reservation_id

    def release_grok_images(self, reservation_id: str) -> None:
        with self._lock:
            self._grok_quota_reservations.pop(self._clean(reservation_id), None)

    def complete_grok_images(self, reservation_id: str, count: int) -> dict[str, object] | None:
        with self._lock:
            reservation = self._grok_quota_reservations.pop(self._clean(reservation_id), None)
        if reservation is None:
            return None
        user_id, reserved = reservation
        increment = min(reserved, max(0, int(count or 0)))
        if increment <= 0:
            return None
        with self._lock:
            index = self._find_item_index_locked(user_id, role="user")
            if index is None:
                return None
            item = dict(self._items[index])
            today = _today_iso()
            current = max(0, int(item.get("daily_grok_image_count") or 0)) if self._clean(item.get("daily_grok_image_date")) == today else 0
            current_bonus = max(0, int(item.get("daily_grok_image_bonus") or 0)) if self._clean(item.get("daily_grok_image_date")) == today else 0
            item["daily_grok_image_date"] = today
            item["daily_grok_image_count"] = current + increment
            item["daily_grok_image_bonus"] = current_bonus
            item["grok_usage_count"] = max(0, int(item.get("grok_usage_count") or 0)) + increment
            result = self.storage.mutate_auth_keys(StorageMutation(upserts=(item,), expected_revision=self._revision))
            self._set_cached_item_locked(item, result.revision)
            return self._public_item(item)

    def list_keys(self, role: AuthRole | None = None) -> list[dict[str, object]]:
        with self._lock:
            self._reload_locked(suppress_errors=True)
            items = [item for item in self._items if role is None or item.get("role") == role]
            return [self._public_item(item) for item in items]

    def list_keys_page(
        self,
        *,
        role: AuthRole | None = None,
        registration_source: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, object]:
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 20), 100))
        items = self.list_keys(role=role)
        needle = self._clean(keyword).lower()
        if needle:
            items = [
                item for item in items
                if needle in self._clean(item.get("email")).lower()
                or needle in self._clean(item.get("name")).lower()
            ]
        source = self._clean(registration_source).lower()
        if source and source != "all":
            items = [item for item in items if self._clean(item.get("registration_source")).lower() == source]
        daily_limit = max(0, int(config.user_daily_image_limit or 0))
        for item in items:
            daily_image_count = max(0, int(item.get("daily_image_count") or 0))
            daily_image_bonus = max(0, int(item.get("daily_image_bonus") or 0))
            item["daily_image_remaining"] = max(
                0,
                daily_limit + daily_image_bonus - daily_image_count,
            )
            item["daily_image_base_remaining"] = max(0, daily_limit - daily_image_count)
        start = (safe_page - 1) * safe_page_size
        return {
            "items": items[start:start + safe_page_size],
            "total": len(items),
            "page": safe_page,
            "page_size": safe_page_size,
        }

    def _has_key_hash_locked(self, key_hash: str, *, exclude_id: str = "") -> bool:
        for item in self._items:
            item_id = self._clean(item.get("id"))
            if exclude_id and item_id == exclude_id:
                continue
            stored_hash = self._clean(item.get("key_hash"))
            if stored_hash and hmac.compare_digest(stored_hash, key_hash):
                return True
        return False

    def _build_key_hash_locked(self, raw_key: str, *, exclude_id: str = "") -> str:
        candidate = self._clean(raw_key)
        if not candidate:
            raise ValueError("请输入新的专用密钥")
        admin_key = self._clean(config.auth_key)
        if admin_key and hmac.compare_digest(candidate, admin_key):
            raise ValueError("这个密钥和管理员密钥冲突了，请换一个新的密钥")
        key_hash = _hash_key(candidate)
        if self._has_key_hash_locked(key_hash, exclude_id=exclude_id):
            raise ValueError("这个专用密钥已经存在，请换一个新的密钥")
        return key_hash

    def _has_name_locked(self, name: str, *, role: AuthRole | None = None, exclude_id: str = "") -> bool:
        candidate = self._clean(name)
        if not candidate:
            return False
        for item in self._items:
            item_id = self._clean(item.get("id"))
            if exclude_id and item_id == exclude_id:
                continue
            if role is not None and item.get("role") != role:
                continue
            if self._clean(item.get("name")) == candidate:
                return True
        return False

    def _build_default_name_locked(self, role: AuthRole, *, exclude_id: str = "") -> str:
        base_name = self._default_name(role)
        if not self._has_name_locked(base_name, role=role, exclude_id=exclude_id):
            return base_name
        suffix = 2
        while True:
            candidate = f"{base_name} {suffix}"
            if not self._has_name_locked(candidate, role=role, exclude_id=exclude_id):
                return candidate
            suffix += 1

    def _build_name_locked(self, name: str, *, role: AuthRole, exclude_id: str = "") -> str:
        candidate = self._clean(name)
        if not candidate:
            return self._build_default_name_locked(role, exclude_id=exclude_id)
        if self._has_name_locked(candidate, role=role, exclude_id=exclude_id):
            raise ValueError("这个名称已经在使用中了，换一个更容易区分的名称吧")
        return candidate

    def create_key(self, *, role: AuthRole, name: str = "") -> tuple[dict[str, object], str]:
        with self._lock:
            for attempt in range(_CAS_ATTEMPTS):
                self._reload_locked()
                normalized_name = self._build_name_locked(name, role=role)
                while True:
                    raw_key = f"sk-{secrets.token_urlsafe(24)}"
                    try:
                        key_hash = self._build_key_hash_locked(raw_key)
                        break
                    except ValueError:
                        continue
                existing_ids = {self._clean(item.get("id")) for item in self._items}
                while True:
                    item_id = uuid.uuid4().hex[:12]
                    if item_id not in existing_ids:
                        break
                item = {
                    "id": item_id,
                    "name": normalized_name,
                    "role": role,
                    "key_hash": key_hash,
                    "enabled": True,
                    "created_at": _now_iso(),
                    "last_used_at": None,
                }
                try:
                    result = self.storage.mutate_auth_keys(
                        StorageMutation(
                            upserts=(item,),
                            expected_revision=self._revision,
                        )
                    )
                except StorageRevisionConflictError:
                    if attempt + 1 >= _CAS_ATTEMPTS:
                        raise
                    continue
                self._set_cached_item_locked(item, result.revision)
                return self._public_item(item), raw_key
        raise RuntimeError("auth key mutation retry exhausted")

    def update_key(
        self,
        key_id: str,
        updates: dict[str, object],
        *,
        role: AuthRole | None = None,
    ) -> dict[str, object] | None:
        normalized_id = self._clean(key_id)
        if not normalized_id:
            return None
        with self._lock:
            for attempt in range(_CAS_ATTEMPTS):
                self._reload_locked()
                index = self._find_item_index_locked(normalized_id, role=role)
                if index is None:
                    return None
                next_item = dict(self._items[index])
                next_role = "admin" if str(next_item.get("role") or "").strip().lower() == "admin" else "user"
                if "name" in updates and updates.get("name") is not None:
                    next_item["name"] = self._build_name_locked(
                        str(updates.get("name") or ""),
                        role=next_role,
                        exclude_id=normalized_id,
                    )
                if "enabled" in updates and updates.get("enabled") is not None:
                    next_item["enabled"] = bool(updates.get("enabled"))
                if "key" in updates and updates.get("key") is not None:
                    next_item["key_hash"] = self._build_key_hash_locked(str(updates.get("key") or ""), exclude_id=normalized_id)
                try:
                    result = self.storage.mutate_auth_keys(
                        StorageMutation(
                            upserts=(next_item,),
                            expected_revision=self._revision,
                        )
                    )
                except StorageRevisionConflictError:
                    if attempt + 1 >= _CAS_ATTEMPTS:
                        raise
                    continue
                self._set_cached_item_locked(next_item, result.revision)
                return self._public_item(next_item)
        return None

    def delete_key(self, key_id: str, *, role: AuthRole | None = None) -> bool:
        normalized_id = self._clean(key_id)
        if not normalized_id:
            return False
        with self._lock:
            for attempt in range(_CAS_ATTEMPTS):
                self._reload_locked()
                if self._find_item_index_locked(normalized_id, role=role) is None:
                    return False
                try:
                    result = self.storage.mutate_auth_keys(
                        StorageMutation(
                            delete_keys=(normalized_id,),
                            expected_revision=self._revision,
                        )
                    )
                except StorageRevisionConflictError:
                    if attempt + 1 >= _CAS_ATTEMPTS:
                        raise
                    continue
                self._delete_cached_item_locked(normalized_id, result.revision)
                self._last_used_flush_at.pop(normalized_id, None)
                return result.deleted > 0
        return False

    def authenticate(self, raw_key: str) -> dict[str, object] | None:
        candidate = self._clean(raw_key)
        if not candidate:
            return None
        candidate_hash = _hash_key(candidate)
        if not self._refresh_snapshot_if_due():
            return None
        with self._lock:
            now = datetime.now(timezone.utc)
            for attempt in range(_CAS_ATTEMPTS):
                index = self._find_hash_index_locked(candidate_hash)
                if index is None:
                    return None
                next_item = dict(self._items[index])
                next_item["last_used_at"] = now.isoformat()
                item_id = self._clean(next_item.get("id"))
                last_flush_at = self._last_used_flush_at.get(item_id)
                if last_flush_at is not None and (now - last_flush_at).total_seconds() < 60:
                    self._items[index] = next_item
                    return self._public_item(next_item)
                if self._revision is None:
                    self._items[index] = next_item
                    return self._public_item(next_item)
                try:
                    result = self.storage.mutate_auth_keys(
                        StorageMutation(
                            upserts=(next_item,),
                            expected_revision=self._revision,
                        )
                    )
                except StorageRevisionConflictError:
                    try:
                        self._reload_locked()
                    except Exception:
                        return None
                    refreshed_index = self._find_hash_index_locked(candidate_hash)
                    if refreshed_index is None:
                        return None
                    if attempt + 1 >= _CAS_ATTEMPTS:
                        validated_item = dict(self._items[refreshed_index])
                        validated_item["last_used_at"] = now.isoformat()
                        self._items[refreshed_index] = validated_item
                        return self._public_item(validated_item)
                    continue
                except Exception:
                    self._items[index] = next_item
                    return self._public_item(next_item)
                self._set_cached_item_locked(next_item, result.revision)
                self._last_used_flush_at[item_id] = now
                return self._public_item(next_item)
        return None

    @staticmethod
    def _password_hash(password: str, salt: str | None = None) -> str:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()
        return f"{salt}${digest}"

    @classmethod
    def _password_matches(cls, password: str, encoded: str) -> bool:
        salt, _, digest = encoded.partition("$")
        if not salt or not digest:
            return False
        candidate = cls._password_hash(password, salt).partition("$")[2]
        return hmac.compare_digest(candidate, digest)

    def register(self, *, email: str, password: str, username: str, phone: str = "", terms_accepted: bool = False) -> tuple[dict[str, object], str]:
        email = self._clean(email).lower()
        username = self._clean(username)
        phone = self._clean(phone)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("请输入有效的邮箱")
        if not username:
            raise ValueError("请输入用户名")
        if len(password) < 8:
            raise ValueError("密码至少需要 8 位")
        if not terms_accepted:
            raise ValueError("请先同意用户协议")
        with self._lock:
            self._reload_locked()
            if any(self._clean(item.get("email")).lower() == email for item in self._items):
                raise ValueError("该邮箱已经注册")
            raw_key = f"sk-{secrets.token_urlsafe(24)}"
            item = {
                "id": uuid.uuid4().hex[:12], "name": username, "role": "user",
                "key_hash": _hash_key(raw_key), "enabled": True,
                "created_at": _now_iso(), "last_used_at": _now_iso(),
                "email": email, "phone": phone or None,
                "password_hash": self._password_hash(password),
                "terms_accepted_at": _now_iso(), "usage_count": 0,
                "daily_image_date": _today_iso(), "daily_image_count": 0,
                "login_count": 0,
                "registration_source": "email",
            }
            result = self.storage.mutate_auth_keys(StorageMutation(upserts=(item,), expected_revision=self._revision))
            self._set_cached_item_locked(item, result.revision)
            return self._public_item(item), raw_key

    def authenticate_password(self, email: str, password: str) -> tuple[dict[str, object], str] | None:
        email = self._clean(email).lower()
        with self._lock:
            self._reload_locked()
            for item in self._items:
                if item.get("role") != "user" or self._clean(item.get("email")).lower() != email:
                    continue
                if not bool(item.get("enabled", True)) or not self._password_matches(password, self._clean(item.get("password_hash"))):
                    return None
                raw_key = f"sk-{secrets.token_urlsafe(24)}"
                next_item = dict(item)
                next_item["key_hash"] = _hash_key(raw_key)
                next_item["last_used_at"] = _now_iso()
                next_item["login_count"] = max(0, int(next_item.get("login_count") or 0)) + 1
                result = self.storage.mutate_auth_keys(StorageMutation(upserts=(next_item,), expected_revision=self._revision))
                self._set_cached_item_locked(next_item, result.revision)
                return self._public_item(next_item), raw_key
        return None

    def authenticate_oauth_user(
        self,
        *,
        provider: str,
        subject: str,
        email: str,
        username: str,
    ) -> tuple[dict[str, object], str]:
        provider = self._clean(provider).lower()
        subject = self._clean(subject)
        email = self._clean(email).lower()
        username = self._clean(username) or email.split("@", 1)[0]
        if not provider or not subject or not email:
            raise ValueError("第三方登录未返回完整用户身份")
        with self._lock:
            self._reload_locked()
            provider_matches = [
                idx for idx, item in enumerate(self._items)
                if item.get("role") == "user"
                and self._clean(item.get("oauth_provider")) == provider
                and self._clean(item.get("oauth_subject")) == subject
            ]
            email_matches = [
                idx for idx, item in enumerate(self._items)
                if self._clean(item.get("email")).lower() == email
            ]
            if len(provider_matches) > 1 or len(email_matches) > 1:
                raise ValueError("第三方登录身份数据重复，请联系管理员处理")
            if email_matches and self._items[email_matches[0]].get("role") != "user":
                raise ValueError("该邮箱已被管理员账号占用，无法绑定第三方登录")
            if provider_matches and email_matches and provider_matches[0] != email_matches[0]:
                raise ValueError("第三方登录身份与邮箱已绑定到不同用户")
            index = provider_matches[0] if provider_matches else (email_matches[0] if email_matches else None)
            raw_key = f"sk-{secrets.token_urlsafe(24)}"
            if index is None:
                item = {
                    "id": uuid.uuid4().hex[:12],
                    "name": username,
                    "role": "user",
                    "key_hash": _hash_key(raw_key),
                    "enabled": True,
                    "created_at": _now_iso(),
                    "last_used_at": _now_iso(),
                    "email": email,
                    "phone": None,
                    "password_hash": self._password_hash(secrets.token_urlsafe(32)),
                    "terms_accepted_at": _now_iso(),
                    "usage_count": 0,
                    "daily_image_date": _today_iso(),
                    "daily_image_count": 0,
                    "login_count": 1,
                    "oauth_provider": provider,
                    "oauth_subject": subject,
                    "registration_source": provider,
                }
            else:
                item = dict(self._items[index])
                if not bool(item.get("enabled", True)):
                    raise ValueError("账号已停用")
                item["key_hash"] = _hash_key(raw_key)
                item["last_used_at"] = _now_iso()
                item["login_count"] = max(0, int(item.get("login_count") or 0)) + 1
                item["name"] = item.get("name") or username
                item["oauth_provider"] = provider
                item["oauth_subject"] = subject
                if not self._clean(item.get("registration_source")):
                    item["registration_source"] = provider
            result = self.storage.mutate_auth_keys(
                StorageMutation(upserts=(item,), expected_revision=self._revision)
            )
            self._set_cached_item_locked(item, result.revision)
            return self._public_item(item), raw_key

    def record_login(self, user_id: str) -> dict[str, object] | None:
        normalized_id = self._clean(user_id)
        if not normalized_id:
            return None
        with self._lock:
            for attempt in range(_CAS_ATTEMPTS):
                self._reload_locked()
                index = self._find_item_index_locked(normalized_id)
                if index is None:
                    return None
                next_item = dict(self._items[index])
                next_item["login_count"] = max(0, int(next_item.get("login_count") or 0)) + 1
                try:
                    result = self.storage.mutate_auth_keys(
                        StorageMutation(upserts=(next_item,), expected_revision=self._revision)
                    )
                except StorageRevisionConflictError:
                    if attempt + 1 >= _CAS_ATTEMPTS:
                        raise
                    continue
                self._set_cached_item_locked(next_item, result.revision)
                return self._public_item(next_item)
        return None

    def successful_image_usage(self, user_id: str) -> tuple[int, int]:
        normalized_id = self._clean(user_id)
        if not normalized_id:
            return 0, 0
        with self._lock:
            self._reload_locked(suppress_errors=True)
            index = self._find_item_index_locked(normalized_id, role="user")
            if index is None:
                return 0, 0
            item = self._items[index]
            total = max(0, int(item.get("usage_count") or 0))
            daily = (
                max(0, int(item.get("daily_image_count") or 0))
                if self._clean(item.get("daily_image_date")) == _today_iso()
                else 0
            )
            return daily, total

    def reserve_successful_images(
        self,
        user_id: str,
        count: int,
        limit: int,
        global_limit: int | None = None,
    ) -> str:
        normalized_id = self._clean(user_id)
        requested = max(1, int(count or 1))
        normalized_limit = max(0, int(limit or 0))
        if not normalized_id:
            raise ValueError("用户身份无效")
        with self._lock:
            self._reload_locked()
            index = self._find_item_index_locked(normalized_id, role="user")
            if index is None:
                raise ValueError("用户不存在或已被删除")
            item = self._items[index]
            used = (
                max(0, int(item.get("daily_image_count") or 0))
                if self._clean(item.get("daily_image_date")) == _today_iso()
                else 0
            )
            bonus = (
                max(0, int(item.get("daily_image_bonus") or 0))
                if self._clean(item.get("daily_image_date")) == _today_iso()
                else 0
            )
            user_reserved = sum(
                reserved_count
                for reserved_user_id, reserved_count in self._image_quota_reservations.values()
                if reserved_user_id == normalized_id
            )
            global_reserved = sum(
                reserved_count
                for _reserved_user_id, reserved_count in self._image_quota_reservations.values()
            )
            effective_limit = normalized_limit + bonus
            if effective_limit and used + user_reserved + requested > effective_limit:
                raise ImageQuotaExceededError(f"今日生图额度已用尽（{effective_limit} 张）")
            if global_limit is not None and global_reserved + requested > max(0, int(global_limit)):
                raise ImageQuotaExceededError("当前账号池剩余总额度不足，请稍后再试")
            reservation_id = uuid.uuid4().hex
            self._image_quota_reservations[reservation_id] = (normalized_id, requested)
            return reservation_id

    def release_successful_images(self, reservation_id: str) -> None:
        normalized_id = self._clean(reservation_id)
        if not normalized_id:
            return
        with self._lock:
            self._image_quota_reservations.pop(normalized_id, None)

    def complete_successful_images(self, reservation_id: str, count: int) -> dict[str, object] | None:
        normalized_id = self._clean(reservation_id)
        succeeded = max(0, int(count or 0))
        if not normalized_id:
            return None
        with self._lock:
            reservation = self._image_quota_reservations.pop(normalized_id, None)
        if reservation is None or succeeded <= 0:
            return None
        user_id, reserved = reservation
        try:
            return self.record_successful_images(user_id, min(reserved, succeeded))
        except Exception:
            with self._lock:
                self._image_quota_reservations[normalized_id] = reservation
            raise

    def record_successful_images(self, user_id: str, count: int) -> dict[str, object] | None:
        normalized_id = self._clean(user_id)
        increment = max(0, int(count or 0))
        if not normalized_id or increment <= 0:
            return None
        with self._lock:
            for attempt in range(_CAS_ATTEMPTS):
                self._reload_locked()
                index = self._find_item_index_locked(normalized_id, role="user")
                if index is None:
                    return None
                next_item = dict(self._items[index])
                today = _today_iso()
                current_daily = (
                    max(0, int(next_item.get("daily_image_count") or 0))
                    if self._clean(next_item.get("daily_image_date")) == today
                    else 0
                )
                current_bonus = (
                    max(0, int(next_item.get("daily_image_bonus") or 0))
                    if self._clean(next_item.get("daily_image_date")) == today
                    else 0
                )
                next_item["usage_count"] = max(0, int(next_item.get("usage_count") or 0)) + increment
                next_item["daily_image_date"] = today
                next_item["daily_image_count"] = current_daily + increment
                next_item["daily_image_bonus"] = current_bonus
                try:
                    result = self.storage.mutate_auth_keys(
                        StorageMutation(
                            upserts=(next_item,),
                            expected_revision=self._revision,
                        )
                    )
                except StorageRevisionConflictError:
                    if attempt + 1 >= _CAS_ATTEMPTS:
                        raise
                    continue
                self._set_cached_item_locked(next_item, result.revision)
                return self._public_item(next_item)
        return None

    def add_daily_image_bonus(self, user_ids: list[str], count: int) -> list[dict[str, object]]:
        normalized_ids = list(dict.fromkeys(self._clean(value) for value in user_ids if self._clean(value)))
        increment = int(count or 0)
        if not normalized_ids:
            raise ValueError("请至少选择一个用户")
        if increment < 1 or increment > 10000:
            raise ValueError("增加次数必须在 1 到 10000 之间")
        with self._lock:
            for attempt in range(_CAS_ATTEMPTS):
                self._reload_locked()
                today = _today_iso()
                selected = set(normalized_ids)
                items = [item for item in self._items if item.get("role") == "user" and self._clean(item.get("id")) in selected]
                if len(items) != len(selected):
                    raise ValueError("部分用户不存在或已被删除，请刷新后重试")
                updates = []
                for item in items:
                    next_item = dict(item)
                    current_bonus = (
                        max(0, int(item.get("daily_image_bonus") or 0))
                        if self._clean(item.get("daily_image_date")) == today
                        else 0
                    )
                    next_item["daily_image_date"] = today
                    next_item["daily_image_bonus"] = current_bonus + increment
                    updates.append(next_item)
                try:
                    result = self.storage.mutate_auth_keys(
                        StorageMutation(upserts=tuple(updates), expected_revision=self._revision)
                    )
                except StorageRevisionConflictError:
                    if attempt + 1 >= _CAS_ATTEMPTS:
                        raise
                    continue
                self._items = [
                    next_item if self._clean(next_item.get("id")) in selected else next_item
                    for next_item in self._items
                ]
                for next_item in updates:
                    self._set_cached_item_locked(next_item, result.revision)
                return [self._public_item(item) for item in updates]
        raise RuntimeError("批量调整用户额度失败")

    def add_daily_grok_image_bonus(self, user_ids: list[str], count: int) -> list[dict[str, object]]:
        normalized_ids = list(dict.fromkeys(self._clean(value) for value in user_ids if self._clean(value)))
        increment = int(count or 0)
        if not normalized_ids:
            raise ValueError("请至少选择一个用户")
        if increment < 1 or increment > 10000:
            raise ValueError("增加次数必须在 1 到 10000 之间")
        with self._lock:
            for attempt in range(_CAS_ATTEMPTS):
                self._reload_locked()
                today = _today_iso()
                selected = set(normalized_ids)
                items = [item for item in self._items if item.get("role") == "user" and self._clean(item.get("id")) in selected]
                if len(items) != len(selected):
                    raise ValueError("部分用户不存在或已被删除，请刷新后重试")
                updates = []
                for item in items:
                    next_item = dict(item)
                    current_bonus = (
                        max(0, int(item.get("daily_grok_image_bonus") or 0))
                        if self._clean(item.get("daily_grok_image_date")) == today
                        else 0
                    )
                    next_item["daily_grok_image_date"] = today
                    next_item["daily_grok_image_bonus"] = current_bonus + increment
                    updates.append(next_item)
                try:
                    result = self.storage.mutate_auth_keys(
                        StorageMutation(upserts=tuple(updates), expected_revision=self._revision)
                    )
                except StorageRevisionConflictError:
                    if attempt + 1 >= _CAS_ATTEMPTS:
                        raise
                    continue
                for next_item in updates:
                    self._set_cached_item_locked(next_item, result.revision)
                return [self._public_item(item) for item in updates]
        raise RuntimeError("批量调整 Grok 额度失败")


auth_service = AuthService(config.get_storage_backend())
