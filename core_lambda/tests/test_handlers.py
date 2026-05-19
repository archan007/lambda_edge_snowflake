"""
Sample Unit Tests
=================
Demonstrates how the modular structure enables easy unit testing.

Run with: pytest tests/ -v
"""

import pytest
from unittest.mock import patch

from utils.validators import validate_enum, validate_int
from utils.exceptions import ValidationError, NotFoundError, UnauthorizedError
from utils.converters import snake_to_camel, convert_row_keys_to_camel
from utils.pagination import build_pagination
from config.data_products import DataProduct


# ============================================================
# Pure utility tests (no mocking needed)
# ============================================================

class TestValidators:
    def test_validate_enum_valid(self):
        result = validate_enum("emea", "regionKey", ["emea", "apac"])
        assert result == "emea"
    
    def test_validate_enum_invalid(self):
        with pytest.raises(ValidationError, match="Invalid value for regionKey"):
            validate_enum("invalid", "regionKey", ["emea", "apac"])
    
    def test_validate_enum_optional_none(self):
        result = validate_enum(None, "regionKey", ["emea", "apac"], required=False)
        assert result is None
    
    def test_validate_int_with_default(self):
        result = validate_int(None, "page", default=1)
        assert result == 1
    
    def test_validate_int_out_of_bounds(self):
        with pytest.raises(ValidationError, match="must be <= 100"):
            validate_int(150, "limit", max_value=100)


class TestConverters:
    def test_snake_to_camel(self):
        assert snake_to_camel("ACCOUNT_NAME") == "accountName"
        assert snake_to_camel("annual_contract_value") == "annualContractValue"
        assert snake_to_camel("id") == "id"
    
    def test_convert_row_keys(self):
        row = {"ACCOUNT_ID": 1, "ACCOUNT_NAME": "Goldman"}
        result = convert_row_keys_to_camel(row)
        assert result == {"accountId": 1, "accountName": "Goldman"}


class TestPagination:
    def test_basic_pagination(self):
        result = build_pagination(total=100, page=2, limit=25)
        assert result == {
            "total": 100,
            "page": 2,
            "limit": 25,
            "totalPages": 4,
        }
    
    def test_partial_last_page(self):
        result = build_pagination(total=27, page=2, limit=25)
        assert result["totalPages"] == 2


class TestDataProducts:
    def test_data_product_constants(self):
        assert DataProduct.GOLD_C360 == "GOLD_C360"
        assert DataProduct.GOLD_CI == "GOLD_CI"


# ============================================================
# Handler tests (with mocked Snowflake)
# ============================================================

class TestAccountsHandler:
    @patch("handlers.accounts.snowflake_client")
    def test_get_account_summary_uses_correct_schema(self, mock_client):
        """Verify handler calls Snowflake with correct schema (data product)."""
        mock_client.call_procedure.return_value = (
            [{"ID": 1, "ACCOUNT_NAME": "Goldman", "TOTAL_COUNT": 1}],
            [],
        )
        
        from handlers.accounts import get_account_summary
        
        event = {"queryStringParameters": {"page": "1", "limit": "10"}}
        result = get_account_summary(event, None)
        
        # Verify the call was made with GOLD_C360 schema
        call_args = mock_client.call_procedure.call_args
        assert call_args.kwargs["schema"] == "GOLD_C360"
        assert call_args.kwargs["procedure_name"] == "sp_account_summary"
        
        # Verify response structure
        assert "data" in result
        assert "pagination" in result
        assert result["data"][0]["accountName"] == "Goldman"
    
    @patch("handlers.accounts.snowflake_client")
    def test_get_account_summary_invalid_region(self, mock_client):
        from handlers.accounts import get_account_summary
        
        event = {"queryStringParameters": {"regionKey": "invalid-region"}}
        
        with pytest.raises(ValidationError):
            get_account_summary(event, None)
    
    @patch("handlers.accounts.snowflake_client")
    def test_account_detail_not_found(self, mock_client):
        mock_client.call_procedure.return_value = ([], [])

        from handlers.accounts import get_account_detail

        event = {"pathParameters": {"id": "999"}}

        with pytest.raises(NotFoundError):
            get_account_detail(event, None)

    @patch("handlers.accounts.snowflake_client")
    def test_get_portfolio(self, mock_client):
        import json
        payload = {"summary": {"total": 5}, "segments": ["A", "B"]}
        mock_client.call_procedure.return_value = (
            [{"SP_GET_PORTFOLIO": json.dumps(payload)}],
            [],
        )

        from handlers.accounts import get_portfolio

        event = {"queryStringParameters": {"regionKey": "emea", "status": "active"}}
        result = get_portfolio(event, None)

        call_args = mock_client.call_procedure.call_args
        assert call_args.kwargs["schema"] == "GOLD"
        assert call_args.kwargs["procedure_name"] == "SP_GET_PORTFOLIO"
        assert len(call_args.kwargs["params"]) == 9

        assert "data" in result
        assert "pagination" not in result
        assert result["data"] == payload

    @patch("handlers.accounts.snowflake_client")
    def test_get_portfolio_empty(self, mock_client):
        mock_client.call_procedure.return_value = ([], [])

        from handlers.accounts import get_portfolio

        result = get_portfolio({}, None)
        assert result == {"data": {}}

    @patch("handlers.accounts.snowflake_client")
    def test_get_account_managers(self, mock_client):
        mock_client.call_procedure.return_value = (
            [
                {"ACCOUNT_MANAGER_KEY": "am-001", "ACCOUNT_MANAGER_NAME": "Jane Smith"},
                {"ACCOUNT_MANAGER_KEY": "am-002", "ACCOUNT_MANAGER_NAME": "John Doe"},
            ],
            [],
        )

        from handlers.accounts import get_account_managers

        result = get_account_managers({}, None)

        call_args = mock_client.call_procedure.call_args
        assert call_args.kwargs["schema"] == "GOLD"
        assert call_args.kwargs["procedure_name"] == "GET_ACCOUNT_MANAGERS"
        assert call_args.kwargs["params"] == ()

        assert "data" in result
        assert "pagination" not in result
        assert result["data"][0] == {"accountManagerKey": "am-001", "accountManagerName": "Jane Smith"}
        assert result["data"][1] == {"accountManagerKey": "am-002", "accountManagerName": "John Doe"}


class TestProduct2Handler:
    @patch("handlers.product_2.snowflake_client")
    def test_uses_different_schema(self, mock_client):
        """Verify product_2 handler uses GOLD_CI schema (different from accounts)."""
        mock_client.call_procedure.return_value = (
            [{"ID": 1, "TOTAL_COUNT": 1}],
            [],
        )
        
        from handlers.product_2 import list_endpoint_d
        
        event = {"queryStringParameters": {}}
        list_endpoint_d(event, None)
        
        call_args = mock_client.call_procedure.call_args
        assert call_args.kwargs["schema"] == "GOLD_CI"


# ============================================================
# Router tests
# ============================================================

class TestRouter:
    @patch("router.validate_authorization")
    @patch("handlers.accounts.snowflake_client")
    def test_route_to_account_summary(self, mock_client, mock_auth):
        mock_client.call_procedure.return_value = ([{"TOTAL_COUNT": 0}], [])
        mock_auth.return_value = None
        
        from router import Router
        router = Router()
        
        event = {
            "httpMethod": "GET",
            "path": "/account-summary",
            "queryStringParameters": {"page": "1"},
            "headers": {"Authorization": "Bearer test"},
        }
        
        result = router.route(event, None)
        assert "data" in result
    
    @patch("router.validate_authorization")
    def test_route_not_found(self, mock_auth):
        from router import Router
        
        router = Router()
        
        event = {
            "httpMethod": "GET",
            "path": "/nonexistent",
            "headers": {"Authorization": "Bearer test"},
        }
        
        with pytest.raises(NotFoundError):
            router.route(event, None)
    
    @patch("router.validate_authorization")
    def test_method_mismatch_returns_404(self, mock_auth):
        """If path exists but method doesn't match, returns NotFound."""
        from router import Router
        
        router = Router()
        
        event = {
            "httpMethod": "POST",  # Path exists for GET, not POST
            "path": "/account-summary",
            "headers": {"Authorization": "Bearer test"},
        }
        
        with pytest.raises(NotFoundError):
            router.route(event, None)
    
    def test_path_pattern_compilation(self):
        from router import Router
        router = Router()
        
        pattern = router._compile_pattern("/accounts/{id}")
        match = pattern.match("/accounts/123")
        assert match is not None
        assert match.group("id") == "123"
    
    def test_list_routes(self):
        """Verify routes can be enumerated (useful for /docs endpoint)."""
        from router import Router
        router = Router()
        
        routes = router.list_routes()
        assert len(routes) >= 12  # 12 routes registered

        paths = [path for _, path in routes]
        assert "/account-summary" in paths
        assert "/account-managers" in paths
        assert "/portfolio" in paths
        assert "/accounts/{id}" in paths


# ============================================================
# Auth tests
# ============================================================

class TestAuth:
    def test_missing_auth_header(self):
        from utils.auth import validate_authorization
        
        event = {"headers": {}}
        
        with pytest.raises(UnauthorizedError, match="Missing authorization"):
            validate_authorization(event)
    
    def test_invalid_format(self):
        from utils.auth import validate_authorization
        
        event = {"headers": {"Authorization": "InvalidFormat token"}}
        
        with pytest.raises(UnauthorizedError, match="Invalid authorization format"):
            validate_authorization(event)
    
    def test_valid_bearer_token(self):
        from utils.auth import validate_authorization
        
        event = {"headers": {"Authorization": "Bearer valid-token-123"}}
        
        # Should not raise
        validate_authorization(event)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
