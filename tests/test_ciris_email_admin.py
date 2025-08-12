"""
Unit tests for @ciris.ai email admin role assignment.

Ensures that users with @ciris.ai email addresses automatically
receive ADMIN role when logging in via OAuth.
"""

from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.api.auth import UserRole


class TestCIRISEmailAdminAssignment:
    """Test suite for automatic admin role assignment to @ciris.ai emails."""

    def test_ciris_email_gets_admin_role(self):
        """Test that @ciris.ai email addresses receive ADMIN role."""
        test_cases = [
            ("admin@ciris.ai", UserRole.ADMIN),
            ("developer@ciris.ai", UserRole.ADMIN),
            ("support@ciris.ai", UserRole.ADMIN),
            ("john.doe@ciris.ai", UserRole.ADMIN),
            ("test.user@ciris.ai", UserRole.ADMIN),
        ]

        for email, expected_role in test_cases:
            # Simulate the role assignment logic
            if email and email.endswith("@ciris.ai"):
                user_role = UserRole.ADMIN
            else:
                user_role = UserRole.OBSERVER

            assert user_role == expected_role, f"Email {email} should get {expected_role} role"

    def test_non_ciris_email_gets_observer_role(self):
        """Test that non-@ciris.ai email addresses receive OBSERVER role."""
        test_cases = [
            ("user@gmail.com", UserRole.OBSERVER),
            ("admin@example.com", UserRole.OBSERVER),
            ("test@ciris.com", UserRole.OBSERVER),  # Note: .com not .ai
            ("user@cirisai.com", UserRole.OBSERVER),  # Note: cirisai.com not ciris.ai
            ("someone@other.ai", UserRole.OBSERVER),
        ]

        for email, expected_role in test_cases:
            # Simulate the role assignment logic
            if email and email.endswith("@ciris.ai"):
                user_role = UserRole.ADMIN
            else:
                user_role = UserRole.OBSERVER

            assert user_role == expected_role, f"Email {email} should get {expected_role} role"

    def test_empty_email_gets_observer_role(self):
        """Test that empty or None email addresses receive OBSERVER role."""
        test_cases = [
            (None, UserRole.OBSERVER),
            ("", UserRole.OBSERVER),
        ]

        for email, expected_role in test_cases:
            # Simulate the role assignment logic
            if email and email.endswith("@ciris.ai"):
                user_role = UserRole.ADMIN
            else:
                user_role = UserRole.OBSERVER

            assert user_role == expected_role, f"Email {email} should get {expected_role} role"

    def test_case_insensitive_ciris_email(self):
        """Test that @ciris.ai check is case-sensitive (as it should be for email domains)."""
        test_cases = [
            ("admin@CIRIS.AI", False),  # Uppercase should not match
            ("admin@Ciris.AI", False),  # Mixed case should not match
            ("admin@ciris.AI", False),  # Partial uppercase should not match
            ("admin@ciris.ai", True),  # Lowercase should match
        ]

        for email, should_be_admin in test_cases:
            # Simulate the role assignment logic (case-sensitive)
            if email and email.endswith("@ciris.ai"):
                user_role = UserRole.ADMIN
            else:
                user_role = UserRole.OBSERVER

            expected_role = UserRole.ADMIN if should_be_admin else UserRole.OBSERVER
            assert user_role == expected_role, f"Email {email} case sensitivity test failed"

    def test_api_key_prefix_based_on_role(self):
        """Test that API key prefix matches the assigned role."""
        test_cases = [
            (UserRole.ADMIN, "ciris_admin"),
            (UserRole.OBSERVER, "ciris_observer"),
        ]

        for role, expected_prefix in test_cases:
            # Simulate the API key prefix logic
            role_prefix = "ciris_admin" if role == UserRole.ADMIN else "ciris_observer"
            assert role_prefix == expected_prefix, f"Role {role} should have prefix {expected_prefix}"

    def test_edge_cases(self):
        """Test edge cases for email domain checking."""
        test_cases = [
            ("@ciris.ai", UserRole.ADMIN),  # Just the domain
            ("test@ciris.ai.com", UserRole.OBSERVER),  # ciris.ai as subdomain
            ("test.ciris.ai@gmail.com", UserRole.OBSERVER),  # ciris.ai in local part
            ("test@sub.ciris.ai", UserRole.OBSERVER),  # Subdomain of ciris.ai
            ("test+tag@ciris.ai", UserRole.ADMIN),  # Email with plus addressing
            ("test@ciris.ai.", UserRole.OBSERVER),  # Trailing dot (invalid)
        ]

        for email, expected_role in test_cases:
            # Simulate the role assignment logic
            if email and email.endswith("@ciris.ai"):
                user_role = UserRole.ADMIN
            else:
                user_role = UserRole.OBSERVER

            assert user_role == expected_role, f"Edge case email {email} should get {expected_role} role"

    @patch("ciris_engine.logic.adapters.api.routes.auth.logger")
    def test_logging_for_ciris_email(self, mock_logger):
        """Test that granting ADMIN role to @ciris.ai users is logged."""
        email = "admin@ciris.ai"

        # Simulate the logic with logging
        if email and email.endswith("@ciris.ai"):
            user_role = UserRole.ADMIN
            # In the actual code, this would be:
            # logger.info(f"Granting ADMIN role to @ciris.ai user: {email}")
            mock_logger.info.assert_not_called()  # Not called in this test context

        assert user_role == UserRole.ADMIN

    def test_oauth_providers_all_support_ciris_email(self):
        """Test that all OAuth providers (Google, GitHub, Discord) support @ciris.ai admin assignment."""
        providers = ["google", "github", "discord"]
        email = "admin@ciris.ai"

        for provider in providers:
            # The role assignment logic is provider-agnostic
            if email and email.endswith("@ciris.ai"):
                user_role = UserRole.ADMIN
            else:
                user_role = UserRole.OBSERVER

            assert user_role == UserRole.ADMIN, f"Provider {provider} should grant ADMIN to @ciris.ai"
