"""LINE Messaging API Webhook 署名検証。"""

import base64
import hashlib
import hmac


def verify_signature(channel_secret: str, body: bytes, x_line_signature: str | None) -> bool:
    if not channel_secret or x_line_signature is None:
        return False
    mac = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, x_line_signature)
