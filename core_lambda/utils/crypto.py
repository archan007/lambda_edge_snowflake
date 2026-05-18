"""
Cryptography Utilities
======================
Helper functions for handling private keys for Snowflake key-pair authentication.
"""

from typing import Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization


def load_private_key(pem_content: str, passphrase: Optional[str] = None) -> bytes:
    """
    Load a PEM-formatted private key and convert to DER format for Snowflake.
    
    Args:
        pem_content: PEM-formatted private key string (with BEGIN/END markers)
        passphrase: Optional passphrase if the key is encrypted
        
    Returns:
        DER-encoded private key bytes (PKCS8 format) ready for Snowflake
    """
    passphrase_bytes = passphrase.encode() if passphrase else None
    
    private_key = serialization.load_pem_private_key(
        pem_content.encode(),
        password=passphrase_bytes,
        backend=default_backend()
    )
    
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
