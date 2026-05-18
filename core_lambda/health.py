"""
Health Check Handler
====================
Called by ALB every 30 seconds to verify Lambda is alive.
Must return 200 quickly — no Snowflake calls, no auth needed.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def health_check(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /health

    Returns 200 immediately.
    ALB uses this to determine if Lambda is healthy.
    No auth required — ALB calls this without Authorization header.
    """
    logger.debug("Health check called")
    return {"status": "healthy"}