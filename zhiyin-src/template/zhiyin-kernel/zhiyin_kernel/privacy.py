"""Redact sensitive text at model boundaries without altering stored user records."""
import re

SENSITIVE = re.compile(
    r"(?:身份证|手机号|银行卡|住址|家庭住址).{0,12}\d{5,}"
    r"|(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\w)"
)


def redact_sensitive(value):
    if isinstance(value, str):
        return SENSITIVE.sub("[敏感信息已隐藏]", value)
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_sensitive(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return redact_sensitive(value.model_dump(mode="json"))
    return value
