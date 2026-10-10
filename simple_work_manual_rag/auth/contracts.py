"""토큰 구현체(JWT, 세션 저장소 등)와 독립적인 인증 계약."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class AuthStatus(str, Enum):
    AUTHORIZED = "authorized"
    ISSUED = "issued"
    REFRESHED = "refreshed"
    LOGIN_REQUIRED = "login_required"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    subject: str


@dataclass(frozen=True)
class AuthResult:
    status: AuthStatus
    reason: str
    subject: str | None = None
    tokens: TokenPair | None = None
    clear_credentials: bool = False


class AccessVerifier(Protocol):
    def verify(self, access_token: str) -> str:
        """서명, 만료, issuer, audience, token type, 세션 상태 검증 후 subject 반환."""


class RefreshRotator(Protocol):
    def rotate(self, refresh_token: str) -> TokenPair:
        """토큰 검증 + 원자적 교체 + 재사용 감지 및 계열 폐기."""


class IdentityProvider(Protocol):
    def authenticate(self, login_evidence: object) -> str:
        """신뢰 가능한 로그인 증빙을 검증하고 subject 반환."""


class TokenIssuer(Protocol):
    def issue(self, subject: str) -> TokenPair:
        """신원 확인을 마친 대상에게만 토큰 쌍을 발급."""
