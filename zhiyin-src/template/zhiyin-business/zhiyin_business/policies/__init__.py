"""业务规则层（policies）。

为什么要单独一层
----------------
`ports/` 冻结的是"服务长什么样"，`services/` 放的是"服务怎么跑"，但两者之间
最容易被写乱的是**规则本身**：意图怎么判、主理怎么选、交接何时触发、影响面
怎么算、什么时候才允许打扰用户。这些规则过去没有归宿，实现者只能塞进
Orchestrator 或某个 Service 的方法体里，结果是规则改一处要动一串调用方。

因此本包按"规则类别"分文件，每条规则一个 ABC，**只声明输入与输出**：

    routing.py        意图识别 → 环节判定（轴 B）
    teaming.py        轴 A × 轴 B × 意图 → 主理/协理
    handoff.py        交接与"换主理必须告知"
    impact.py         画像字段 → 受影响资产（重算范围）
    intervention.py   停滞阈值 / 冷却期 / 打扰上限
    renderers.py      可视件白名单与校验（图 / 时间线 … 的注册点）

依赖方向（单向，禁止倒流）
--------------------------
    services/ → policies/ → ports/ → kernel

`policies/` 不得 import `services/`：规则不能反过来依赖某次实现。
规则实现只允许依赖 Port（读黑板、读 registry）与共享内核，因此可以被单测直接
驱动，不需要起整个服务。

参数来源
--------
阈值、冷却期、话术这类**可调参数一律来自动态资源**（`data/registry/*.json`），
不得写死在规则实现里。规则实现只负责"怎么用参数"，不负责"参数是多少"。

状态：接口已冻结，**业务口径已定稿**。
由各业务线在此补实现；规则的参数已写进 `data/registry/policy_params.json`
（`intervention` / `profile_collection` / `routing` 三项 `confirmed`）。
"""

from zhiyin_business.policies.handoff import HandoffPolicy
from zhiyin_business.policies.impact import ImpactPolicy
from zhiyin_business.policies.intel_query import intel_topic
from zhiyin_business.policies.intervention import InterventionPolicy
from zhiyin_business.policies.routing import IntentPolicy, StagePolicy
from zhiyin_business.policies.teaming import LeadPolicy
from zhiyin_business.policies.handoff_rules import DisclosureHandoffPolicy
from zhiyin_business.policies.impact_rules import DependencyImpactPolicy
from zhiyin_business.policies.intervention_rules import ThresholdInterventionPolicy
from zhiyin_business.policies.routing_rules import KeywordIntentPolicy, RuleStagePolicy
from zhiyin_business.policies.teaming_rules import RegistryLeadPolicy

__all__ = [
    "HandoffPolicy",
    "ImpactPolicy",
    "intel_topic",
    "IntentPolicy",
    "InterventionPolicy",
    "LeadPolicy",
    "StagePolicy",
    "DisclosureHandoffPolicy",
    "DependencyImpactPolicy",
    "KeywordIntentPolicy",
    "RegistryLeadPolicy",
    "RuleStagePolicy",
    "ThresholdInterventionPolicy",
]
