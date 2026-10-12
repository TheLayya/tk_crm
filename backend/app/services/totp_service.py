"""Small RFC 6238 TOTP helper shared by email and card-key flows."""
import base64
import binascii
import hashlib
import hmac
import struct
import time


def totp_code(secret: object, now: float | None = None) -> tuple[str | None, int | None]:
    try:
        if not secret:
            return None, None
        normalized = "".join(str(secret).split()).replace("-", "").upper()
        key = base64.b32decode(normalized + "=" * (-len(normalized) % 8), casefold=True)
        if not key:
            return None, None
        timestamp = int(time.time() if now is None else now)
        counter = timestamp // 30
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
        return f"{number:06d}", 30 - (timestamp % 30)
    except (ValueError, TypeError, binascii.Error):
        return None, None
