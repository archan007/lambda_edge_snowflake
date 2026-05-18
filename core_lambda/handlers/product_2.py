"""
Product 2 Handlers (Placeholder)
================================
Handles all endpoints for Data Product 2.

Data Product: GOLD_CI (CreditSights)

Note how this handler queries a DIFFERENT schema than handlers/product_1.py.
This demonstrates how the same Lambda serves multiple data products
without separate connections.
"""

import logging
from typing import Any, Dict

from services.snowflake_client import snowflake_client
from utils.validators import validate_int, validate_string
from utils.converters import convert_rows_to_camel
from utils.pagination import build_pagination
from config.data_products import DataProduct
from config.enums import (
    DEFAULT_PAGE,
    DEFAULT_LIMIT,
    MIN_PAGE,
    MIN_LIMIT,
    MAX_LIMIT,
)

logger = logging.getLogger(__name__)

# This handler queries a different data product than product_1
SCHEMA = DataProduct.GOLD_CI


def list_endpoint_d(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """GET /endpoint-d - Generic list from GOLD_CI."""
    query = event.get("queryStringParameters") or {}
    
    page = validate_int(query.get("page"), "page", min_value=MIN_PAGE, default=DEFAULT_PAGE)
    limit = validate_int(query.get("limit"), "limit", min_value=MIN_LIMIT, max_value=MAX_LIMIT, default=DEFAULT_LIMIT)
    filter_param = validate_string(query.get("filter"), "filter", max_length=100)
    
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_list_endpoint_d",
        params=(page, limit, filter_param),
    )
    
    total = int(rows[0]["TOTAL_COUNT"]) if rows else 0
    for row in rows:
        row.pop("TOTAL_COUNT", None)
    
    return {
        "data": convert_rows_to_camel(rows),
        "pagination": build_pagination(total, page, limit),
    }


def get_endpoint_e_detail(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """GET /endpoint-e/{id} - Generic detail from GOLD_CI."""
    path_params = event.get("pathParameters") or {}
    item_id = validate_int(path_params.get("id"), "id", min_value=1)
    
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_endpoint_e_detail",
        params=(item_id,),
    )
    
    if not rows:
        from utils.exceptions import NotFoundError
        raise NotFoundError(f"Item {item_id} not found")
    
    return {"data": convert_rows_to_camel(rows)[0]}


def get_endpoint_f_metrics(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """GET /endpoint-f/metrics - Generic metrics from GOLD_CI."""
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_endpoint_f_metrics",
        params=(),
    )
    
    return {"data": convert_rows_to_camel(rows)}


def get_endpoint_g(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """GET /endpoint-g - Generic endpoint from GOLD_CI."""
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_endpoint_g",
        params=(),
    )
    
    return {"data": convert_rows_to_camel(rows)}
