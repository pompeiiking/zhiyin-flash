"""真实的安全实现：脱敏 + 加密 + 审计。

替换掉的是什么
--------------
原来那个 `NoopSecurity` 三件事全是假的：`encrypt` 原样返回、`mask` 原样返回、
`audit` 只 `print` 一行。它在装配报告里显示"已装配"，而实际上：

  · 任何写进对象存储的东西都是明文；
  · 日志与界面里出现的手机号、邮箱、身份证号不会被遮；
  · "谁在什么时候动了哪条数据"没有留下任何可查的痕迹。

三条口径
--------
1. **加密用 AES-GCM**（认证加密）：密文被改一个字节，解密直接失败 ——
   这比"解密出来是乱码"重要得多，后者会被当成数据坏了而不是被篡改；
2. **密钥只从环境来**：它保护的正是库里的东西，不能和它们放在一起；
3. **审计落到结构化日志**：`zhiyin.audit` 这个 logger 单独一路，
   运维把它接进日志系统就是可查询的审计流；接不了也不影响业务。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from zhiyin_data_sdk.gateways.security import SecurityGateway

logger = logging.getLogger(__name__)

#: 审计单独一路：运维把它接进日志系统就是可查询的审计流
audit_logger = logging.getLogger("zhiyin.audit")

#: 环境变量名。密钥只有这一处来源 —— 它保护的是库里的数据，不能和它们放在一起。
KEY_ENV = "ZHIYIN_SECURITY_KEY"


class CryptoSecurity(SecurityGateway):
    """AES-GCM 加密 + 真脱敏 + 结构化审计。"""

    IMPLEMENTATION_STATUS = "wired"

    #: 各类敏感信息的脱敏规则：`(留头几位, 留尾几位)`
    _RULES: dict[str, tuple[int, int]] = {
        "phone": (3, 4),
        "email": (2, 0),
        "id_card": (4, 2),
        "name": (1, 0),
        "token": (0, 0),
        "generic": (2, 2),
    }

    def __init__(self, key: str) -> None:
        raw = (key or "").encode("utf-8")
        if len(raw) < 32:
            raise ValueError(
                f"{KEY_ENV} 至少 32 字节 —— 密钥太短等于没有加密。"
                '生成一条：python -c "import secrets;print(secrets.token_urlsafe(48))"'
            )
        self._key = raw[:32]

    def encrypt(self, data: bytes) -> bytes:
        """AES-GCM：随机 nonce 拼在密文前面，认证标签由算法自己带上。"""
        nonce = os.urandom(12)
        sealed = AESGCM(self._key).encrypt(nonce, data, None)
        return b"v1" + nonce + sealed

    def decrypt(self, data: bytes) -> bytes:
        """解密。**不是本实现加的密**（或密文被改过）时抛错，不静默返回原文。"""
        if not data.startswith(b"v1") or len(data) < 15:
            raise ValueError("这段数据不是本实现加密的（或已被篡改），拒绝按明文返回")
        nonce, sealed = data[2:14], data[14:]
        return AESGCM(self._key).decrypt(nonce, sealed, None)

    def mask(self, value: str, *, kind: str = "generic") -> str:
        """脱敏：**留头留尾，中间打星**。

        全遮（`****`）看起来安全，但排查时完全没用 —— 用户报"我的手机号不对"，
        运维连是不是同一个号都看不出来。留头尾是"够遮 + 还能核对"的平衡点。
        """
        text = value or ""
        if not text:
            return ""
        if kind == "token":
            return "*" * min(8, len(text))
        keep_head, keep_tail = self._RULES.get(kind, self._RULES["generic"])
        if kind == "email" and "@" in text:
            name, _, domain = text.partition("@")
            head = name[:keep_head]
            return f"{head}{'*' * max(3, len(name) - keep_head)}@{domain}"
        if len(text) <= keep_head + keep_tail:
            return "*" * len(text)
        middle = len(text) - keep_head - keep_tail
        tail = text[-keep_tail:] if keep_tail else ""
        return f"{text[:keep_head]}{'*' * middle}{tail}"

    def audit(self, record: dict[str, Any]) -> None:
        """审计：一条结构化 JSON，进 `zhiyin.audit` 这一路 logger。

        字段写全（谁 / 对什么 / 做了什么 / 结果）才有查的价值；
        只打一句"audit: {...}"的，出事时没人能按字段过滤。
        """
        try:
            payload = {
                "action": str(record.get("action") or ""),
                "user_id": str(record.get("user_id") or ""),
                "target": str(record.get("target") or ""),
                "result": str(record.get("result") or "ok"),
                "detail": record.get("detail") or {},
            }
            audit_logger.info(json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:  # noqa: BLE001 - 审计失败不能反过来打断业务
            logger.warning("审计记录写入失败（已忽略）", exc_info=True)


__all__ = ["KEY_ENV", "CryptoSecurity", "audit_logger"]
