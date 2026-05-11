"""
LRSI V11.1 — Audit Signing Adapters
====================================

Production-near audit records need identity-bound signatures.  V11.1 keeps the
legacy HMAC path for development compatibility, but adds an Ed25519 public-key
adapter with explicit signer identity and public-key material.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Protocol, cast


class SigningAdapter(Protocol):
    """Minimal signing/verifying contract for audit records and seals."""

    algorithm: str
    signer_id: str

    def sign(self, payload: bytes) -> str: ...

    def public_metadata(self) -> dict: ...

    def verify(self, payload: bytes, signature: str, metadata: dict | None = None) -> bool: ...


@dataclass
class NoopSigningAdapter:
    algorithm: str = "none"
    signer_id: str = "unsigned"

    def sign(self, payload: bytes) -> str:  # noqa: ARG002
        return ""

    def public_metadata(self) -> dict:
        return {"audit_signature_algorithm": self.algorithm, "audit_signer_id": self.signer_id}

    def verify(self, payload: bytes, signature: str, metadata: dict | None = None) -> bool:  # noqa: ARG002
        return signature == ""


@dataclass
class HMACSigningAdapter:
    """Compatibility adapter for local/dev signing."""

    key: str
    signer_id: str = "local-hmac-runtime"
    algorithm: str = "HMAC-SHA256(record_hash)"

    def sign(self, payload: bytes) -> str:
        return hmac.new(self.key.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    def public_metadata(self) -> dict:
        return {
            "audit_signature_algorithm": self.algorithm,
            "audit_signer_id": self.signer_id,
        }

    def verify(self, payload: bytes, signature: str, metadata: dict | None = None) -> bool:  # noqa: ARG002
        expected = self.sign(payload)
        return hmac.compare_digest(str(signature), expected)


class Ed25519SigningAdapter:
    """Ed25519 signer using ``cryptography`` when available.

    ``private_key_b64`` may contain either raw 32-byte private key bytes or a PEM
    document encoded as base64.  ``from_env`` reads ``AUDIT_ED25519_PRIVATE_KEY``
    and ``AUDIT_SIGNER_ID``.
    """

    algorithm = "Ed25519(record_hash)"

    def __init__(self, private_key_b64: str, *, signer_id: str = "lrsi-runtime"):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Ed25519 signing requires the 'cryptography' package") from exc

        raw = base64.b64decode(private_key_b64.encode("ascii"))
        if raw.startswith(b"-----BEGIN"):
            loaded = serialization.load_pem_private_key(raw, password=None)
            if not isinstance(loaded, Ed25519PrivateKey):
                raise ValueError("AUDIT_ED25519_PRIVATE_KEY PEM must contain an Ed25519 private key")
            self._private_key = loaded
        elif len(raw) == 32:
            self._private_key = Ed25519PrivateKey.from_private_bytes(raw)
        else:
            raise ValueError("AUDIT_ED25519_PRIVATE_KEY must be base64(raw32) or base64(PEM)")
        self.signer_id = signer_id

    @classmethod
    def generate_for_tests(cls, *, signer_id: str = "test-ed25519") -> "Ed25519SigningAdapter":
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        raw = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return cls(base64.b64encode(raw).decode("ascii"), signer_id=signer_id)

    @classmethod
    def from_env(cls) -> "Ed25519SigningAdapter":
        key = os.getenv("AUDIT_ED25519_PRIVATE_KEY")
        if not key:
            raise RuntimeError("AUDIT_ED25519_PRIVATE_KEY is required for Ed25519 signing")
        return cls(key, signer_id=os.getenv("AUDIT_SIGNER_ID", "lrsi-runtime"))

    def sign(self, payload: bytes) -> str:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = cast(Ed25519PrivateKey, self._private_key)
        return base64.b64encode(private_key.sign(payload)).decode("ascii")

    def public_metadata(self) -> dict:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = cast(Ed25519PrivateKey, self._private_key)
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return {
            "audit_signature_algorithm": self.algorithm,
            "audit_signer_id": self.signer_id,
            "audit_public_key_b64": base64.b64encode(public_key).decode("ascii"),
        }

    def verify(self, payload: bytes, signature: str, metadata: dict | None = None) -> bool:
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            meta = metadata or self.public_metadata()
            public_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(meta["audit_public_key_b64"].encode("ascii"))
            )
            public_key.verify(base64.b64decode(signature.encode("ascii")), payload)
            return True
        except (InvalidSignature, KeyError, ValueError, TypeError):
            return False


def adapter_from_env() -> SigningAdapter | None:
    """Return a configured signing adapter, preserving V11.0 HMAC behavior."""
    mode = os.getenv("AUDIT_SIGNING_MODE", "auto").lower().strip()
    if mode in {"none", "off", "unsigned"}:
        return None
    if mode in {"ed25519", "public-key", "public_key"} or os.getenv("AUDIT_ED25519_PRIVATE_KEY"):
        return Ed25519SigningAdapter.from_env()
    if mode in {"hmac", "auto"} and os.getenv("AUDIT_HMAC_KEY"):
        return HMACSigningAdapter(
            os.environ["AUDIT_HMAC_KEY"],
            signer_id=os.getenv("AUDIT_SIGNER_ID", "local-hmac-runtime"),
        )
    return None


def verify_signature_payload(record_hash_value: str, record: dict, *, key: str | None = None) -> bool:
    """Verify a record signature for either Ed25519 or legacy HMAC records."""
    algorithm = record.get("audit_signature_algorithm")
    signature = record.get("audit_signature")
    if not algorithm or not signature:
        return False
    payload = str(record_hash_value).encode("utf-8")
    if str(algorithm).startswith("HMAC"):
        hmac_key = key or os.getenv("AUDIT_HMAC_KEY")
        if not hmac_key:
            return False
        return HMACSigningAdapter(hmac_key).verify(payload, signature)
    if str(algorithm).startswith("Ed25519"):
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            public_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(record["audit_public_key_b64"].encode("ascii"))
            )
            public_key.verify(base64.b64decode(signature.encode("ascii")), payload)
            return True
        except (KeyError, ValueError, TypeError, InvalidSignature):
            return False
    return False
