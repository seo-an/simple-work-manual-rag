import unittest
from unittest.mock import Mock

from simple_work_manual_rag.auth.contracts import AuthStatus, TokenPair
from simple_work_manual_rag.auth.errors import (
    AccessExpired, AccessInvalid, LoginRejected,
    RefreshExpired, RefreshInvalid, RefreshReused,
)
from simple_work_manual_rag.auth.flow import AuthFlow


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.access = Mock()
        self.refresh = Mock()
        self.identity = Mock()
        self.issuer = Mock()
        self.access.verify.return_value = "user-1"
        self.refresh.rotate.return_value = TokenPair("new-access", "new-refresh", "user-1")
        self.identity.authenticate.return_value = "user-1"
        self.issuer.issue.return_value = TokenPair("first-access", "first-refresh", "user-1")
        self.flow = AuthFlow(self.access, self.refresh, self.identity, self.issuer)

    def test_no_tokens_no_login_means_login_required(self):
        result = self.flow.handle()
        self.assertEqual(result.status, AuthStatus.LOGIN_REQUIRED)
        self.assertEqual(result.reason, "no_credentials")
        self.assertTrue(result.clear_credentials)
        self.issuer.issue.assert_not_called()

    def test_no_tokens_after_verified_login_issues_pair(self):
        result = self.flow.handle(login_evidence="test-verified-login")
        self.assertEqual(result.status, AuthStatus.ISSUED)
        self.assertEqual(result.tokens.access_token, "first-access")
        self.identity.authenticate.assert_called_once_with("test-verified-login")
        self.issuer.issue.assert_called_once_with("user-1")

    def test_invalid_login_never_issues_pair(self):
        self.identity.authenticate.side_effect = LoginRejected()
        result = self.flow.handle(login_evidence="bad")
        self.assertEqual(result.reason, "login_rejected")
        self.issuer.issue.assert_not_called()

    def test_both_tokens_valid_access_skips_refresh(self):
        result = self.flow.handle(access_token="valid-access", refresh_token="valid-refresh")
        self.assertEqual(result.status, AuthStatus.AUTHORIZED)
        self.assertEqual(result.subject, "user-1")
        self.refresh.rotate.assert_not_called()

    def test_valid_access_alone_is_allowed(self):
        result = self.flow.handle(access_token="valid-access")
        self.assertEqual(result.status, AuthStatus.AUTHORIZED)

    def test_expired_access_and_valid_refresh_rotates_pair(self):
        self.access.verify.side_effect = AccessExpired()
        result = self.flow.handle(access_token="expired", refresh_token="refresh")
        self.assertEqual(result.status, AuthStatus.REFRESHED)
        self.assertEqual(result.tokens.refresh_token, "new-refresh")
        self.refresh.rotate.assert_called_once_with("refresh")

    def test_expired_access_without_refresh_requires_login(self):
        self.access.verify.side_effect = AccessExpired()
        result = self.flow.handle(access_token="expired")
        self.assertEqual(result.reason, "refresh_missing")

    def test_expired_access_and_expired_refresh_requires_login(self):
        self.access.verify.side_effect = AccessExpired()
        self.refresh.rotate.side_effect = RefreshExpired()
        result = self.flow.handle(access_token="expired", refresh_token="expired-refresh")
        self.assertEqual(result.reason, "refresh_expired")
        self.assertTrue(result.clear_credentials)

    def test_expired_access_and_invalid_refresh_requires_login(self):
        self.access.verify.side_effect = AccessExpired()
        self.refresh.rotate.side_effect = RefreshInvalid()
        result = self.flow.handle(access_token="expired", refresh_token="invalid-refresh")
        self.assertEqual(result.reason, "refresh_invalid")

    def test_expired_access_and_reused_refresh_requires_login(self):
        self.access.verify.side_effect = AccessExpired()
        self.refresh.rotate.side_effect = RefreshReused()
        result = self.flow.handle(access_token="expired", refresh_token="reused-refresh")
        self.assertEqual(result.reason, "refresh_reused")

    def test_missing_access_valid_refresh_rotates_pair(self):
        result = self.flow.handle(refresh_token="refresh")
        self.assertEqual(result.status, AuthStatus.REFRESHED)

    def test_missing_access_invalid_refresh_requires_login(self):
        self.refresh.rotate.side_effect = RefreshInvalid()
        result = self.flow.handle(refresh_token="invalid")
        self.assertEqual(result.status, AuthStatus.LOGIN_REQUIRED)

    def test_tampered_access_must_not_fall_back_to_refresh(self):
        self.access.verify.side_effect = AccessInvalid()
        result = self.flow.handle(access_token="tampered", refresh_token="valid-refresh")
        self.assertEqual(result.reason, "access_invalid")
        self.refresh.rotate.assert_not_called()

    def test_valid_access_ignores_invalid_refresh_until_renewal(self):
        self.refresh.rotate.side_effect = RefreshInvalid()
        result = self.flow.handle(access_token="valid-access", refresh_token="invalid-refresh")
        self.assertEqual(result.status, AuthStatus.AUTHORIZED)
        self.refresh.rotate.assert_not_called()

    def test_blank_tokens_without_login_requires_login(self):
        result = self.flow.handle(access_token=" ", refresh_token=" ")
        self.assertEqual(result.reason, "no_credentials")

    def test_incomplete_issued_pair_is_not_accepted(self):
        self.issuer.issue.return_value = TokenPair("token", "", "user-1")
        with self.assertRaises(RuntimeError):
            self.flow.handle(login_evidence="test-verified-login")

    def test_infrastructure_failure_does_not_count_as_bad_credentials(self):
        self.refresh.rotate.side_effect = ConnectionError("session backend down")
        with self.assertRaises(ConnectionError):
            self.flow.handle(refresh_token="refresh")


if __name__ == "__main__":
    unittest.main()
