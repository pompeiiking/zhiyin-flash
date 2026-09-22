"""意图识别与环节判定的默认规则实现。"""

from __future__ import annotations

import logging
from typing import Optional

from zhiyin_business.policies.routing import IntentPolicy, StagePolicy
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import (
    IntentType,
    StageDecision,
)
from zhiyin_business.ports.registry import RegistryService
from zhiyin_kernel.enums import LoopStage

logger = logging.getLogger(__name__)

CLARIFY_PROMPT_CODE = "router.clarify"
"""全新会话的澄清追问文案。它以前是方法体里的一句字面量。"""


class KeywordIntentPolicy(IntentPolicy):
    """关键词优先的意图识别。

    词表来自动态资源（`ai_routing_rule` 的 `kind=intent` 条目），不在代码里。

    为什么这件事值得单独说：词表是**产品语言**，不是逻辑。用户说「投了没回音」
    和「投了没人理」是同一件事；而「投了没回音」到底算「想验证方向」还是
    「卡住了」，是会随产品判断变化的取舍。写进代码，这两件事就都被冻在发版节奏上。

    不缓存读结果：改一条词表应当立刻生效。一次读十来条带索引的行，
    比"改完配置却要等重启"便宜得多。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, registry: Optional[RegistryService] = None) -> None:
        self._registry = registry

    async def classify(self, *, message: str, blackboard: BlackboardView) -> IntentType:
        text = (message or "").strip()
        for rule in await self._rules("intent"):
            if not rule.match:
                continue
            if not any(keyword in text for keyword in rule.match):
                continue
            try:
                return IntentType(rule.intent)
            except ValueError:
                # 配置里写了不存在的意图：跳过并留痕，不要让一条错配置打断整轮对话。
                logger.warning(
                    "路由规则 %s 的目标意图不存在：%s（已跳过）", rule.id, rule.intent
                )
        return IntentType.FREE_CHAT

    async def _rules(self, kind: str):
        if self._registry is None:
            return []
        return await self._registry.list_routing_rules(kind)


class RuleStagePolicy(StagePolicy):
    """由意图映射目标环节。

    映射来自动态资源（`kind=stage` 的条目）。**未命中时的行为仍在代码里**，
    因为那是策略而不是配置：

    ⚠️ 这里踩过一个代价很大的坑，值得写下来：

    原先"意图不在映射表里"就直接返回一句**写死的**澄清追问
    （"你现在最想先解决哪一件事：了解自己、验证方向、做选择，还是推进计划？"），
    而且这条路径**根本不调用模型**。于是：

      「我今天投了三家设计院，还没回音」→ 关键词没命中 → 0.0 秒回同一句；
      「我在准备秋招，但不知道先做什么」→ 命中关键词 → 22 秒，真实模型回复。

    用户看到的就是"有时像真的、大多时候是复读机"，很自然会判断成接了个假模型。

    但"关键词没命中"从来不等于"用户的意思不清楚"。上面第一句话一点也不含糊，
    只是我们的词表没想到。这种情况正确的做法是**退回当前所处环节、交给模型**，
    而不是用一句模板把用户挡回去 —— 编排器存在的意义就是处理这种自由表达。

    只有当**连当前环节都没有**（全新会话、还没定过位）时，才真的需要先澄清。
    这时用哪句话，仍然来自动态资源（`router.clarify`）。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, registry: Optional[RegistryService] = None) -> None:
        self._registry = registry

    async def decide(
        self,
        *,
        blackboard: BlackboardView,
        intent: IntentType,
        message: str,
    ) -> StageDecision:
        for rule in await self._rules("stage"):
            if rule.intent != intent.value:
                continue
            try:
                stage = LoopStage(rule.stage)
            except ValueError:
                logger.warning(
                    "路由规则 %s 的目标环节不存在：%s（已跳过）", rule.id, rule.stage
                )
                continue
            return StageDecision(stage=stage, confidence=0.85)

        # 退回当前环节，让模型去答 —— 见类文档里那两句话的对比
        if blackboard.current_stage is not None:
            return StageDecision(stage=blackboard.current_stage, confidence=0.5)
        return StageDecision(
            confidence=0.3,
            need_clarify=True,
            clarify_question=await self._clarify_question(),
        )

    async def _rules(self, kind: str):
        if self._registry is None:
            return []
        return await self._registry.list_routing_rules(kind)

    async def _clarify_question(self) -> Optional[str]:
        """澄清话术取自动态资源。取不到返回 None，由调用方决定兜底口径。"""
        if self._registry is None:
            return None
        prompt = await self._registry.get_prompt(CLARIFY_PROMPT_CODE)
        return prompt.content if prompt is not None else None


__all__ = ["KeywordIntentPolicy", "RuleStagePolicy"]
