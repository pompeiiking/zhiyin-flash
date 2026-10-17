"""给本机部署写入一批演示账号与数据（供浏览与联调使用）。

为什么放在容器里跑
------------------
数据要用**应用自己的仓储**写进去（`zhiyin_infrastructure.postgres.repository`），
这样画像字段、报告正文、方向方案、行动计划、会话逐轮原文的 JSON 形状与读接口完全一致；
用裸 SQL 拼 JSON 迟早会和模型定义漂移。

用法
----
    docker compose cp scripts/seed_demo_data.py zhiyin-flash:/tmp/seed_demo_data.py
    docker compose exec -T zhiyin-flash python /tmp/seed_demo_data.py

账号口令统一是 `123456`；账号 d1a..d1d 大一、d2a..d2d 大二、d3a..d3d 大三、d4a..d4d 大四。
重复执行会先清掉这些账号的业务数据再重写（账号与密码保留）。
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from zhiyin_data_sdk.gateways.academic import AcademicSnapshot, CourseEntry, GradeEntry
from zhiyin_infrastructure.postgres.database import PostgresDatabase
from zhiyin_infrastructure.postgres.repository import (
    PostgresAcademicSnapshotRepository,
    PostgresAssetRepository,
    PostgresBehaviorRepository,
    PostgresCalendarNodeRepository,
    PostgresConversationMemoryRepository,
    PostgresConversationTurnRepository,
    PostgresProfileRepository,
    PostgresTaskSessionRepository,
    PostgresTrackEventRepository,
    PostgresUserNoteRepository,
)
from zhiyin_kernel.assets import (
    ActionPhase,
    ActionPlan,
    ActionTask,
    CalendarNode,
    DirectionPlan,
    GapClaim,
    PlanGap,
    Report,
    ReportDimensionGroup,
    ReportDimensionItem,
    Swot,
    TrackEvent,
    Verdict,
)
from zhiyin_kernel.blackboard import (
    AssetVersion,
    BehaviorLog,
    ConversationMemory,
    ConversationTurn,
    ProfileField,
    ProfileGap,
    TaskSession,
    UserNote,
)
from zhiyin_kernel.enums import (
    AssetType,
    BehaviorEventType,
    LoopStage,
    PathFocus,
    PlanRole,
    ProfileSource,
    TaskStatus,
)
from zhiyin_kernel.identity import UserAccount

API = os.environ.get("SEED_API_BASE", "http://127.0.0.1:8000/api/v1")
DSN = os.environ.get("ZHIYIN_POSTGRES_DSN", "postgresql://zhiyin:zhiyin@postgres:5432/zhiyin")
PASSWORD = "123456"
NOW = datetime.now(timezone.utc)


def dt(days: float = 0, hours: float = 0) -> datetime:
    return NOW + timedelta(days=days, hours=hours)


def d(value: str) -> date:
    return date.fromisoformat(value)


# ---------------------------------------------------------------------------
# 账号人设：16 个，覆盖大一到大四，每人一个不同的专业与目标方向
# ---------------------------------------------------------------------------
PERSONAS = [
    # ---- 大一 ----
    dict(account="d1a", name="林知夏", grade="year_1", school="河北大学", major="汉语言文学", degree="本科", city="保定",
         interest="写东西、做短视频脚本；看到好文案会想拆解它怎么起的效果",
         value="成长优先，能接受前两年辛苦，但不想做重复劳动",
         experience="校报写过 12 篇稿；给学院公众号做过 3 个月排版",
         skills="文字表达、选题策划、简单剪辑",
         strengths=["文字敏感度高", "愿意主动找事做", "信息搜集快"],
         weaknesses=["缺少数据意识", "公开发言会紧张"],
         careers=["新媒体运营", "内容策划", "事业单位文字岗"], industry="互联网内容",
         courses=["现代汉语", "中国古代文学", "写作学", "新闻采访与写作", "大学英语", "传播学概论"]),
    dict(account="d1b", name="陈子昂", grade="year_1", school="河北大学", major="计算机科学与技术", degree="本科", city="石家庄",
         interest="写代码、折腾开源项目，喜欢把一个想法做成能跑的东西",
         value="成就感优先，想进技术氛围强的团队",
         experience="高中起自学 Python；做过一个校园二手交易小工具，200+ 同学用过",
         skills="Python、基础前端、git 协作",
         strengths=["动手能力强", "自学速度快", "愿意读源码"],
         weaknesses=["算法基础薄弱", "表达时偏技术、不够通俗"],
         careers=["后端开发工程师", "算法工程师", "技术产品经理"], industry="互联网技术",
         courses=["程序设计基础", "高等数学", "线性代数", "计算机导论", "离散数学", "大学英语"]),
    dict(account="d1c", name="苏念", grade="year_1", school="河北大学", major="会计学", degree="本科", city="邯郸",
         interest="喜欢把一堆数字理清楚，做表格类的事情特别有耐心",
         value="稳定与专业成长并重，希望工作有明确的能力标尺",
         experience="班委管班费，做过一学期的收支表；参加过商科案例分析比赛",
         skills="Excel、数据整理、细致耐心",
         strengths=["细致、出错率低", "数字敏感", "计划性强"],
         weaknesses=["行业视野窄", "缺乏公开表达经验"],
         careers=["财务分析", "审计", "数据分析"], industry="财务与咨询",
         courses=["会计学原理", "微观经济学", "管理学", "统计学", "大学英语", "经济法"]),
    dict(account="d1d", name="赵一鸣", grade="year_1", school="河北大学", major="机械设计制造及其自动化", degree="本科", city="唐山",
         interest="机器人、3D 打印，喜欢动手把零件拼起来看它动",
         value="技术钻研优先，希望长期在制造业升级里做实事",
         experience="参加校机器人社团；用 SolidWorks 做过一个小车模型",
         skills="三维建模、基础电路、动手装配",
         strengths=["动手能力强", "空间想象好", "抗压"],
         weaknesses=["英语文献阅读慢", "缺少项目文档习惯"],
         careers=["机械设计工程师", "智能制造工程师", "工业产品经理"], industry="智能制造",
         courses=["机械制图", "工程力学", "机械原理", "工程材料", "大学英语", "高等数学"]),
    # ---- 大二 ----
    dict(account="d2a", name="周雨桐", grade="year_2", school="河北大学", major="应用心理学", degree="本科", city="保定",
         interest="研究人怎么想问题和做决定，喜欢做访谈、写观察记录",
         value="意义感优先，想做能理解具体人的工作",
         experience="院心理协会干事，组织过 5 场朋辈工作坊；参与过一个用户访谈课程项目",
         skills="访谈提问、问卷设计、基础统计",
         strengths=["共情能力强", "提问有条理", "能写结构化记录"],
         weaknesses=["定量工具不熟", "项目落地经验少"],
         careers=["用户研究", "HR 招聘与培训", "心理咨询方向深造"], industry="互联网用户研究与人力资源",
         courses=["普通心理学", "心理统计", "实验心理学", "社会心理学", "研究方法", "大学英语"]),
    dict(account="d2b", name="何嘉言", grade="year_2", school="河北大学", major="电子商务", degree="本科", city="石家庄",
         interest="看电商数据、策划活动，喜欢研究一个店铺怎么从 0 做到有销量",
         value="结果导向，喜欢能看到增长的工作",
         experience="帮家里网店做过 2 个月运营，把日单量从 3 单做到 20 单",
         skills="店铺后台、活动策划、基础数据分析",
         strengths=["执行力强", "对数据敏感", "懂平台规则"],
         weaknesses=["平台依赖单一", "文案能力一般"],
         careers=["电商运营", "用户增长", "品牌运营"], industry="电商与消费品",
         courses=["电子商务概论", "市场营销", "网络营销", "消费者行为学", "统计学", "大学英语"]),
    dict(account="d2c", name="罗清越", grade="year_2", school="河北大学", major="视觉传达设计", degree="本科", city="北京",
         interest="做海报、品牌视觉，喜欢研究一个品牌从 logo 到门店的整体感觉",
         value="审美与成长优先，愿意进专业设计团队慢慢熬",
         experience="接过 6 个校内社团的视觉设计；参与过一家咖啡店的品牌改版",
         skills="PS/AI、版式设计、品牌视觉基础",
         strengths=["审美在线", "出图快", "沟通耐心"],
         weaknesses=["作品集缺少商业项目", "理论表达弱"],
         careers=["品牌设计师", "UI 视觉设计", "广告创意"], industry="设计行业",
         courses=["设计基础", "字体设计", "版式设计", "品牌设计", "色彩构成", "设计史"]),
    dict(account="d2d", name="韩沐辰", grade="year_2", school="河北大学", major="电子信息工程", degree="本科", city="秦皇岛",
         interest="嵌入式开发、单片机，喜欢自己焊板子做小装置",
         value="技术深度优先，希望做别人做不出来的东西",
         experience="参加电子设计竞赛校赛获二等奖；做过一个自动浇花装置",
         skills="C 语言、单片机、焊接调试",
         strengths=["动手扎实", "调试耐心", "愿意啃原理"],
         weaknesses=["项目复盘少", "团队协作经验不足"],
         careers=["嵌入式开发", "硬件工程师", "物联网方案工程师"], industry="电子信息与物联网",
         courses=["电路分析", "模拟电子技术", "数字电子技术", "C 语言程序设计", "信号与系统", "大学英语"]),
    # ---- 大三 ----
    dict(account="d3a", name="沈书瑶", grade="year_3", school="河北大学", major="金融学", degree="本科", city="天津",
         interest="看财报、研究利率和行业周期，喜欢把一家公司算明白",
         value="专业成长与收入并重，愿意先吃几年投研的苦",
         experience="券商营业部实习 2 个月；校级金融案例分析大赛一等奖；通过证券从业资格",
         skills="财报分析、Excel 建模、行业资料检索",
         strengths=["分析框架清晰", "自驱强", "抗压"],
         weaknesses=["缺少深度实习", "面试表达偏学术"],
         careers=["券商研究员", "银行管培生", "金融科技产品"], industry="金融与资本市场",
         courses=["公司金融", "投资学", "财务报表分析", "金融工程", "国际金融", "计量经济学"]),
    dict(account="d3b", name="顾言川", grade="year_3", school="河北大学", major="软件工程", degree="本科", city="北京",
         interest="后端架构、数据库，喜欢把系统做得又快又稳",
         value="技术成长优先，想去大厂做有挑战的系统",
         experience="参与实验室横向项目，负责后端；LeetCode 400+；有一段中小厂后端实习",
         skills="Java、Spring、MySQL、Redis、基础分布式",
         strengths=["工程能力强", "自驱学习", "问题定位准"],
         weaknesses=["缺少高并发实战", "表达偏技术细节"],
         careers=["大厂后端开发", "基础架构工程师", "数据库内核方向"], industry="互联网/基础软件",
         courses=["软件工程", "数据库系统", "操作系统", "计算机网络", "分布式系统", "算法设计"]),
    dict(account="d3c", name="叶清和", grade="year_3", school="河北大学", major="新闻传播学", degree="本科", city="保定",
         interest="做深度采访和内容策划，喜欢把一个复杂的事讲清楚",
         value="表达与社会价值优先，希望做不违心的内容",
         experience="校媒主编，带过 8 人团队；在市级媒体实习 1 个月；写过 3 篇 10w+ 公众号",
         skills="采访写作、选题策划、短视频脚本",
         strengths=["采访能力强", "选题敏锐", "团队带得动"],
         weaknesses=["数据复盘弱", "商业化理解不足"],
         careers=["品牌公关", "内容编辑", "媒体记者"], industry="媒体与品牌传播",
         courses=["新闻学概论", "传播理论", "采访写作", "编辑学", "新媒体研究", "媒介伦理"]),
    dict(account="d3d", name="唐星野", grade="year_3", school="河北大学", major="材料科学与工程", degree="本科", city="石家庄",
         interest="研究材料性能，喜欢进实验室做表征和数据分析",
         value="科研深度优先，但也在犹豫考研还是直接就业",
         experience="进入导师课题组 1 年，参与 1 个省级项目；能独立做 SEM 样品制备",
         skills="实验设计、材料表征、论文检索",
         strengths=["科研耐心", "数据严谨", "英语文献能力好"],
         weaknesses=["企业需求了解少", "工程实践偏少"],
         careers=["材料研发工程师", "考研深造", "新能源工艺工程师"], industry="新材料与新能源",
         courses=["材料科学基础", "材料物理性能", "材料分析方法", "固体物理", "材料力学", "大学英语"]),
    # ---- 大四 ----
    dict(account="d4a", name="江晚晴", grade="year_4", school="河北大学", major="工商管理", degree="本科", city="天津",
         interest="组织协调、带项目，喜欢把人聚起来把事情推下去",
         value="稳定与平台并重，倾向成熟企业的管理培训生路径",
         experience="学生会副主席，组织过 2 场 500 人活动；快消公司市场部实习 3 个月",
         skills="项目推进、活动策划、跨部门沟通",
         strengths=["组织力强", "抗压", "沟通表达好"],
         weaknesses=["专业硬技能弱", "数据分析浅"],
         careers=["管培生", "市场运营", "国企综合管理"], industry="快消与国企",
         courses=["管理学原理", "组织行为学", "战略管理", "人力资源管理", "市场营销", "财务管理"]),
    dict(account="d4b", name="墨承宇", grade="year_4", school="河北大学", major="数据科学与大数据技术", degree="本科", city="北京",
         interest="数据建模、做可视化，喜欢从数据里找出一条能说服人的结论",
         value="技术成长优先，想进数据驱动型公司",
         experience="字节跳动数据分析实习 3 个月；全国大学生数学建模竞赛省一；Kaggle 银牌 1 次",
         skills="SQL、Python、Tableau、统计建模",
         strengths=["数据敏感", "业务理解快", "表达清晰"],
         weaknesses=["工程化经验少", "缺少管理经验"],
         careers=["数据分析师", "数据产品经理", "算法工程（数据方向）"], industry="互联网数据",
         courses=["数据结构", "概率统计", "数据库原理", "机器学习", "数据可视化", "大数据技术"]),
    dict(account="d4c", name="许知意", grade="year_4", school="河北大学", major="英语（师范）", degree="本科", city="保定",
         interest="教学、语言本身，喜欢把复杂的知识讲得让人听懂",
         value="稳定与意义并重，倾向教育行业",
         experience="教育机构兼职教师 1 年；获得校级师范生教学技能大赛二等奖",
         skills="英语教学、备课、课堂管理",
         strengths=["表达清晰", "耐心", "备课认真"],
         weaknesses=["行业选择偏窄", "非教学技能弱"],
         careers=["中学英语教师", "外企行政/翻译", "教育产品运营"], industry="教育与语言服务",
         courses=["英语语言学", "英美文学", "英语教学法", "翻译基础", "第二外语", "教育学"]),
    dict(account="d4d", name="温子航", grade="year_4", school="河北大学", major="土木工程", degree="本科", city="唐山",
         interest="工程现场、结构设计，喜欢看图纸变成实物的过程",
         value="稳定优先，能接受工地现场，希望有技术积累",
         experience="中建某局项目部实习 2 个月；参与过学校实训楼结构建模课程设计",
         skills="CAD、PKPM、施工组织基础",
         strengths=["吃苦耐劳", "图纸理解快", "现场适应强"],
         weaknesses=["表达偏少", "证书不足"],
         careers=["施工技术员", "设计院结构设计", "考公/事业单位"], industry="建筑与基建",
         courses=["结构力学", "混凝土结构设计", "钢结构", "土力学", "施工技术", "工程测量"]),
]

GRADE_META = {
    "year_1": dict(label="大一", grad="2030-06-30", enroll="2026-09-01", stage=LoopStage.COLLECT,
                   lead="profile_analyst", grad_year=2030),
    "year_2": dict(label="大二", grad="2029-06-30", enroll="2025-09-01", stage=LoopStage.DIAGNOSE,
                   lead="career_advisor", grad_year=2029),
    "year_3": dict(label="大三", grad="2028-06-30", enroll="2024-09-01", stage=LoopStage.ACT,
                   lead="path_planner", grad_year=2028),
    "year_4": dict(label="大四", grad="2027-06-30", enroll="2023-09-01", stage=LoopStage.REVIEW,
                   lead="companion_coach", grad_year=2027),
}

GRADE_TASKS = {
    "year_1": [
        ("专业适应与兴趣探索", "2026.09 - 2026.10", "适应",
         ["列出本学期最感兴趣的三门课，写下原因",
          "约一位高年级学长学姐聊专业去向",
          "完成一次职业兴趣测评并记录结果",
          "加入一个与目标方向相关的社团或项目",
          "整理这学期做过的三件事，写成 200 字"]),
        ("社团与项目尝试", "2026.10 - 2026.12", "探索",
         ["在社团里主动承担一次具体任务",
          "找一个可以练手的小项目，两周内做完",
          "旁听一场校内招聘宣讲会",
          "把兴趣和专业的交叉点写成一句话"]),
        ("寒假复盘与方向初判", "2027.01 - 2027.02", "复盘",
         ["寒假读完一本行业入门书",
          "复盘这学期最投入的一件事",
          "把三个可能的方向各写一条主要风险"]),
    ],
    "year_2": [
        ("方向验证", "2026.09 - 2026.12", "验证",
         ["为目标方向做一次信息访谈",
          "把简历初稿写出来（哪怕只有一页）",
          "选一门和目标方向相关的选修课",
          "参加一次与目标方向有关的比赛或项目"]),
        ("项目与证书", "2027.01 - 2027.03", "积累",
         ["完成一个能写进简历的项目",
          "考一个目标方向认可的证书",
          "把项目复盘写成 STAR 格式"]),
        ("暑期实习落地", "2027.04 - 2027.08", "实习",
         ["整理 10 家目标公司的岗位要求",
          "投递至少 8 份暑期实习",
          "准备并模拟一次面试",
          "争取一段可写进简历的实习"]),
    ],
    "year_3": [
        ("简历与项目冲刺", "2026.09 - 2026.12", "备战",
         ["把简历改成目标岗位版本",
          "补齐一个能体现岗位能力的项目",
          "整理目标行业 10 家公司的招聘节奏",
          "做一次完整的模拟面试"]),
        ("寒假实习申请", "2027.01 - 2027.02", "申请",
         ["投递 10 份寒假/日常实习",
          "把项目复盘讲成 3 分钟版本",
          "补齐岗位要求里最缺的一项技能"]),
        ("暑期实习与秋招预热", "2027.03 - 2027.08", "冲刺",
         ["拿到一段核心岗位实习",
          "把实习成果写成可复用的案例",
          "维护一份持续更新的投递表"]),
    ],
    "year_4": [
        ("秋招投递与面试", "2026.09 - 2026.11", "秋招",
         ["确定三档投递名单（冲刺/匹配/保底）",
          "完成 20 份秋招网申",
          "准备并完成 5 场面试",
          "复盘每一场面试的问题"]),
        ("补录与备选", "2026.11 - 2027.01", "兜底",
         ["整理未录用原因并调整定位",
          "准备 2 个备选路径（考公/深造/其他）",
          "保持每周 3 次投递节奏"]),
        ("毕业设计与收尾", "2027.02 - 2027.05", "收尾",
         ["按节点完成毕业设计",
          "把毕业论文与求职材料分开管理",
          "完成毕业前的最后一次复盘"]),
    ],
}

DIMENSIONS = [
    ("SELF-PORTRAIT", "兴趣类型与投入度", "霍兰德 RIASEC + 生涯建构"),
    ("SELF-PORTRAIT", "能力结构与证据", "能力三核（知识/技能/才干）"),
    ("SELF-PORTRAIT", "价值取向", "舒伯工作价值观"),
    ("SELF-PORTRAIT", "性格与协作风格", "大五人格简版"),
    ("SELF-PORTRAIT", "学习方式与节奏", "元认知策略"),
    ("SELF-PORTRAIT", "经历积累", "STAR 经历盘点"),
    ("JOB-MARKET", "目标行业认知", "行业研究框架"),
    ("JOB-MARKET", "岗位要求匹配", "岗位胜任力模型"),
    ("JOB-MARKET", "行业趋势与周期", "PEST + 行业生命周期"),
    ("JOB-MARKET", "地域与机会窗口", "机会成本分析"),
    ("JOB-MARKET", "校招时间窗口", "校招节奏表"),
    ("DECISION-RISK", "方向匹配度", "决策平衡单"),
    ("DECISION-RISK", "决策约束", "约束条件排序"),
    ("DECISION-RISK", "主要风险", "风险矩阵"),
    ("DECISION-RISK", "备选路径", "三叶草模型"),
]


# ---------------------------------------------------------------------------
# HTTP / 数据库小工具
# ---------------------------------------------------------------------------
def http(method: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def api_ok(envelope: dict) -> dict:
    if int(envelope.get("code", -1)) != 0:
        raise RuntimeError(f"API failed: {envelope}")
    return envelope["data"]


def try_http(method: str, path: str, payload: dict | None = None, token: str = ""):
    try:
        return http(method, path, payload, token)
    except urllib.error.HTTPError as exc:
        print(f"    skip {method} {path}: HTTP {exc.code} {exc.read().decode('utf-8', 'replace')[:160]}")
    except Exception as exc:  # noqa: BLE001
        print(f"    skip {method} {path}: {exc}")
    return None


def pget(persona: dict) -> dict:
    return persona


PERSONALITY_STYLES = [
    "偏内向，但对感兴趣的事会主动开口",
    "外向，喜欢在讨论里把想法磨清楚",
    "慢热，熟悉之后表达很直接",
    "理性，习惯先看数据和事实再下判断",
]


def personality_of(persona: dict) -> str:
    return PERSONALITY_STYLES[sum(map(ord, persona["account"])) % len(PERSONALITY_STYLES)]


def jitter(persona: dict, base: float, spread: float = 0.06) -> float:
    rng = random.Random(persona["account"] + str(base))
    return round(min(0.97, max(0.35, base + rng.uniform(-spread, spread))), 2)


# ---------------------------------------------------------------------------
# 生成各类数据
# ---------------------------------------------------------------------------
def make_profile(persona: dict) -> tuple[list[ProfileField], list[ProfileGap]]:
    meta = GRADE_META[persona["grade"]]
    account = persona["account"]
    now = dt()
    src = ProfileSource.CONVERSATION
    fields = [
        ("study_year", "当前学习阶段", meta["label"], 0.98, src, ["开学时本人确认"]),
        ("major", "专业", persona["major"], 0.99, ProfileSource.RECORD, ["学籍信息"]),
        ("degree_level", "层次", persona["degree"], 0.99, ProfileSource.RECORD, ["学籍信息"]),
        ("school", "学校", persona["school"], 0.99, ProfileSource.RECORD, ["学籍信息"]),
        ("expected_graduation", "预计毕业", meta["grad"], 0.9, ProfileSource.RECORD, ["学籍信息"]),
        ("enrollment_status", "学籍状态", "在读", 0.99, ProfileSource.RECORD, ["学籍信息"]),
        ("duration", "学制", "四年", 0.99, ProfileSource.RECORD, ["学籍信息"]),
        ("study_mode", "学习形式", "全日制", 0.99, ProfileSource.RECORD, ["学籍信息"]),
        ("enrolled_at", "入学日期", meta["enroll"], 0.99, ProfileSource.RECORD, ["学籍信息"]),
        ("interest", "兴趣", persona["interest"], 0.86, src, ["对话里提到的具体事情"]),
        ("values", "价值取向", persona["value"], 0.82, src, ["对'稳定还是成长'的回答"]),
        ("experience", "经历", persona["experience"], 0.8, src, ["对话中的经历自述"]),
        ("skills", "能力自评", persona["skills"], 0.78, src, ["对话中的能力自述"]),
        ("strengths", "优势", persona["strengths"], 0.8, src, ["多次提到同类行为"]),
        ("weaknesses", "待提升", persona["weaknesses"], 0.62, src, ["本人主动提到"]),
        ("career_goal", "目标方向", persona["careers"][0], 0.66, src, ["本人表述的目标"]),
        ("preferred_city", "期望就业城市", persona["city"], 0.6, src, ["被问到时提到"]),
        ("work_style", "工作方式偏好", "希望有明确目标和反馈，节奏可以快一点", 0.55, src, ["对话推断，尚待验证"]),
        ("motivation", "当前最重要的动力", "想尽早把方向定下来，不想再漂着", 0.62, src, ["多次提及"]),
        ("constraint", "现实约束", "家庭希望离家近一些，可接受周边省会城市", 0.5, src, ["聊到地域时的回答"]),
        ("personality", "性格特质", personality_of(persona), 0.6, src, ["对话中的自我描述"]),
        ("learning_style", "学习方式", "喜欢先动手做，再回头补理论", 0.58, src, ["对话推断"]),
    ]
    out = [
        ProfileField(
            key=key, label=label, value=value, confidence=conf,
            source=source, evidence=evidence, updated_at=now - timedelta(days=idx),
        )
        for idx, (key, label, value, conf, source, evidence) in enumerate(fields)
    ]
    gaps_src = [
        ("internship_evidence", "实习或项目的量化证据", "还没有一段能和目标岗位对上号的完整经历", "这学期做一次岗位要求对照，把缺口写成清单"),
        ("industry_network", "行业内的信息源", "对目标行业的判断多来自网络，没有一手信息", "约一位从业者做一次 20 分钟信息访谈"),
        ("interview_readiness", "面试表达", "没有做过完整的模拟面试", "周末完成一次一对一模拟面试并复盘"),
        ("portfolio", "作品/案例集", "现有材料还不足以展示岗位要求的能力", "把一个项目整理成可展示的案例"),
        ("timeline", "秋招/实习时间表", "对各家的网申节奏只有模糊印象", "整理一份目标公司的投递时间表"),
    ]
    rng = random.Random(account + "gaps")
    picked = gaps_src if persona["grade"] in {"year_3", "year_4"} else gaps_src[: 3 + rng.randint(0, 1)]
    gaps = [
        ProfileGap(key=key, label=label, reason=reason, suggested_next_action=action)
        for key, label, reason, action in picked[: 4 + rng.randint(0, 2)]
    ]
    return out, gaps


def make_academic(persona: dict) -> AcademicSnapshot:
    rng = random.Random(persona["account"] + "academic")
    courses = []
    for idx, name in enumerate(persona["courses"]):
        courses.append(
            CourseEntry(
                name=name,
                teacher=f"{'李王张刘陈赵周吴'[idx % 8]}老师",
                weekday=(idx % 5) + 1,
                start_period=(idx % 3) * 2 + 1,
                end_period=(idx % 3) * 2 + 2,
                weeks="1-16周",
                place=f"{'文理教学楼' if idx % 2 else '综合楼'}{201 + idx}",
                credit=f"{1 + idx % 3}.0",
                category="必修" if idx < 4 else "选修",
            )
        )
    generic = ["大学英语", "体育", "马克思主义基本原理", "大学生职业发展与就业指导"]
    grades = []
    for name in [*persona["courses"], *generic]:
        score = rng.randint(72, 96)
        grades.append(
            GradeEntry(
                term="2026-2027-1",
                name=name,
                credit=f"{1 + (len(grades) % 3)}.0",
                score=str(score),
                point=f"{(score - 50) / 10:.1f}",
                category="必修" if grades.__len__() % 3 else "选修",
                kind="必修" if grades.__len__() % 3 else "选修",
            )
        )
    return AcademicSnapshot(
        school=persona["school"],
        source="json",
        term="2026-2027-1",
        courses=courses,
        grades=grades,
        imported_at=dt(-3).isoformat(),
        note="",
    )


def make_notes(persona: dict, plan: ActionPlan) -> list[UserNote]:
    account = persona["account"]
    rng = random.Random(account + "notes")
    texts = [
        ("goal", f"{GRADE_META[persona['grade']]['label']}结束前把方向从「{persona['careers'][0]}」缩小到两个具体岗位"),
        ("goal", "每个月至少和一位从业者聊一次"),
        ("todo", "把上次面试的问题整理成清单"),
        ("todo", "这周投三家目标公司"),
        ("todo", "看完岗位 JD 后改一版简历"),
        ("todo", "把项目复盘写成 STAR 三段"),
        ("todo", "约同学做一次模拟面试"),
        ("goal", "六级/证书按计划刷完"),
        ("todo", "把课程表和自习时间合起来排一版周计划"),
        ("todo", "整理作品集里最能打的三个项目"),
        ("todo", "给导师发邮件确认毕设选题"),
        ("todo", "把这学期的成绩单导出存档"),
    ]
    notes: list[UserNote] = []
    first_task_text = plan.phases[0].tasks[0].text if plan.phases and plan.phases[0].tasks else "完成本周任务"
    texts.insert(2, ("todo", first_task_text))
    for idx, (kind, text) in enumerate(texts[: 9 + rng.randint(0, 3)]):
        created = dt(-rng.randint(1, 30))
        notes.append(
            UserNote(
                id=f"note_{account}_{idx}",
                user_id=account, kind=kind, text=text,
                done=(kind == "todo" and rng.random() < 0.35),
                created_at=created, updated_at=created,
            )
        )
    return notes


def make_action_plan(persona: dict, main_plan_id: str) -> ActionPlan:
    rng = random.Random(persona["account"] + "plan")
    meta = GRADE_META[persona["grade"]]
    phases: list[ActionPhase] = []
    task_seq = 0
    weekday_today = NOW.weekday()
    for phase_idx, (name, date_range, tag, tasks) in enumerate(GRADE_TASKS[persona["grade"]]):
        phase_tasks: list[ActionTask] = []
        base_day = -45 + phase_idx * 30
        for task_idx, text in enumerate(tasks):
            task_seq += 1
            due = dt(base_day + 10 + task_idx * 4)
            roll = rng.random()
            if roll < 0.34:
                status, progress, done = "completed", 100, True
                due = min(due, dt(-3 - rng.randint(0, 20)))
                done_at = due
            elif roll < 0.55:
                status, progress, done, done_at = "in_progress", rng.choice([25, 40, 60, 80]), False, None
            elif roll < 0.68:
                status, progress, done, done_at = "waiting", rng.choice([10, 30]), False, None
            else:
                status, progress, done, done_at = "pending", 0, False, None
            # 未完成的任务不要挂在过去：主界面「现在做」不该第一眼就是一条过期任务
            if not done and due < dt(1):
                due = dt(1 + task_idx + phase_idx * 2)
            phase_tasks.append(
                ActionTask(
                    id=f"task-{persona['account']}-{task_seq}",
                    text=text,
                    due_date=due,
                    done=done,
                    done_at=done_at,
                    status=status,
                    progress=progress,
                    waiting_reason="等对方回复实习岗位信息" if status == "waiting" else "",
                    scheduled_at=(due - timedelta(days=1)) if status in {"in_progress", "pending"} else None,
                    estimated_minutes=rng.choice([20, 30, 45, 60, 90]),
                )
            )
        phases.append(
            ActionPhase(
                id=f"phase-{persona['account']}-{phase_idx + 1}",
                name=name,
                date_range=date_range,
                tag=tag,
                tasks=phase_tasks,
                starts_at=dt(-45 + phase_idx * 30),
                ends_at=dt(-45 + phase_idx * 30 + 40),
            )
        )
    return ActionPlan(
        id=f"act_{persona['account']}",
        plan_id=main_plan_id,
        phases=phases,
        reminders_synced=True,
    )


def make_report(persona: dict, version: int) -> Report:
    rng = random.Random(persona["account"] + str(version))
    meta = GRADE_META[persona["grade"]]
    strengths = persona["strengths"]
    weaknesses = persona["weaknesses"]
    career = persona["careers"][0]
    tags = ["优势", "待验证", "优势", "待验证", "优势", "优势",
            "待验证", "待验证", "待验证", "待验证", "优势",
            "待验证", "优势", "待验证", "待验证"]
    dims: list[ReportDimensionGroup] = []
    groups = {"SELF-PORTRAIT": [], "JOB-MARKET": [], "DECISION-RISK": []}
    for idx, (group, name, method) in enumerate(DIMENSIONS, start=1):
        tag = tags[idx - 1] if version == 1 else ("优势" if idx % 4 != 0 else "待验证")
        if tag == "短板":
            tag = "待验证"
        evidence = (
            f"画像字段：{persona['interest']}"
            if idx <= 6
            else f"外部情报与岗位要求对照（第{idx}维）"
        )
        conclusion = {
            1: f"兴趣集中在{persona['interest'][:18]}…，与{career}方向有交叉",
            2: f"能力上最强的是{strengths[0]}，能拿出经历的证据还不够系统",
            3: f"你更看重{persona['value'][:14]}，这会影响对岗位类型的取舍",
            4: f"协作风格：{personality_of(persona)}，适合有明确目标的小团队",
            5: f"学习方式偏动手，先做再补理论，适合项目驱动",
            6: f"经历里能写进简历的是：{persona['experience'][:20]}…",
            7: f"对{persona['industry']}的判断主要来自公开信息，还缺一手信源",
            8: f"{career}岗位的硬性要求和当前准备之间还差一到两项",
            9: f"{persona['industry']}处在结构调整期，岗位数量与门槛都在变",
            10: f"目标城市是{persona['city']}，机会密度与生活成本需要一起算",
            11: f"距离{meta['label']}结束还有时间，但关键窗口在下一次招聘季",
            12: f"三条路径里，{career}与你的兴趣、能力匹配度最高",
            13: f"现实约束里，地域和家庭期望会限制可选范围",
            14: f"主要风险是准备度不足与信息滞后，而不是能力不行",
            15: f"备选路径可以是{persona['careers'][1]}，需要提前准备材料",
        }[idx]
        groups[group].append(
            ReportDimensionItem(index=idx, name=name, tag=tag, conclusion=conclusion, evidence=evidence)
        )
    for group, items in groups.items():
        dims.append(
            ReportDimensionGroup(
                group=group,
                group_method={
                    "SELF-PORTRAIT": "霍兰德 RIASEC + 能力三核",
                    "JOB-MARKET": "行业研究框架 + 岗位胜任力",
                    "DECISION-RISK": "决策平衡单 + 风险矩阵",
                }[group],
                items=items,
            )
        )
    if version == 1:
        verdict = Verdict(
            title=f"先把{career}方向从「想做」变成「有条件做」",
            summary=(
                f"你在{persona['interest'][:14]}上有真实投入，"
                f"但{career}的第一道门槛不是意愿而是证据：一段对得上的经历、一份能过筛的简历、"
                f"一次完整的模拟面试。{meta['label']}这一阶段最值得做的，是把这三件事补齐，"
                f"而不是再换方向。"
            ),
        )
    else:
        verdict = Verdict(
            title=f"{career}仍是主线，但要把证据补齐到可投递",
            summary=(
                f"和上一版相比，你的方向没有变，变的是准备度："
                f"已经补了项目与信息访谈，还差投递节奏和面试。"
                f"接下来两个月，按阶段任务推进就能把「想做」变成「能投」。"
            ),
        )
    return Report(
        id=f"rpt_{persona['account']}",
        user_id=persona["account"],
        version=version,
        generated_at=dt(-14 if version == 1 else -2),
        verdict=verdict,
        swot=Swot(
            strength=[strengths[0],
                      strengths[1] if len(strengths) > 1 else strengths[0],
                      strengths[2] if len(strengths) > 2 else strengths[0]],
            weakness=[weaknesses[0], weaknesses[1] if len(weaknesses) > 1 else weaknesses[0]],
            opportunity=[f"{persona['industry']}对真实项目经历的需求在上升",
                         f"{meta['label']}阶段还有试错空间，可以低成本验证"],
            risk=["岗位竞争集中在准备充分的候选人上",
                  "如果只停留在信息收集，下一次窗口会再错过"],
        ),
        dimensions=dims,
        gap_claims=[
            GapClaim(gap_id="internship_evidence", label="实习或项目的量化证据", claimed_at=dt(-10)),
            GapClaim(gap_id="interview_readiness", label="面试表达", claimed_at=dt(-6)),
        ],
        sources=["学职平台岗位要求", "目标公司校招 JD", "行业公开报告"],
        methodologies=["霍兰德 RIASEC", "能力三核", "决策平衡单", "SWOT"],
    )


def make_direction_plans(persona: dict) -> list[DirectionPlan]:
    plans = []
    for idx, (name, role) in enumerate(zip(persona["careers"], [PlanRole.MAIN, PlanRole.PARALLEL, PlanRole.FALLBACK])):
        plans.append(
            DirectionPlan(
                id=f"dir_{persona['account']}_{idx}",
                name=name,
                role=role,
                target_desc={
                    PlanRole.MAIN: f"以{name}为主攻，目标是拿到一段核心实习并在下一次招聘季投递",
                    PlanRole.PARALLEL: f"并行准备{name}方向，作为主线的补充选项",
                    PlanRole.FALLBACK: f"把{name}作为保底路径，先解决「有工作」再谈理想",
                }[role],
                match_score=jitter(persona, [0.84, 0.72, 0.58][idx]),
                match_method="三叶草契合度 × 可达性（兴趣、能力、价值 与 岗位门槛）",
                gaps=[
                    PlanGap(requirement=f"{name}岗位要求", current_state=f"已有{persona['experience'][:16]}…",
                            suggestion="把经历整理成岗位语言能读懂的证据"),
                    PlanGap(requirement="可投递的材料", current_state="简历与作品还在草稿状态",
                            suggestion="两周内完成一版可投递材料"),
                ],
                fit_reason=f"你的兴趣（{persona['interest'][:12]}…）与{name}的日常工作最接近",
                main_risk=f"准备度不足：{persona['weaknesses'][0]}",
                selected=(idx == 0),
                selected_at=dt(-8) if idx == 0 else None,
            )
        )
    return plans


def make_calendar(persona: dict) -> list[CalendarNode]:
    meta = GRADE_META[persona["grade"]]
    career = persona["careers"][0]
    items = [
        (f"{career}方向·信息访谈", dt(3), "coach"),
        ("把简历改成目标岗位版本", dt(6), "planner"),
        ("本周投递节奏：3 家", dt(9), "planner"),
        ("模拟面试（找同学）", dt(12), "coach"),
        ("目标公司网申截止", dt(18), "planner"),
        ("阶段复盘：这一个月做成了什么", dt(24), "coach"),
        ("期末课程作业提交", dt(35), "manual"),
        ("寒假实习申请截止", dt(52), "planner"),
        ("招聘季关键节点（关注官网）", dt(70), "planner"),
        ("毕业设计中期检查", dt(120), "manual"),
    ]
    if persona["grade"] in {"year_3", "year_4"}:
        items += [
            ("秋招/暑期实习提前批开始", dt(28), "planner"),
            ("目标行业笔试集中期", dt(45), "planner"),
        ]
    return [
        CalendarNode(node_id=f"cal-{persona['account']}-{idx}", user_id=persona["account"],
                     title=title, due_at=due, source=source, related_task_text="")
        for idx, (title, due, source) in enumerate(items)
    ]


def make_track_events(persona: dict, plan: ActionPlan) -> list[TrackEvent]:
    rng = random.Random(persona["account"] + "track")
    completed = [t for phase in plan.phases for t in phase.tasks if t.done]
    events = []
    for idx, task in enumerate(completed[:6]):
        events.append(TrackEvent(
            id=f"track-{persona['account']}-{idx}",
            user_id=persona["account"], type="milestone_done",
            title=f"完成：{task.text}",
            detail="按计划完成，已记录到你的完成记录里。",
            occurred_at=task.done_at or dt(-rng.randint(2, 20)),
        ))
    events += [
        TrackEvent(id=f"track-{persona['account']}-r1", user_id=persona["account"], type="reminder",
                   title="本周还有 2 件计划内任务未开始", detail="如果时间不够，可以把其中一件挪到周末。",
                   occurred_at=dt(-1), due_at=dt(2)),
        TrackEvent(id=f"track-{persona['account']}-s1", user_id=persona["account"], type="semester_review",
                   title="上学期复盘已生成", detail=f"这学期重点：{persona['careers'][0]}方向的准备度。",
                   occurred_at=dt(-25), related_stage="review"),
        TrackEvent(id=f"track-{persona['account']}-w1", user_id=persona["account"], type="warning",
                   title="有一条任务已停滞 10 天", detail="任务：把岗位 JD 对照成能力清单。可以先拆成 15 分钟的一步。",
                   occurred_at=dt(-4), related_stage="act"),
        TrackEvent(id=f"track-{persona['account']}-c1", user_id=persona["account"], type="coach_message",
                   title="陪跑提醒：不用现在就做决定", detail="方向可以改，先把手头这一小步做完。",
                   occurred_at=dt(-2), related_stage="review"),
    ]
    return events


SESSION_SCRIPTS = {
    "collect": [
        ("agent", "你好，我是建档分析师。先确认一下：你目前处于哪个学习阶段？"),
        ("user", "我是{grade}，{major}专业。"),
        ("agent", "收到。抛开专业，有没有什么事你愿意反复做、做起来不觉得累？"),
        ("user", "{interest}"),
        ("agent", "这个兴趣和你现在学的专业有交叉吗？"),
        ("user", "有交叉，但还不太系统，主要是自己摸索。"),
        ("agent", "了解。找工作的时候，你更在意稳定，还是更在意能不能长本事？"),
        ("user", "{value}"),
        ("agent", "最后一条：到目前为止，你花时间最多的那件事是什么？"),
        ("user", "{experience}"),
        ("agent", "记下了。围绕你的兴趣、能力和价值取向，我建议下一步先做一次方向信息验证，而不是马上定死。"),
    ],
    "diagnose": [
        ("agent", "我是职业顾问。根据目前的画像，我先给你一个判断：你的方向不算错，缺的是可验证的证据。"),
        ("user", "那我现在差在哪？"),
        ("agent", "两条。一是和目标岗位对得上的经历；二是能过筛的材料。这两条能在本学期补上。"),
        ("user", "听起来有点多。"),
        ("agent", "不用一次补完。先做一条：把目标岗位的要求拆成一张清单，和你现有的经历逐项对。"),
        ("user", "好，我这周做。"),
        ("agent", "做完之后告诉我结果，我帮你判断哪条差距值得先补。"),
    ],
    "decide": [
        ("agent", "现在有三条路可以走：主攻{career0}、平行{career1}、保底{career2}。我把各自的代价摆出来。"),
        ("user", "主攻会不会风险太大？"),
        ("agent", "会有风险，但你现在有时间试错。主攻的代价是准备强度高，好处是回报也最高。"),
        ("user", "那我兜底选哪条比较稳？"),
        ("agent", "保底选{career2}，需要准备的材料和主攻重合度大概一半，不会白做。"),
        ("user", "行，那就主攻{career0}。"),
        ("agent", "已经记下你的选择。这个选择可以随时撤回，改了之后我只重算受影响的部分。"),
    ],
    "act": [
        ("agent", "我是路径规划师。接下来我们把它拆成今天和本周能做完的事。"),
        ("user", "我从哪儿开始？"),
        ("agent", "先做最小的一步：把目标岗位的三条要求抄下来，20 分钟能完成。"),
        ("user", "这个可以。"),
        ("agent", "做完它我会给你下一步。今天不用做完整个计划。"),
        ("user", "好。"),
    ],
    "review": [
        ("agent", "我是陪伴教练。上次给你的任务，实际做了多少？"),
        ("user", "做了一半，后面卡在不知道怎么写简历。"),
        ("agent", "先不追究为什么没做完。卡住的地方本身就是有用的信息：你可能缺的是一个简历模板，而不是动力。"),
        ("user", "那这周怎么调整？"),
        ("agent", "这周只做一件事：用目标岗位的三条要求改一版简历，其他先停。"),
        ("user", "行。"),
        ("agent", "做完回来告诉我，我帮你过一遍。"),
    ],
}

SESSION_PLAN = {
    "year_1": [("confused", "collect"), ("verify_direction", "diagnose"), ("free_chat", "act"), ("how_to_act", "act")],
    "year_2": [("verify_direction", "diagnose"), ("undecided", "decide"), ("how_to_act", "act"), ("free_chat", "collect")],
    "year_3": [("how_to_act", "act"), ("undecided", "decide"), ("review_due", "review"), ("stuck", "review")],
    "year_4": [("how_to_act", "act"), ("review_due", "review"), ("stuck", "review"), ("undecided", "decide")],
}

TASK_NAMES = {
    "confused": "还不清楚自己适合什么",
    "verify_direction": "想验证某个方向行不行",
    "undecided": "几个方向拿不准",
    "how_to_act": "定了方向不知道怎么动",
    "stuck": "执行卡住了 / 没进展",
    "review_due": "好久没管了 / 该复盘了",
    "free_chat": "直接开聊",
}

STAGE_AGENT = {
    LoopStage.COLLECT: ("profile_analyst", "建档分析师"),
    LoopStage.DIAGNOSE: ("career_advisor", "职业顾问"),
    LoopStage.DECIDE: ("career_advisor", "职业顾问"),
    LoopStage.ACT: ("path_planner", "路径规划师"),
    LoopStage.REVIEW: ("companion_coach", "陪伴教练"),
}

STAGE_OF_SCRIPT = {
    "collect": LoopStage.COLLECT, "diagnose": LoopStage.DIAGNOSE,
    "decide": LoopStage.DECIDE, "act": LoopStage.ACT, "review": LoopStage.REVIEW,
}


def make_sessions(persona: dict):
    account = persona["account"]
    sessions: list[TaskSession] = []
    turns: list[ConversationTurn] = []
    memories: list[ConversationMemory] = []
    turn_seq = 0
    for idx, (task_code, script_key) in enumerate(SESSION_PLAN[persona["grade"]]):
        stage = STAGE_OF_SCRIPT[script_key]
        agent_id, _ = STAGE_AGENT[stage]
        session_id = f"tsk_{account}_{idx + 1}"
        started = dt(-30 + idx * 6)
        status = TaskStatus.COMPLETED if idx < 2 else TaskStatus.ACTIVE
        sessions.append(TaskSession(
            id=session_id, user_id=account, task_code=task_code,
            task_name=TASK_NAMES[task_code], loop_stage=stage, lead_agent=agent_id,
            path_focus=PathFocus.EMPLOYMENT, status=status,
            created_at=started, updated_at=started + timedelta(hours=2),
        ))
        script = SESSION_SCRIPTS[script_key]
        for line_idx, (role, template) in enumerate(script):
            turn_seq += 1
            text = template.format(
                grade=GRADE_META[persona["grade"]]["label"],
                major=persona["major"],
                interest=persona["interest"],
                value=persona["value"],
                experience=persona["experience"],
                career0=persona["careers"][0],
                career1=persona["careers"][1],
                career2=persona["careers"][2],
            )
            turns.append(ConversationTurn(
                id=f"turn-{account}-{turn_seq}",
                user_id=account, task_id=session_id, role=role, text=text,
                loop_stage=stage,
                agent_id=agent_id if role == "agent" else "",
                client_msg_id=f"{account}-{idx}-{line_idx}" if role == "user" else "",
                created_at=started + timedelta(minutes=line_idx * 4),
                renderables=[],
            ))
        memories.append(ConversationMemory(
            id=f"mem-{account}-{idx}",
            user_id=account, task_id=session_id, loop_stage=stage, lead_agent=agent_id,
            summary=f"围绕「{TASK_NAMES[task_code]}」聊了 {len(script)} 轮，"
                    f"确认方向是{persona['careers'][0]}，下一步是补齐可验证的准备证据。",
            last_active_at=started + timedelta(hours=2),
        ))
    return sessions, turns, memories


def make_behavior(persona: dict, plan: ActionPlan, versions: dict[str, int]) -> list[BehaviorLog]:
    rng = random.Random(persona["account"] + "behavior")
    logs: list[BehaviorLog] = []
    today = NOW
    tasks = [t for phase in plan.phases for t in phase.tasks]
    done = [t for t in tasks if t.done]
    events = [
        (BehaviorEventType.ANSWER, {"round": 1}),
        (BehaviorEventType.ANSWER, {"round": 2}),
        (BehaviorEventType.PROFILE_FIELD_UPDATED, {"key": "study_year"}),
        (BehaviorEventType.PROFILE_FIELD_UPDATED, {"key": "interest"}),
        (BehaviorEventType.GAP_CLAIM, {"gap_id": "internship_evidence"}),
        (BehaviorEventType.DECISION_SELECT, {"plan_id": f"dir_{persona['account']}_0"}),
        (BehaviorEventType.REVIEW, {"review_id": f"review_{persona['account']}_1"}),
    ]
    for task in done[:3]:
        events.append((BehaviorEventType.TASK_DONE, {"task_id": task.id}))
    events.append((BehaviorEventType.ASSET_VERSION_CHANGED,
                   {"asset_type": "report", "to_version": versions.get("report", 1)}))
    for idx, (event_type, payload) in enumerate(events):
        logs.append(BehaviorLog(
            id=f"bhv-{persona['account']}-{idx}", user_id=persona["account"],
            event_type=event_type, occurred_at=today - timedelta(days=25 - idx),
            payload=payload, related_asset_ids=[],
        ))
    return logs


# ---------------------------------------------------------------------------
# 写库
# ---------------------------------------------------------------------------
USER_TABLES = (
    "ai_task_result", "biz_academic_snapshot", "biz_asset_content", "biz_asset_version",
    "biz_behavior_log", "biz_calendar_node", "biz_conversation_memory", "biz_conversation_turn",
    "biz_profile", "biz_profile_field", "biz_profile_gap", "biz_student_state",
    "biz_task_session", "biz_track_event", "biz_user_note", "orc_notification",
)


async def wipe_user(db: PostgresDatabase, account: str) -> None:
    for table in USER_TABLES:
        await db.execute(f"DELETE FROM {table} WHERE user_id = $1", account)


async def seed_user(repos: dict, persona: dict) -> dict:
    account = persona["account"]
    db: PostgresDatabase = repos["db"]

    # 1) 账号：注册（HTTP）+ 昵称
    login = try_http("POST", "/app/auth/register", {"account": account, "password": PASSWORD})
    if login is None or login.get("code") != 0:
        login = try_http("POST", "/app/auth/login", {"account": account, "password": PASSWORD})
    if login is None or login.get("code") != 0:
        raise RuntimeError(f"账号创建失败：{account} {login}")
    token = api_ok(login)["token"]
    await db.execute(
        "UPDATE biz_user_account SET payload = jsonb_set(payload, '{nickname}', to_jsonb($2::text)) WHERE id = $1",
        account, persona["name"],
    )

    # 2) 画像 + 缺口
    fields, gaps = make_profile(persona)
    for field in fields:
        await repos["profile"].upsert_field(account, field)
    await repos["profile"].replace_gaps(account, gaps)

    # 3) 教务快照
    academic = make_academic(persona)
    await repos["academic"].upsert(account, academic)

    # 4) 报告（两版）+ 方向方案 + 行动计划
    report1 = make_report(persona, 1)
    report2 = make_report(persona, 2)
    await repos["asset"].save_report(report1)
    await repos["asset"].save_version(AssetVersion(
        id=f"av-{account}-report-1", user_id=account, asset_type=AssetType.REPORT, version=1,
        created_at=dt(-14), depends_on_profile_keys=["interest", "skills"],
        diff_from_previous=None,
    ))
    await repos["asset"].save_report(report2)
    await repos["asset"].save_version(AssetVersion(
        id=f"av-{account}-report-2", user_id=account, asset_type=AssetType.REPORT, version=2,
        created_at=dt(-2), depends_on_profile_keys=["interest", "skills", "experience"],
        diff_from_previous="补了项目经历与信息访谈，结论方向不变，准备度提高",
    ))

    plans = make_direction_plans(persona)
    await repos["asset"].save_version(AssetVersion(
        id=f"av-{account}-dir-1", user_id=account, asset_type=AssetType.DIRECTION_PLAN, version=1,
        created_at=dt(-9), depends_on_profile_keys=["interest", "values"],
    ))
    await repos["asset"].save_direction_plans(account, plans)

    action_plan = make_action_plan(persona, plans[0].id)
    await repos["asset"].save_version(AssetVersion(
        id=f"av-{account}-act-1", user_id=account, asset_type=AssetType.ACTION_PLAN, version=1,
        created_at=dt(-7), depends_on_profile_keys=["interest", "skills"],
    ))
    await repos["asset"].save_action_plan(account, action_plan)

    # 5) 笔记 / 日历 / 跟踪 / 会话 / 行为
    for note in make_notes(persona, action_plan):
        await repos["note"].upsert(note)
    for node in make_calendar(persona):
        await repos["calendar"].upsert_node(account, node)
    for event in make_track_events(persona, action_plan):
        await repos["track"].append_event(account, event)
    sessions, turns, memories = make_sessions(persona)
    for session in sessions:
        await repos["session"].create(session)
    for turn in turns:
        await repos["turn"].append(turn)
    for memory in memories:
        await repos["memory"].upsert(memory)
    behavior = make_behavior(persona, action_plan, {"report": 2})
    for log in behavior:
        await repos["behavior"].append(log)

    # 6) 学生端状态：偏好 / 学期 / 权重 / 复盘 / 测量（走 HTTP，形状由服务层保证）
    prefs = try_http("GET", "/app/preferences", token=token)
    if prefs and prefs.get("code") == 0:
        try_http("PUT", "/app/preferences", {
            **prefs["data"],
            "proactive_reminders": True,
            "quiet_start": "22:30",
            "quiet_end": "07:30",
            "timezone": "Asia/Shanghai",
            "academic_analysis": True,
            "material_analysis": True,
            "expected": prefs["data"],
        }, token=token)

    semester = try_http("GET", "/app/schedule/semester", token=token)
    if semester is not None and semester.get("code") == 0:
        periods = [{"number": n, "start": f"{8 + (n - 1) * 2:02d}:00", "end": f"{10 + (n - 1) * 2:02d}:00"}
                   for n in range(1, 6)]
        first_monday = NOW.date() - timedelta(days=NOW.weekday()) - timedelta(weeks=5)
        try_http("PUT", "/app/schedule/semester", {
            "first_monday": first_monday.isoformat(),
            "weeks": 20,
            "timezone": "Asia/Shanghai",
            "periods": periods,
            "weekly_available_minutes": 2400,
            "expected": semester["data"],
        }, token=token)

    weights = try_http("GET", "/app/plan/direction-weights", token=token)
    if weights and weights.get("code") == 0:
        try_http("PUT", "/app/plan/direction-weights", {
            "major": 70, "jobs": 85, "salary": 60, "stability": 55, "location": 45,
            "expected": weights["data"],
        }, token=token)

    measurements = try_http("GET", "/app/measurements", token=token)
    if measurements and measurements.get("code") == 0:
        measured_at = dt(-6).isoformat()
        report_dims = [
            ("1", "兴趣倾向", 78),
            ("2", "能力结构", 62),
            ("3", "价值取向", 74),
        ]
        try_http("POST", "/app/measurements", {
            "asset_type": "report",
            "version": 2,
            "subject_id": report2.id,
            "measurements": [
                {"key": key, "label": label, "value": value, "minimum": 0, "maximum": 100,
                 "threshold": 60, "source": "职业兴趣测评（校内）",
                 "method": "测评量表归一化（0-100）", "measured_at": measured_at,
                 "origin": "assessment"}
                for key, label, value in report_dims
            ],
            "expected": [],
        }, token=token)
        for plan_idx, plan in enumerate(plans):
            base = 84 - plan_idx * 10
            try_http("POST", "/app/measurements", {
                "asset_type": "direction_plan",
                "version": 1,
                "subject_id": plan.id,
                "measurements": [
                    {"key": key, "label": label, "value": base - offset, "minimum": 0,
                     "maximum": 100, "threshold": 60,
                     "source": "方向评估工作坊", "method": "维度自评 + 证据折算",
                     "measured_at": measured_at, "origin": "self_report"}
                    for key, label, offset in [
                        ("major", "专业匹配", 0), ("jobs", "岗位匹配", 4),
                        ("salary", "薪资预期", 8), ("stability", "稳定性", 6),
                        ("location", "地域可行", 10),
                    ]
                ],
                "expected": [],
            }, token=token)

    pending = [t for phase in action_plan.phases for t in phase.tasks if not t.done][:2]
    for idx, task in enumerate(pending):
        try_http("POST", "/app/reviews", {
            "task_id": task.id,
            "reason": "按计划推进中的阶段复盘" if idx == 0 else "上一次调整后的效果复盘",
            "note": "这周实际投入比计划少，卡在材料准备上；下一步把任务拆得更小。" if idx == 0
                    else "调整后效率有提升，但还缺少一次真实面试反馈。",
            "result": "continue",
            "adjustment": None,
            "expected_updated_at": None,
        }, token=token)

    # 7) 资产版本快照（方向 / 行动的历史版本正文接口读它）
    snapshots = {
        "direction_plan:1": {
            "asset_type": "direction_plan",
            "version": 1,
            "created_at": dt(-9).isoformat(),
            "content": [plan.model_dump(mode="json") for plan in plans],
        },
        "action_plan:1": {
            "asset_type": "action_plan",
            "version": 1,
            "created_at": dt(-7).isoformat(),
            "content": action_plan.model_dump(mode="json"),
        },
    }
    await db.execute(
        """
        INSERT INTO biz_student_state (user_id, payload, updated_at)
        VALUES ($1, $2::jsonb, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            payload = jsonb_set(
                biz_student_state.payload,
                '{asset_snapshots}',
                COALESCE(biz_student_state.payload -> 'asset_snapshots', '{}'::jsonb) || $2::jsonb
            ),
            updated_at = NOW()
        """,
        account,
        json.dumps(snapshots, ensure_ascii=False),
    )

    # 8) 主动提醒（工作台的 coach_messages / 通知面板读 orc_notification）
    first_pending_text = pending[0].text if pending else "把这周的下一步写下来"
    notices = [
        ("pending", f"这周的下一步：{first_pending_text}", "做完记得勾掉，我会按结果给你下一件。", -2, None),
        ("read", "上周复盘已生成", "看看哪一步有效、哪一步需要调整，再决定要不要改计划。", -6, None),
        ("later", f"{persona['careers'][0]}方向网申截止提醒", "距离截止还有几天，材料准备到哪一步了？", -1, dt(2)),
    ]
    for idx, (state, title, body, days, snooze) in enumerate(notices):
        await db.execute(
            """
            INSERT INTO orc_notification
                (id, user_id, channel, status, title, body, created_at, sent_at,
                 action, related_task_id, processing_status, snoozed_until)
            VALUES ($1, $2, 'in_app', $3, $4, $5, $6, $6, NULL, NULL, $3, $7)
            ON CONFLICT (id) DO NOTHING
            """,
            f"notice-{account}-{idx}", account,
            "read" if state == "read" else state,
            title, body, dt(days), snooze,
        )

    return {
        "account": account, "name": persona["name"], "grade": GRADE_META[persona["grade"]]["label"],
        "profile_fields": len(fields), "turns": len(turns), "tasks": sum(len(p.tasks) for p in action_plan.phases),
    }


async def main() -> None:
    db = PostgresDatabase(DSN, min_size=1, max_size=4)
    await db.pool()
    repos = {
        "db": db,
        "profile": PostgresProfileRepository(db),
        "academic": PostgresAcademicSnapshotRepository(db),
        "asset": PostgresAssetRepository(db),
        "note": PostgresUserNoteRepository(db),
        "calendar": PostgresCalendarNodeRepository(db),
        "track": PostgresTrackEventRepository(db),
        "session": PostgresTaskSessionRepository(db),
        "turn": PostgresConversationTurnRepository(db),
        "memory": PostgresConversationMemoryRepository(db),
        "behavior": PostgresBehaviorRepository(db),
    }
    print(f"seeding {len(PERSONAS)} users -> {API}")
    for persona in PERSONAS:
        await wipe_user(db, persona["account"])
        summary = await seed_user(repos, persona)
        print(
            f"  {summary['account']} {summary['name']} {summary['grade']}: "
            f"画像 {summary['profile_fields']} 项 · 对话 {summary['turns']} 轮 · 任务 {summary['tasks']} 条"
        )
    await db.aclose()
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
