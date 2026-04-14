import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class EncryptionService:
    def __init__(self, key_hex: str):
        self.key = bytes.fromhex(key_hex)

    def encrypt(self, plaintext: str) -> str:
        """返回 base64(iv[12] + tag[16] + ciphertext)"""
        iv = os.urandom(12)
        cipher = Cipher(algorithms.AES(self.key), modes.GCM(iv))
        encryptor = cipher.encryptor()
        ct = encryptor.update(plaintext.encode()) + encryptor.finalize()
        return base64.b64encode(iv + encryptor.tag + ct).decode()

    def decrypt(self, encrypted: str) -> str:
        data = base64.b64decode(encrypted)
        iv, tag, ct = data[:12], data[12:28], data[28:]
        cipher = Cipher(algorithms.AES(self.key), modes.GCM(iv, tag))
        decryptor = cipher.decryptor()
        return (decryptor.update(ct) + decryptor.finalize()).decode()


# 模块级单例，延迟初始化以避免循环导入
_encryption_service: EncryptionService | None = None


def _get_encryption_service() -> EncryptionService:
    global _encryption_service
    if _encryption_service is None:
        from app.core.config import settings
        _encryption_service = EncryptionService(settings.FIELD_ENCRYPTION_KEY)
    return _encryption_service


class EncryptedType(TypeDecorator):
    """SQLAlchemy TypeDecorator，透明加解密字符串字段"""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _get_encryption_service().encrypt(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _get_encryption_service().decrypt(value)
        except Exception:
            # Value is not encrypted (legacy plaintext data), return as-is
            return value
