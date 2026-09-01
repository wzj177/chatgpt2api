from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AuthRole = Literal["admin", "user", "unknown"]
AuthHomeRoute = Literal["/login", "/", "/studio"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthSubject(_StrictModel):
    id: str
    name: str
    role: AuthRole
    email: str | None = None
    created_at: str | None = None


class AuthCapabilities(_StrictModel):
    admin_console: bool = False
    studio: bool = False
    service_access: bool = False


class AuthView(_StrictModel):
    schema_version: Literal[1] = 1
    authenticated: bool
    version: str
    subject: AuthSubject | None
    capabilities: AuthCapabilities = Field(default_factory=AuthCapabilities)
    home_route: AuthHomeRoute
    access_token: str | None = None

    @model_validator(mode="after")
    def validate_session_shape(self) -> "AuthView":
        if self.authenticated:
            if self.subject is None:
                raise ValueError("authenticated sessions require a subject")
            if self.home_route == "/login":
                raise ValueError("authenticated sessions require an authenticated home route")
        else:
            if self.subject is not None:
                raise ValueError("anonymous sessions must not expose a subject")
            if self.capabilities.admin_console or self.capabilities.studio or self.capabilities.service_access:
                raise ValueError("anonymous sessions must not expose capabilities")
            if self.home_route != "/login":
                raise ValueError("anonymous sessions must use the login route")
        if self.capabilities.admin_console and self.subject and self.subject.role != "admin":
            raise ValueError("admin console capability requires the admin role")
        return self


class RegisterRequest(_StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=1, max_length=80)
    phone: str = ""
    captcha: str = ""
    accepted_terms: bool = False


class PasswordLoginRequest(_StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    captcha: str = ""


class PublicProtocolView(_StrictModel):
    markdown: str
    revision: str


class OAuthProviderView(_StrictModel):
    enabled: bool = False


class RegistrationConfigView(_StrictModel):
    enabled: bool = True


class OAuthExchangeRequest(_StrictModel):
    code: str = Field(min_length=1, max_length=256)


class UserKeyUpdateRequest(_StrictModel):
    name: str | None = None
    enabled: bool | None = None
    key: str | None = None


class UserKeyView(_StrictModel):
    id: str
    name: str
    role: Literal["admin", "user"]
    enabled: bool
    created_at: str | None = None
    last_used_at: str | None = None
    email: str | None = None
    phone: str | None = None
    usage_count: int = 0
    grok_usage_count: int = 0
    daily_image_count: int = 0
    daily_image_bonus: int = 0
    daily_image_remaining: int = 0
    daily_image_base_remaining: int = 0
    daily_grok_image_count: int = 0
    login_count: int = 0
    registration_source: str = "email"
    registration_source_label: str = "邮箱注册"


class UserKeyListView(_StrictModel):
    items: list[UserKeyView] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)


class UserKeyUpdateResult(_StrictModel):
    item: UserKeyView


class UserKeyDeleteResult(_StrictModel):
    deleted_id: str


class UserDailyImageAdjustmentRequest(_StrictModel):
    user_ids: list[str] = Field(min_length=1, max_length=100)
    count: int = Field(ge=1, le=10000)


class UserDailyImageAdjustmentResult(_StrictModel):
    items: list[UserKeyView] = Field(default_factory=list)
    count: int = Field(ge=1)
