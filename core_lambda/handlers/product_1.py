"""
Product 1 Handlers (Placeholder)
================================
Handles all endpoints for Data Product 1.

Data Product: GOLD_C360 (or change as needed)

Replace this file's contents with your actual endpoint implementations.
This is a generic template showing the pattern.
"""

import logging
from typing import Any, Dict

from services.snowflake_client import snowflake_client
from utils.validators import validate_int
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

# Data product this handler serves
SCHEMA = DataProduct.GOLD_C360


def list_endpoint_a(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /endpoint-a
    
    Generic paginated list endpoint - replace with actual logic.
    """
    query = event.get("queryStringParameters") or {}
    
    page = validate_int(query.get("page"), "page", min_value=MIN_PAGE, default=DEFAULT_PAGE)
    limit = validate_int(query.get("limit"), "limit", min_value=MIN_LIMIT, max_value=MAX_LIMIT, default=DEFAULT_LIMIT)
    
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_list_endpoint_a",
        params=(page, limit),
    )
    
    total = int(rows[0]["TOTAL_COUNT"]) if rows else 0
    for row in rows:
        row.pop("TOTAL_COUNT", None)
    
    return {
        "data": convert_rows_to_camel(rows),
        "pagination": build_pagination(total, page, limit),
    }


def get_endpoint_b_detail(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /endpoint-b/{id}
    
    Generic detail endpoint - replace with actual logic.
    """
    path_params = event.get("pathParameters") or {}
    item_id = validate_int(path_params.get("id"), "id", min_value=1)
    
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_endpoint_b_detail",
        params=(item_id,),
    )
    
    if not rows:
        from utils.exceptions import NotFoundError
        raise NotFoundError(f"Item {item_id} not found")
    
    return {"data": convert_rows_to_camel(rows)[0]}


def get_endpoint_c_summary(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /endpoint-c/summary
    
    Generic summary endpoint - replace with actual logic.
    """
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_endpoint_c_summary",
        params=(),
    )
    
    return {"data": convert_rows_to_camel(rows)}
