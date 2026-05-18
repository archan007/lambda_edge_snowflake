"""
Enum Definitions
================
Centralized definition of allowed values for validation.

Adding a new allowed value? Update it here, all endpoints automatically use it.
"""

# Region keys
REGION_KEYS = ["north-america", "emea", "apac", "latam"]

# Segment keys
SEGMENT_KEYS = ["enterprise", "mid-market", "smb"]

# Primary products
PRIMARY_PRODUCTS = ["CreditSights", "RDR", "Analytics", "Research"]

# Usage trend directions
USAGE_TRENDS = ["declining", "stable", "growing"]

# Account health statuses
ACCOUNT_STATUSES = ["critical", "at-risk", "healthy", "excellent"]

# Sort fields for account summary
ACCOUNT_SORT_FIELDS = [
    "default",
    "name",
    "risk-value",
    "acv",
    "renewal-date",
    "last-touch",
]

# Sort fields for opportunities
OPPORTUNITY_SORT_FIELDS = [
    "default",
    "value",
    "close-date",
    "stage",
    "probability",
]

# Sort fields for renewals
RENEWAL_SORT_FIELDS = [
    "default",
    "renewal-date",
    "value",
    "risk",
]

# Sort orders
SORT_ORDERS = ["asc", "desc"]

# Pagination limits
MIN_PAGE = 1
MIN_LIMIT = 1
MAX_LIMIT = 100
DEFAULT_LIMIT = 25
DEFAULT_PAGE = 1
