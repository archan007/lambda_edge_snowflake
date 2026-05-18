"""
Pagination Utility
==================
Builds standard pagination metadata for API responses.
"""

from typing import Any, Dict


def build_pagination(total: int, page: int, limit: int) -> Dict[str, Any]:
    """
    Build pagination metadata.
    
    Args:
        total: Total number of records (across all pages)
        page: Current page number (1-indexed)
        limit: Records per page
        
    Returns:
        Pagination dictionary
    """
    total_pages = (total + limit - 1) // limit if limit > 0 else 0
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": total_pages,
    }
