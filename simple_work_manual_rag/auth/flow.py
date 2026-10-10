"""API/프레임워크와 분리한 인증 상태 머신.

이 파일은 인증 흐름만 구현한다. 암호 검증, JWT 서명 검증, 발급,
Refresh Token 해시 저장 및 원자적 회전은 주입되는 구현체의 책임이다.
"""
from __future__ import annotations

from .contracts import (
    AccessVerifier, AuthResult, AuthStatus, IdentityProvider,
    RefreshRotator, TokenIssuer,
)
from .errors import (
    AccessExpired, AccessInvalid, LoginRejected, RefreshExpired,
    RefreshInvalid, RefreshReused,
)


class AuthFlow:
    def __init__(
        self,
        access_verifier: AccessVerifier,
        refresh_rotator: RefreshRotator,
        identity_provider: IdentityProvider,
        token_issuer: TokenIssuer,
    ):
        self.access_verifier = access_verifier
        self.refresh_rotator = refresh_rotator
        self.identity_provider = identity_provider
        self.token_issuer = token_issuer

    def handle(
        self,
        *,
        access_token: str | None = None,
        refresh_token: str | None = None,
        login_evidence: object | None = None,
    ) -> AuthResult:
        access_token = access_token if access_token and access_token.strip() else None
        refresh_token = refresh_token if refresh_token and refresh_token.strip() else None

        if access_token:
            try:
                subject = self.access_verifier.verify(access_token)
                if not subject:
                    raise AccessInvalid()
            except AccessExpired:
                return self._refresh(refresh_token)
            except AccessInvalid:
                return self._login_required("access_invalid")
            return AuthResult(
                status=AuthStatus.AUTHORIZED,
                reason="access_valid",
                subject=subject,
            )

        if refresh_token:
            return self._refresh(refresh_token)

        if login_evidence is None:
            return self._login_required("no_credentials")

        try:
            subject = self.identity_provider.authenticate(login_evidence)
            if not subject:
                raise LoginRejected()
        except LoginRejected:
            return self._login_required("login_rejected")
        pair = self.token_issuer.issue(subject)
        self._check_pair(pair)
        return AuthResult(
            status=AuthStatus.ISSUED,
            reason="login_verified",
            subject=pair.subject,
            tokens=pair,
        )

    def _refresh(self, refresh_token: str | None) -> AuthResult:
        if not refresh_token:
            return self._login_required("refresh_missing")
        try:
            pair = self.refresh_rotator.rotate(refresh_token)
        except RefreshExpired:
            return self._login_required("refresh_expired")
        except RefreshReused:
            return self._login_required("refresh_reused")
        except RefreshInvalid:
            return self._login_required("refresh_invalid")
        self._check_pair(pair)
        return AuthResult(
            status=AuthStatus.REFRESHED,
            reason="refresh_rotated",
            subject=pair.subject,
            tokens=pair,
        )

    @staticmethod
    def _check_pair(pair: object) -> None:
        if not all((
            getattr(pair, "access_token", None),
            getattr(pair, "refresh_token", None),
            getattr(pair, "subject", None),
        )):
            raise RuntimeError("Authentication provider returned an incomplete token pair")

    @staticmethod
    def _login_required(reason: str) -> AuthResult:
        return AuthResult(
            status=AuthStatus.LOGIN_REQUIRED,
            reason=reason,
            clear_credentials=True,
        )
