"""
Data Product Configuration
==========================
Centralized definitions of Snowflake schemas (data products).

Each data product = one Snowflake schema containing related stored procedures.
This separation reflects the data mesh / data product architecture pattern.

To add a new data product:
1. Add the schema name as a constant below
2. Use it in your handler when calling stored procedures
"""


class DataProduct:
    """
    Snowflake schema names for each data product.
    
    These map to actual schema names in Snowflake (database is set per environment
    via Secrets Manager).
    
    Usage in handler:
        from config.data_products import DataProduct
        
        snowflake_client.call_procedure(
            schema=DataProduct.GOLD_C360,
            procedure_name="sp_account_summary",
            params=(...)
        )
    """
    
    # Customer 360 - account, customer, and engagement data
    GOLD_C360 = "GOLD_C360"

    # CreditSights data product
    GOLD_CI = "GOLD_CI"

    # Shared reference / lookup data (e.g. account managers, regions)
    GOLD = "GOLD"

    # Add more as needed:
    # GOLD_RDR = "GOLD_RDR"
    # GOLD_ANALYTICS = "GOLD_ANALYTICS"
    # GOLD_RESEARCH = "GOLD_RESEARCH"


# List of all valid data products (used for validation if needed)
ALL_DATA_PRODUCTS = [
    DataProduct.GOLD_C360,
    DataProduct.GOLD_CI,
    DataProduct.GOLD,
]
