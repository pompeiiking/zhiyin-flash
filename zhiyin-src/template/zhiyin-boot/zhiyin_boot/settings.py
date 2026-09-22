"""启动配置。

第一期全部走环境变量，不引入配置中心。
`.env` 文件（仓库根 / 模板目录 / 当前工作目录，就近优先）由 `from_env()`
自动加载，**已显式设置的环境变量优先于 `.env`**——与 docker-compose、
dotenv 的通用语义一致：容器/CI 里用真实环境变量，本地裸跑用 `.env`。
不引入 python-dotenv 依赖：加载逻辑只有十几行，且必须能控制优先级。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# 模板目录锚点：zhiyin-boot/zhiyin_boot/settings.py → zhiyin-src/template
_TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
# 仓库根：template 的上两级（zhiyin-src/template → 仓库根）
_REPO_ROOT = _TEMPLATE_ROOT.parents[1]


def _resolve_local_dir(value: str) -> str:
    """把相对的数据目录按"就近"解析：当前目录 → 模板目录 → 仓库根。

    口径与 `_load_dotenv` 一致，理由是踩过同一个坑：
    这几个目录（data / data/registry / data/knowledge / data/objects）一直写成
    纯相对路径，于是**从仓库根启动**时 `data/registry` 并不存在，
    而"种子文件缺失"在导入那一侧是**静默跳过**的 ——
    结果是：代码里加了新配置、测试里过了、跑起来那一类永远导不进去，
    还不报错。配置要真的落地，路径就不能取决于你在哪个目录敲命令。
    """
    path = Path(value)
    if path.is_absolute() or path.exists():
        return str(path)
    for base in (_TEMPLATE_ROOT, _REPO_ROOT):
        candidate = base / value
        if candidate.is_dir():
            return str(candidate)
    return value


def _load_dotenv() -> None:
    """从就近的 `.env` 补齐环境变量；不覆盖已显式设置的变量。

    查找顺序（先找到先用）：当前工作目录 → 模板目录 → 仓库根。
    解析规则：`KEY=VALUE`；忽略空行与 `#` 注释；值两侧引号剥掉；
    行内 `#` 注释只在没有引号包裹时截断。
    """
    for base in (Path.cwd(), _TEMPLATE_ROOT, _REPO_ROOT):
        candidate = base / ".env"
        if not candidate.is_file():
            continue
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            elif " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            os.environ[key] = value
        return


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = _env(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = _env(key)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    """运行配置。"""

    # ---------- 应用 ----------
    app_name: str = "职引"
    env: str = "local"                     # local / dev / prod
    api_prefix: str = "/api/v1"

    # ---------- 外部存储 ----------
    # 只保留 Redis 与 PostgreSQL + pgvector。
    use_redis: bool = False
    redis_url: str = "redis://redis:6379/0"
    redis_key_prefix: str = "zhiyin"
    #: 加密密钥（AES-GCM）。只在配了它时装配真安全实现 —— 它保护的是库里的数据，
    #: 所以不能和那些数据放在一起，只能从环境来。
    security_key: str = ""
    #: 通用网络搜索：配了密钥才装配。没配就是"这个能力位没接"，不假装能搜。
    search_api_key: str = ""
    search_endpoint: str = "https://api.search.brave.com/res/v1/web/search"

    use_postgres: bool = False
    postgres_dsn: str = "postgresql://zhiyin:zhiyin@postgres:5432/zhiyin"
    auth_jwt_secret: str = ""
    auth_token_ttl_s: int = 86400

    # ---------- AI 模型 ----------
    use_remote_llm: bool = False
    use_remote_embedding: bool = False
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-flash"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    embedding_model: str = "doubao-embedding-text-240715"
    #: 嵌入走哪家：`doubao`（云端 Ark）或 `ollama`（本机 Ollama）。
    #: 两者都是 OpenAI 兼容协议，差别只在默认地址与署名 ——
    #: 但"现在到底用哪个"必须能一眼看出来，不能靠 base_url 猜。
    embedding_provider: str = "doubao"

    # ---------- 学职平台 ----------
    xuezhi_base_url: str = "https://xz.chsi.com.cn"
    xuezhi_request_interval_s: float = 0.25

    # ---------- 学信网在线验证 ----------
    # 只走"在线验证码核验"这一条官方通道：用户自己在学信档案申请报告，
    # 我们凭码去官方验证页读结果。不需要、也不接受用户的学信网账号密码。
    chsi_base_url: str = "https://www.chsi.com.cn"
    chsi_request_interval_s: float = 0.5

    # ---------- 本地实现参数 ----------
    local_data_dir: str = "data"
    local_object_dir: str = "data/objects"
    local_registry_dir: str = "data/registry"
    local_knowledge_dir: str = "data/knowledge"

    # ---------- 调度 ----------
    # 只放**运行节奏**（多久扫一次），不放**规则参数**（停几天算停滞）。
    # 规则参数走动态资源：data/registry/policy_params.json（见 PolicyParamSet）。
    stall_check_interval_s: float = 3600.0
    # Worker 轮询间隔。同进程部署时每个 Worker 按该间隔跑一轮；独立部署
    # （python -m zhiyin_boot worker <name>）时同样使用这个值。
    worker_interval_s: float = 60.0

    # ---------- 功能开关 ----------
    # 注意：功能开关属于**动态资源**，
    # 不在这里存值，而是由 LocalFeatureFlagStore 读 data/registry/feature_flags.json。
    # 禁止再往本类里加文案 / 开关 / 规则类常量。

    @classmethod
    def from_env(cls) -> "Settings":
        """构造配置：先自动加载就近的 `.env`，再读环境变量。"""
        _load_dotenv()
        return cls(
            env=_env("ZHIYIN_ENV", "local"),
            use_redis=_env_bool("ZHIYIN_USE_REDIS"),
            redis_url=_env("ZHIYIN_REDIS_URL", "redis://redis:6379/0"),
            security_key=_env("ZHIYIN_SECURITY_KEY"),
            search_api_key=_env("ZHIYIN_SEARCH_API_KEY"),
            search_endpoint=_env(
                "ZHIYIN_SEARCH_ENDPOINT",
                "https://api.search.brave.com/res/v1/web/search",
            ),
            redis_key_prefix=_env("ZHIYIN_REDIS_KEY_PREFIX", "zhiyin"),
            use_postgres=_env_bool("ZHIYIN_USE_POSTGRES"),
            postgres_dsn=_env(
                "ZHIYIN_POSTGRES_DSN",
                "postgresql://zhiyin:zhiyin@postgres:5432/zhiyin",
            ),
            auth_jwt_secret=_env(
                "ZHIYIN_AUTH_JWT_SECRET",
                "",
            ),
            auth_token_ttl_s=_env_int("ZHIYIN_AUTH_TOKEN_TTL_S", 86400),
            use_remote_llm=_env_bool(
                "ZHIYIN_USE_REMOTE_LLM", _env_bool("ZHIYIN_USE_REMOTE_AI")
            ),
            use_remote_embedding=_env_bool(
                "ZHIYIN_USE_REMOTE_EMBEDDING", _env_bool("ZHIYIN_USE_REMOTE_AI")
            ),
            llm_api_key=_env("ZHIYIN_LLM_API_KEY"),
            llm_base_url=_env("ZHIYIN_LLM_BASE_URL", "https://api.deepseek.com"),
            llm_model=_env("ZHIYIN_LLM_MODEL", "deepseek-flash"),
            embedding_api_key=_env("ZHIYIN_EMBEDDING_API_KEY"),
            embedding_base_url=_env(
                "ZHIYIN_EMBEDDING_BASE_URL",
                "https://ark.cn-beijing.volces.com/api/v3",
            ),
            embedding_model=_env(
                "ZHIYIN_EMBEDDING_MODEL", "doubao-embedding-text-240715"
            ),
            embedding_provider=_env("ZHIYIN_EMBEDDING_PROVIDER", "doubao"),
            xuezhi_base_url=_env(
                "ZHIYIN_XUEZHI_BASE_URL", "https://xz.chsi.com.cn"
            ),
            xuezhi_request_interval_s=_env_float(
                "ZHIYIN_XUEZHI_REQUEST_INTERVAL_S", 0.25
            ),
            chsi_base_url=_env("ZHIYIN_CHSI_BASE_URL", "https://www.chsi.com.cn"),
            chsi_request_interval_s=_env_float(
                "ZHIYIN_CHSI_REQUEST_INTERVAL_S", 0.5
            ),
            local_data_dir=_resolve_local_dir(_env("ZHIYIN_DATA_DIR", "data")),
            local_object_dir=_resolve_local_dir(_env("ZHIYIN_OBJECT_DIR", "data/objects")),
            local_registry_dir=_resolve_local_dir(
                _env("ZHIYIN_REGISTRY_DIR", "data/registry")
            ),
            local_knowledge_dir=_resolve_local_dir(
                _env("ZHIYIN_KNOWLEDGE_DIR", "data/knowledge")
            ),
        )
