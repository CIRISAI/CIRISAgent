"""Pin the SQL identifier allowlist on PrivacyTableMapping / PrivacyColumnMapping.

Defense-in-depth at the config-load boundary. The privacy schema is operator-
controlled today, but several call sites in service.py + dialects/* interpolate
table_name / column_name / identifier_column directly into SQL strings. If the
schema ever becomes user-editable this is the choke point.
"""

import pytest
from pydantic import ValidationError

from ciris_adapters.external_data_sql.schemas import (
    PrivacyColumnMapping,
    PrivacyTableMapping,
)


class TestIdentifierAllowlist:
    """Block SQL-injection-shaped strings at config parse time."""

    @pytest.mark.parametrize(
        "bad_table",
        [
            "users; DROP TABLE accounts;",
            "users--",
            "users' OR '1'='1",
            "users WHERE 1=1",
            "users.email",  # dotted identifier
            "users-table",  # hyphen
            "users table",  # whitespace
            "1users",  # digit start
            "",  # empty
            'users"',  # quote
        ],
    )
    def test_rejects_malicious_table_name(self, bad_table: str) -> None:
        with pytest.raises(ValidationError, match="invalid SQL identifier"):
            PrivacyTableMapping(
                table_name=bad_table,
                columns=[],
                identifier_column="user_id",
            )

    def test_rejects_malicious_identifier_column(self) -> None:
        with pytest.raises(ValidationError, match="invalid SQL identifier"):
            PrivacyTableMapping(
                table_name="users",
                columns=[],
                identifier_column="id; DELETE FROM users",
            )

    def test_rejects_malicious_column_name(self) -> None:
        with pytest.raises(ValidationError, match="invalid SQL identifier"):
            PrivacyColumnMapping(
                column_name="email; DROP TABLE accounts",
                data_type="email",
            )

    def test_rejects_malicious_cascade_delete(self) -> None:
        with pytest.raises(ValidationError, match="invalid SQL identifier"):
            PrivacyTableMapping(
                table_name="users",
                columns=[],
                identifier_column="user_id",
                cascade_deletes=["sessions; DROP TABLE accounts"],
            )

    def test_accepts_normal_identifiers(self) -> None:
        # Sanity check — these were the example_config.json values that were
        # already shipping. Don't break existing operator configs.
        mapping = PrivacyTableMapping(
            table_name="users",
            columns=[
                PrivacyColumnMapping(column_name="email", data_type="email"),
                PrivacyColumnMapping(column_name="full_name", data_type="name"),
                PrivacyColumnMapping(column_name="_internal_flag", data_type="flag"),
            ],
            identifier_column="user_id",
            cascade_deletes=["user_sessions", "user_preferences"],
        )
        assert mapping.table_name == "users"
        assert mapping.identifier_column == "user_id"
        assert mapping.cascade_deletes == ["user_sessions", "user_preferences"]
