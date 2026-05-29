"""RSA-2048 签字工具（用于行长终审的不可篡改电子签章）。

私钥存于 backend/keystores/user_{id}.key.pem（mode 600，不入库不入 git）。
公钥写入 UserKeyPair.public_key_pem，用于签名验真。
"""
import base64
import logging
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding as _padding
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

KEYSTORE_DIR = Path(__file__).parent / 'keystores'


def is_available() -> bool:
    return _CRYPTO_OK


def _keypath(user_id: int) -> Path:
    KEYSTORE_DIR.mkdir(mode=0o700, exist_ok=True)
    return KEYSTORE_DIR / f'user_{user_id}.key.pem'


def get_or_create_keypair(user_id: int) -> tuple[str, str]:
    """返回 (private_key_pem_text, public_key_pem_text)。"""
    if not _CRYPTO_OK:
        raise RuntimeError('cryptography 库未安装，RSA 签名不可用')
    kp = _keypath(user_id)
    if kp.exists():
        with open(kp, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_bytes = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        kp.write_bytes(priv_bytes)
        kp.chmod(0o600)

    pub_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('utf-8')
    priv_pem = kp.read_text()
    return priv_pem, pub_pem


def sign_payload(user_id: int, payload: str) -> str:
    """RSA-SHA256 签名，返回 base64 编码字符串；失败时返回空串。"""
    if not _CRYPTO_OK:
        return ''
    try:
        kp = _keypath(user_id)
        if not kp.exists():
            get_or_create_keypair(user_id)
        with open(kp, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        sig = private_key.sign(payload.encode('utf-8'), _padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode('utf-8')
    except Exception as e:
        log.error('RSA 签名失败 user_id=%s: %s', user_id, e)
        return ''


def verify_payload(public_key_pem: str, payload: str, signature_b64: str) -> bool:
    """用公钥验签；验证失败返回 False。"""
    if not _CRYPTO_OK or not signature_b64:
        return False
    try:
        pub_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
        pub_key.verify(
            base64.b64decode(signature_b64),
            payload.encode('utf-8'),
            _padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False
