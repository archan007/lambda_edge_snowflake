"""
Lambda Entry Point
==================
This is the ONLY file Lambda invokes directly.
It contains the lambda_handler function and delegates everything else to modules.

Responsibilities:
- Receive API Gateway event
- Route to appropriate handler based on path/method
- Return formatted response
- Handle top-level exceptions

Does NOT contain:
- Business logic (in handlers/)
- Snowflake logic (in services/)
- Validation logic (in utils/)
"""

import json
import logging
from typing import Any, Dict

from router import Router
from utils.response import create_response
from utils.exceptions import (
    UnauthorizedError,
    ValidationError,
    SnowflakeError,
    NotFoundError,
)

# Configure logging once
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize router once (reused across warm invocations)
router = Router()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda entry point.
    
    Routes incoming API Gateway requests to the appropriate handler.
    
    Args:
        event: API Gateway event object
        context: Lambda context object
        
    Returns:
        API Gateway response dictionary
    """
    request_id = context.aws_request_id if context else "local"
    logger.info(f"[{request_id}] Received request: {event.get('httpMethod')} {event.get('path')}")
    
    try:
        # Delegate to router - it figures out which handler to call
        result = router.route(event, context)
        return create_response(200, result, event)
    
    except UnauthorizedError as e:
        logger.warning(f"[{request_id}] Unauthorized: {str(e)}")
        return create_response(401, {"message": str(e)}, event)
    
    except ValidationError as e:
        logger.warning(f"[{request_id}] Validation error: {str(e)}")
        return create_response(402, {"message": str(e)}, event)
    
    except NotFoundError as e:
        logger.warning(f"[{request_id}] Not found: {str(e)}")
        return create_response(404, {"message": str(e)}, event)
    
    except SnowflakeError as e:
        logger.error(f"[{request_id}] Snowflake error: {str(e)}")
        return create_response(500, {"message": "Database error occurred"}, event)
    
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {str(e)}", exc_info=True)
        return create_response(500, {"message": "Internal server error"}, event)