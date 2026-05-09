import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


TOKEN_PREFIX = "fernet:"


class SecretDecryptionError(ValueError):
    pass


def encrypt_secret(value):
    value = (value or "").strip()
    if not value:
        return ""
    return TOKEN_PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value):
    value = value or ""
    if not value:
        return ""
    if not value.startswith(TOKEN_PREFIX):
        return value
    try:
        return _fernet().decrypt(value.removeprefix(TOKEN_PREFIX).encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptionError("Stored AI provider secret could not be decrypted.") from exc


def is_encrypted(value):
    return bool(value and value.startswith(TOKEN_PREFIX))


def _fernet():
    raw_key = getattr(settings, "THREADLINE_FIELD_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    digest = hashlib.sha256(str(raw_key).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
