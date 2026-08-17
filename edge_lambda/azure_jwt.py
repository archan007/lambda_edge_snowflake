"""
Azure AD (Entra ID) Bearer Token Verification
==============================================
Verifies RS256-signed access tokens issued by Azure Entra ID, using only the
Python standard library.

Why not PyJWT / python-jose:
  Lambda@Edge viewer-request functions are capped at a 1 MB deployment
  package (AWS hard limit — origin-request/response get 50 MB, viewer
  functions don't). Both PyJWT and python-jose pull in `cryptography`, a
  compiled C-extension package that blows past that budget on its own, and
  deploy_edge.sh / deploy-edge.yml have no pip-install/vendoring step to
  bring in a dependency in the first place.

  RSASSA-PKCS1-v1_5 signature verification (RFC 8017 §8.2.2) is a
  well-defined operation we can do directly with `hashlib` and Python's
  built-in arbitrary-precision `pow()` for the modular exponentiation —
  no extra package required.

What this checks:
  - Signature (RS256 only) against Azure's published JWKS
  - exp / nbf (with a small clock-skew leeway)
  - aud == configured client_id
  - iss == the tenant's v1 or v2 issuer URL

What this does NOT do (out of scope for an edge auth gate):
  - Token revocation / introspection (Azure access tokens are short-lived;
    rely on `exp`)
  - Scope/role authorization — that's the core Lambda's job
"""

import base64
import hashlib
import hmac
import json
import time
import urllib.request
from urllib.error import URLError

# ASN.1 DER prefix for a SHA-256 DigestInfo structure (RFC 8017, PKCS#1 v1.5).
_SHA256_DIGESTINFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")

_JWKS_CACHE_TTL_SECONDS = 24 * 60 * 60  # Azure rotates signing keys infrequently.
_CLOCK_SKEW_LEEWAY_SECONDS = 60

# Module-level cache. Lambda@Edge reuses warm containers, so this survives
# across invocations within the same edge-location container.
_jwks_cache = {"keys_by_kid": {}, "fetched_at": 0.0}


def _b64url_decode(segment):
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _fetch_jwks(tenant_id, timeout=2.0):
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = json.loads(resp.read())

    keys_by_kid = {}
    for jwk in data.get("keys", []):
        kid = jwk.get("kid")
        if not kid or jwk.get("kty") != "RSA":
            continue
        n = int.from_bytes(_b64url_decode(jwk["n"]), "big")
        e = int.from_bytes(_b64url_decode(jwk["e"]), "big")
        keys_by_kid[kid] = (n, e)
    return keys_by_kid


def _get_signing_key(tenant_id, kid):
    now = time.time()
    stale = (now - _jwks_cache["fetched_at"]) > _JWKS_CACHE_TTL_SECONDS
    if not _jwks_cache["keys_by_kid"] or stale:
        _jwks_cache["keys_by_kid"] = _fetch_jwks(tenant_id)
        _jwks_cache["fetched_at"] = now

    key = _jwks_cache["keys_by_kid"].get(kid)
    if key is None:
        # kid not found — could be a key rotated in since our last fetch.
        # Refresh once before giving up rather than waiting out the TTL.
        _jwks_cache["keys_by_kid"] = _fetch_jwks(tenant_id)
        _jwks_cache["fetched_at"] = time.time()
        key = _jwks_cache["keys_by_kid"].get(kid)
    return key


def _rsa_pkcs1_v15_verify(message, signature, n, e):
    """RSASSA-PKCS1-v1_5 verify with SHA-256, per RFC 8017 section 8.2.2."""
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False

    sig_int = int.from_bytes(signature, "big")
    if sig_int >= n:
        return False

    em = pow(sig_int, e, n).to_bytes(k, "big")

    digest = hashlib.sha256(message).digest()
    ps_len = k - len(_SHA256_DIGESTINFO_PREFIX) - len(digest) - 3
    if ps_len < 8:
        return False
    expected_em = b"\x00\x01" + b"\xff" * ps_len + b"\x00" + _SHA256_DIGESTINFO_PREFIX + digest

    return hmac.compare_digest(em, expected_em)


def verify_azure_jwt(token, tenant_id, client_id):
    """
    Verify an Azure Entra ID RS256 access token.

    Returns (True, claims, None) on success, or (False, None, error_message).
    """
    parts = token.split(".")
    if len(parts) != 3:
        return False, None, "Malformed token"
    header_b64, payload_b64, sig_b64 = parts

    try:
        header = json.loads(_b64url_decode(header_b64))
        claims = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(sig_b64)
    except Exception:
        return False, None, "Malformed token"

    if header.get("alg") != "RS256":
        return False, None, f"Unsupported alg: {header.get('alg')}"

    kid = header.get("kid")
    if not kid:
        return False, None, "Missing kid in token header"

    try:
        key = _get_signing_key(tenant_id, kid)
    except (URLError, OSError, ValueError):
        return False, None, "Unable to fetch signing keys"

    if key is None:
        return False, None, "Unknown signing key"

    n, e = key
    signed_message = f"{header_b64}.{payload_b64}".encode("ascii")
    if not _rsa_pkcs1_v15_verify(signed_message, signature, n, e):
        return False, None, "Invalid signature"

    now = time.time()

    exp = claims.get("exp")
    if exp is None or now > exp + _CLOCK_SKEW_LEEWAY_SECONDS:
        return False, None, "Token expired"

    nbf = claims.get("nbf")
    if nbf is not None and now < nbf - _CLOCK_SKEW_LEEWAY_SECONDS:
        return False, None, "Token not yet valid"

    if claims.get("aud") != client_id:
        return False, None, "Token audience mismatch"

    # v1 tokens: https://sts.windows.net/{tenant}/  v2 tokens: .../v2.0
    valid_issuers = (
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        f"https://sts.windows.net/{tenant_id}/",
    )
    if claims.get("iss") not in valid_issuers:
        return False, None, "Token issuer mismatch"

    return True, claims, None
