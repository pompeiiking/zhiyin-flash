"""会话记忆服务实现。

除了摘要与逐轮原文，它还负责**用户带上来的材料**（简历、证书、导出的表格…）：
材料正文抽出来落在对象存储里，对话里只留一句"我传了一份材料：xxx"
（正文进模型输入，不进气泡 —— 见 `put_material` 的说明）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from zhiyin_business.ports.blackboard import (
    ConversationMaterial,
    ConversationMaterialBody,
    ConversationMemoryService,
)
from zhiyin_data_sdk.gateways.documents import DocumentReadError, DocumentTextGateway
from zhiyin_data_sdk.gateways.storage import ObjectStoreGateway
from zhiyin_data_sdk.repositories import (
    ConversationMemoryRepository,
    ConversationTurnRepository,
)
from zhiyin_kernel.blackboard import ConversationMemory, ConversationTurn
from zhiyin_kernel.enums import LoopStage
from zhiyin_kernel.errors import InvalidRequest


class DefaultConversationMemoryService(ConversationMemoryService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        memories: ConversationMemoryRepository,
        turns: Optional[ConversationTurnRepository] = None,
        documents: Optional[DocumentTextGateway] = None,
        object_store: Optional[ObjectStoreGateway] = None,
    ) -> None:
        self._memories = memories
        # 逐轮原文是可选的：只做摘要续接的装配（单测、纯内存最小装配）可以不接它，
        # 那时 record_turn 是空操作，而不是抛错 —— 它不该成为主链路的必需依赖。
        self._turns = turns
        # 材料那两个也是可选的，理由同上：不接它们时 put_material 会如实报
        # "这一版没有装配材料上传"，而不是假装收下了（假装收下 = 用户交了一份
        # 材料，模型却什么都没看到，而他不会知道）。
        self._documents = documents
        self._object_store = object_store

    async def get(self, user_id: str, task_id: str) -> Optional[ConversationMemory]:
        return await self._memories.get(user_id, task_id)

    async def upsert(
        self,
        user_id: str,
        task_id: str,
        *,
        loop_stage: LoopStage,
        lead_agent: str,
        summary_delta: str = "",
    ) -> ConversationMemory:
        existing = await self._memories.get(user_id, task_id)
        summary = (existing.summary if existing else "") + summary_delta
        return await self._memories.upsert(
            ConversationMemory(
                id=existing.id if existing else f"mem_{uuid4().hex[:12]}",
                user_id=user_id,
                task_id=task_id,
                loop_stage=loop_stage,
                lead_agent=lead_agent,
                summary=summary,
                last_active_at=datetime.now(timezone.utc),
            )
        )

    async def list_by_user(self, user_id: str) -> list[ConversationMemory]:
        return await self._memories.list_by_user(user_id)

    async def record_turn(
        self,
        user_id: str,
        task_id: str,
        *,
        role: str,
        text: str,
        loop_stage: LoopStage,
        agent_id: str = "",
        client_msg_id: str = "",
    ) -> ConversationTurn:
        turn = ConversationTurn(
            id=f"turn_{uuid4().hex[:12]}",
            user_id=user_id,
            task_id=task_id or None,
            role=role,  # type: ignore[arg-type]
            text=text,
            loop_stage=loop_stage,
            agent_id=agent_id,
            client_msg_id=client_msg_id,
            created_at=datetime.now(timezone.utc),
        )
        if self._turns is None:
            return turn
        return await self._turns.append(turn)

    async def find_reply(
        self, user_id: str, client_msg_id: str
    ) -> Optional[ConversationTurn]:
        if self._turns is None:
            return None
        return await self._turns.find_reply_by_client_msg_id(user_id, client_msg_id)

    async def list_turns(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationTurn]:
        if self._turns is None:
            return []
        return await self._turns.list_by_task(user_id, task_id, limit=limit)

    # ------------------------------------------------------------ 用户带上来的材料

    async def put_material(
        self, user_id: str, *, name: str, data: bytes
    ) -> ConversationMaterial:
        """收下一份材料：抽出正文 → 落对象存储 → 回一句"它是什么"。

        读不出正文时抛 `DocumentReadError`（消息里是用户能自己做的那一步）——
        业务层会把它翻成 422 的原话，界面照原样显示。
        """
        if self._documents is None or self._object_store is None:
            raise RuntimeError("材料上传未装配（Container.documents / object_store）")
        try:
            text = self._documents.extract_text(data, filename=name)
        except DocumentReadError as exc:
            # "这份文件我读不了"（Excel 那种二进制、空文件）是**用户能自己修的事**：
            # 翻成 InvalidRequest，api 按 422 + 原话返回，界面照原样显示那句
            # "另存为 CSV 再传"。不翻的话用户看到的是 500。
            raise InvalidRequest(str(exc)) from exc
        material_id = f"mat_{uuid4().hex[:12]}"
        key = self._object_store.build_named_key(
            user_id, "conversation_material", material_id, "txt"
        )
        # 存的是一个**带名字的信封**（名字 + 正文），不是光秃秃的正文：
        # 取用时（拼模型输入）要告诉模型"这段是哪份材料"，而对象存储只认识字节。
        # 统一按 UTF-8 写：读进来时编码已经归一过一次，再存回原文编码会让取用方
        # 多背一份"这份是什么编码"的知识。
        payload = ConversationMaterialBody(name=name, text=text).model_dump_json()
        await self._object_store.put(
            key, payload.encode("utf-8"), content_type="application/json"
        )
        return ConversationMaterial(
            material_id=material_id,
            name=name,
            size=len(data),
            chars=len(text),
        )

    async def material_body(
        self, user_id: str, material_id: str
    ) -> ConversationMaterialBody:
        """取回材料的名字与正文。键里带 user_id，所以别人的 id 取不到自己的文件。"""
        if self._object_store is None:
            raise RuntimeError("材料上传未装配（Container.object_store）")
        key = self._object_store.build_named_key(
            user_id, "conversation_material", material_id, "txt"
        )
        try:
            raw = await self._object_store.get(key)
        except FileNotFoundError as exc:
            raise LookupError("这份材料找不到了 —— 重新传一次就行。") from exc
        return ConversationMaterialBody.model_validate_json(raw.decode("utf-8", errors="replace"))


__all__ = ["DefaultConversationMemoryService"]
