"""인증 공급자 어댑터가 반환하는 분류된 오류."""

class AuthenticationError(Exception):
    """사용자에게 민감한 세부정보를 노출하지 않는 인증 실패의 공통형."""


class LoginRejected(AuthenticationError):
    pass


class AccessExpired(AuthenticationError):
    pass


class AccessInvalid(AuthenticationError):
    pass


class RefreshExpired(AuthenticationError):
    pass


class RefreshInvalid(AuthenticationError):
    pass


class RefreshReused(AuthenticationError):
    """공급자는 이 오류를 반환하기 전에 관련 토큰 계열을 폐기해야 한다."""
