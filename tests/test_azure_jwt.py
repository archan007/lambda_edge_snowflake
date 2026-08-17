"""
Unit Tests for azure_jwt.py
===========================
azure_jwt.py hand-rolls RS256 verification (stdlib only — see its module
docstring for why). These tests exercise that logic directly against a
real self-signed token, rather than mocking the crypto away.

To build a real RS256 token without adding a dependency, this file
includes a minimal pure-Python RSA keypair generator (test-only, small key
size for speed — not suitable for anything but signing test fixtures).
"""

import base64
import hashlib
import json
import os
import random
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "edge_lambda"))

import azure_jwt  # noqa: E402

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
KID = "test-kid-1"


# ---------------------------------------------------------------------------
# Minimal RSA keypair generation + PKCS#1 v1.5 signing, for test fixtures only
# ---------------------------------------------------------------------------
def _is_probable_prime(n, rounds=20):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits):
    while True:
        candidate = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def _generate_rsa_keypair(bits=512):
    e = 65537
    while True:
        p = _gen_prime(bits // 2)
        q = _gen_prime(bits // 2)
        if p == q:
            continue
        n = p * q
        phi = (p - 1) * (q - 1)
        if phi % e == 0:
            continue
        d = pow(e, -1, phi)
        if n.bit_length() >= bits - 1:
            return (n, e), (n, d)


def _b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _rsa_pkcs1_v15_sign(message, n, d):
    k = (n.bit_length() + 7) // 8
    digest = hashlib.sha256(message).digest()
    ps_len = k - len(azure_jwt._SHA256_DIGESTINFO_PREFIX) - len(digest) - 3
    em = b"\x00\x01" + b"\xff" * ps_len + b"\x00" + azure_jwt._SHA256_DIGESTINFO_PREFIX + digest
    sig_int = pow(int.from_bytes(em, "big"), d, n)
    return sig_int.to_bytes(k, "big")


def _make_token(public_key, private_key, kid=KID, claim_overrides=None, alg="RS256"):
    now = int(time.time())
    header = {"alg": alg, "kid": kid, "typ": "JWT"}
    claims = {
        "aud": CLIENT_ID,
        "iss": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        "exp": now + 3600,
        "nbf": now - 10,
        "sub": "test-user",
    }
    claims.update(claim_overrides or {})

    header_b64 = _b64url_encode(json.dumps(header).encode())
    payload_b64 = _b64url_encode(json.dumps(claims).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    n, d = private_key
    signature = _rsa_pkcs1_v15_sign(signing_input, n, d)
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


class TestAzureJwtVerification:
    @classmethod
    def setup_class(cls):
        random.seed(1234)  # deterministic, fast keygen for tests
        cls.public_key, cls.private_key = _generate_rsa_keypair(bits=512)

    def _with_cached_key(self):
        return patch.dict(
            azure_jwt._jwks_cache,
            {"keys_by_kid": {KID: self.public_key}, "fetched_at": time.time()},
        )

    def test_valid_token_verifies(self):
        token = _make_token(self.public_key, self.private_key)
        with self._with_cached_key():
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is True
        assert error is None
        assert claims["sub"] == "test-user"

    def test_tampered_payload_fails_signature(self):
        token = _make_token(self.public_key, self.private_key)
        header_b64, payload_b64, sig_b64 = token.split(".")
        tampered_claims = json.loads(azure_jwt._b64url_decode(payload_b64))
        tampered_claims["sub"] = "attacker"
        tampered_payload_b64 = _b64url_encode(json.dumps(tampered_claims).encode())
        tampered_token = f"{header_b64}.{tampered_payload_b64}.{sig_b64}"

        with self._with_cached_key():
            ok, claims, error = azure_jwt.verify_azure_jwt(tampered_token, TENANT_ID, CLIENT_ID)
        assert ok is False
        assert error == "Invalid signature"

    def test_expired_token_rejected(self):
        token = _make_token(self.public_key, self.private_key, claim_overrides={"exp": int(time.time()) - 3600})
        with self._with_cached_key():
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is False
        assert error == "Token expired"

    def test_not_yet_valid_token_rejected(self):
        token = _make_token(self.public_key, self.private_key, claim_overrides={"nbf": int(time.time()) + 3600})
        with self._with_cached_key():
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is False
        assert error == "Token not yet valid"

    def test_wrong_audience_rejected(self):
        token = _make_token(self.public_key, self.private_key, claim_overrides={"aud": "some-other-client-id"})
        with self._with_cached_key():
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is False
        assert error == "Token audience mismatch"

    def test_wrong_issuer_rejected(self):
        token = _make_token(
            self.public_key, self.private_key,
            claim_overrides={"iss": "https://login.microsoftonline.com/some-other-tenant/v2.0"},
        )
        with self._with_cached_key():
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is False
        assert error == "Token issuer mismatch"

    def test_v1_issuer_format_accepted(self):
        token = _make_token(
            self.public_key, self.private_key,
            claim_overrides={"iss": f"https://sts.windows.net/{TENANT_ID}/"},
        )
        with self._with_cached_key():
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is True

    def test_unsupported_algorithm_rejected(self):
        token = _make_token(self.public_key, self.private_key, alg="HS256")
        with self._with_cached_key():
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is False
        assert "Unsupported alg" in error

    def test_unknown_kid_rejected(self):
        token = _make_token(self.public_key, self.private_key, kid="some-unknown-kid")
        with self._with_cached_key(), patch.object(azure_jwt, "_fetch_jwks", return_value={}):
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is False
        assert error == "Unknown signing key"

    def test_malformed_token_rejected(self):
        ok, claims, error = azure_jwt.verify_azure_jwt("not-a-jwt", TENANT_ID, CLIENT_ID)
        assert ok is False
        assert error == "Malformed token"

    def test_jwks_fetch_failure_fails_closed(self):
        with patch.dict(azure_jwt._jwks_cache, {"keys_by_kid": {}, "fetched_at": 0.0}), \
             patch.object(azure_jwt, "_fetch_jwks", side_effect=OSError("network unreachable")):
            token = _make_token(self.public_key, self.private_key)
            ok, claims, error = azure_jwt.verify_azure_jwt(token, TENANT_ID, CLIENT_ID)
        assert ok is False
        assert error == "Unable to fetch signing keys"
