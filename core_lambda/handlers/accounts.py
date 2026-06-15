"""
Account Handlers
================
Handles all /accounts/* endpoints.

Data Product: GOLD_C360 (Customer 360)

Each handler:
1. Declares which data product (schema) it queries
2. Parses and validates input
3. Calls the appropriate stored procedure
4. Formats and returns response
"""

import json
import logging
from typing import Any, Dict

from services.snowflake_client import snowflake_client
from utils.validators import validate_enum, validate_int, validate_string
from utils.converters import convert_rows_to_camel
from utils.pagination import build_pagination
from config.data_products import DataProduct
from config.enums import (
    REGION_KEYS,
    SEGMENT_KEYS,
    PRIMARY_PRODUCTS,
    USAGE_TRENDS,
    ACCOUNT_STATUSES,
    ACCOUNT_SORT_FIELDS,
    SORT_ORDERS,
    DEFAULT_PAGE,
    DEFAULT_LIMIT,
    MIN_PAGE,
    MIN_LIMIT,
    MAX_LIMIT,
)

logger = logging.getLogger(__name__)

# All account endpoints query the Customer 360 data product
SCHEMA = DataProduct.GOLD


def get_account_summary(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /account-summary
    
    Returns paginated list of accounts with health/risk summary data.
    Source: GOLD_C360.sp_account_summary
    """
    query = event.get("queryStringParameters") or {}
    
    # Validate all parameters
    page = validate_int(query.get("page"), "page", min_value=MIN_PAGE, default=DEFAULT_PAGE)
    limit = validate_int(query.get("limit"), "limit", min_value=MIN_LIMIT, max_value=MAX_LIMIT, default=DEFAULT_LIMIT)
    search = validate_string(query.get("search"), "search", max_length=200)
    account_manager_key = validate_string(query.get("accountManagerKey"), "accountManagerKey", max_length=100)
    region_key = validate_enum(query.get("regionKey"), "regionKey", REGION_KEYS)
    segment_key = validate_enum(query.get("segmentKey"), "segmentKey", SEGMENT_KEYS)
    product = validate_enum(query.get("product"), "product", PRIMARY_PRODUCTS)
    usage_trend = validate_enum(query.get("usageTrend"), "usageTrend", USAGE_TRENDS)
    renewal_days_min = validate_int(query.get("renewalDaysMin"), "renewalDaysMin", min_value=0)
    renewal_days_max = validate_int(query.get("renewalDaysMax"), "renewalDaysMax", min_value=0)
    status = validate_enum(query.get("status"), "status", ACCOUNT_STATUSES)
    sort = validate_enum(query.get("sort"), "sort", ACCOUNT_SORT_FIELDS) or "default"
    sort_order = validate_enum(query.get("sortOrder"), "sortOrder", SORT_ORDERS) or "desc"
    
    # Stored procedure parameters in order matching SP signature
    proc_params = (
        page, limit, search, account_manager_key, region_key, segment_key,
        product, usage_trend, renewal_days_min, renewal_days_max,
        status, sort, sort_order,
    )
    
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_account_summary",
        params=proc_params,
    )
    
    # Extract total count (assumes SP returns TOTAL_COUNT in each row)
    total = int(rows[0]["TOTAL_COUNT"]) if rows else 0
    for row in rows:
        row.pop("TOTAL_COUNT", None)
    
    return {
        "data": convert_rows_to_camel(rows),
        "pagination": build_pagination(total, page, limit),
    }


def get_account_detail(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /accounts/{id}

    Returns detailed information for a single account as Snowflake-serialized JSON.
    Source: GOLD.sp_get_account_details
    """
    path_params = event.get("pathParameters") or {}
    account_id = validate_string(path_params.get("id"), "id", max_length=100)

    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_get_account_details",
        params=(account_id,),
    )

    if not rows:
        return {"data": {}}

    raw = list(rows[0].values())[0]
    return {"data": json.loads(raw)}


def get_customer_overview(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /accounts/{id}/overview

    Returns customer overview as Snowflake-serialized JSON.
    Source: GOLD.sp_get_customer_overview
    """
    path_params = event.get("pathParameters") or {}
    account_id = validate_string(path_params.get("id"), "id", max_length=100)

    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_get_customer_overview",
        params=(account_id,),
    )

    if not rows:
        return {"data": {}}

    raw = list(rows[0].values())[0]
    return {"data": json.loads(raw)}


def get_revenue_history(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /revenue-history/{id}

    Returns customer revenue history as Snowflake-serialized JSON.
    Source: GOLD.GET_CUSTOMER_REVENUE_HISTORY
    """
    path_params = event.get("pathParameters") or {}
    account_id = validate_string(path_params.get("id"), "id", max_length=100)

    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="GET_CUSTOMER_REVENUE_HISTORY",
        params=(account_id,),
    )

    if not rows:
        return {"data": {}}

    raw = list(rows[0].values())[0]
    return {"data": json.loads(raw)}


def get_account_activities(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /accounts/{id}/activities
    
    Returns activity history for a specific account.
    Source: GOLD_C360.sp_account_activities
    """
    path_params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    
    account_id = validate_int(path_params.get("id"), "id", min_value=1)
    page = validate_int(query.get("page"), "page", min_value=MIN_PAGE, default=DEFAULT_PAGE)
    limit = validate_int(query.get("limit"), "limit", min_value=MIN_LIMIT, max_value=MAX_LIMIT, default=DEFAULT_LIMIT)
    
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_account_activities",
        params=(account_id, page, limit),
    )
    
    total = int(rows[0]["TOTAL_COUNT"]) if rows else 0
    for row in rows:
        row.pop("TOTAL_COUNT", None)
    
    return {
        "data": convert_rows_to_camel(rows),
        "pagination": build_pagination(total, page, limit),
    }


def get_portfolio(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /portfolio

    Returns complex portfolio data serialized as JSON by Snowflake itself.
    Source: GOLD.SP_GET_PORTFOLIO
    """
    query = event.get("queryStringParameters") or {}

    search = validate_string(query.get("search"), "search", max_length=200)
    account_manager_key = validate_string(query.get("accountManagerKey"), "accountManagerKey", max_length=100)
    region_key = validate_enum(query.get("regionKey"), "regionKey", REGION_KEYS)
    segment_key = validate_enum(query.get("segmentKey"), "segmentKey", SEGMENT_KEYS)
    product = validate_enum(query.get("product"), "product", PRIMARY_PRODUCTS)
    usage_trend = validate_enum(query.get("usageTrend"), "usageTrend", USAGE_TRENDS)
    renewal_days_min = validate_int(query.get("renewalDaysMin"), "renewalDaysMin", min_value=0)
    renewal_days_max = validate_int(query.get("renewalDaysMax"), "renewalDaysMax", min_value=0)
    status = validate_enum(query.get("status"), "status", ACCOUNT_STATUSES)

    proc_params = (
        search, account_manager_key, region_key, segment_key,
        product, usage_trend, renewal_days_min, renewal_days_max, status,
    )

    rows, _ = snowflake_client.call_procedure(
        schema=DataProduct.GOLD,
        procedure_name="SP_GET_PORTFOLIO",
        params=proc_params,
    )

    if not rows:
        return {"data": {}}

    # Snowflake returns the JSON as a single value in the first row.
    # Column name is unpredictable for expression results, so grab by position.
    raw = list(rows[0].values())[0]
    return {"data": json.loads(raw)}


def get_account_managers(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /account-managers

    Returns the full list of account managers for filter population.
    Source: GOLD.GET_ACCOUNT_MANAGERS()
    """
    rows, _ = snowflake_client.call_procedure(
        schema=DataProduct.GOLD,
        procedure_name="GET_ACCOUNT_MANAGERS",
        params=(),
    )

    return {"data": convert_rows_to_camel(rows)}


def get_account_team_regions(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /account-team-region

    Returns the full list of account team regions for dropdown population.
    Source: GOLD.GET_ACCOUNT_TEAM_REGIONS()
    """
    rows, _ = snowflake_client.call_procedure(
        schema=DataProduct.GOLD,
        procedure_name="GET_ACCOUNT_TEAM_REGIONS",
        params=(),
    )

    raw = list(rows[0].values())[0]
    return json.loads(raw)


# ============================================================
# FUTURE: POST/PUT examples (placeholder)
# ============================================================

def update_account_status(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    PUT /accounts/{id}/status
    
    Updates an account's status. Example of a write endpoint.
    Source: GOLD_C360.sp_update_account_status
    
    Note: Add JSON body parsing when implementing.
    """
    import json
    
    path_params = event.get("pathParameters") or {}
    account_id = validate_int(path_params.get("id"), "id", min_value=1)
    
    # Parse JSON body
    body_str = event.get("body") or "{}"
    body = json.loads(body_str)
    
    new_status = validate_enum(body.get("status"), "status", ACCOUNT_STATUSES, required=True)
    reason = validate_string(body.get("reason"), "reason", max_length=500)
    
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_update_account_status",
        params=(account_id, new_status, reason),
    )
    
    return {
        "message": "Account status updated successfully",
        "accountId": account_id,
        "newStatus": new_status,
    }
