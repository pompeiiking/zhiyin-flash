# Kev-0.8B 接入与联调说明

Kev 是独立的 System One 决策服务，只辅助职业意图分类；原聊天模型继续生成回复、报告和计划。模型权重与 PyTorch 不进入职引镜像。

> **本机部署记录（2026-10-17）**
>
> - 实际安装目录是 `D:\ai-models\kev`（本文下面写的 `E:\ai-models\kev` 是早先的位置，本机不存在该目录；`install-startup.ps1` 用 `-KevRoot D:\ai-models\kev` 注册自启）。
> - 模型 `jaredpalmer/kev-0.8b@v1.0`，当前以 **CPU / float32** 运行（PyPI 的 torch 是 CPU 版，未启用本机 4070）；分类耗时首轮约 2.5 s，前缀缓存命中后约 0.7 s，仍低于 10 s 超时。
> - Kev 目录里有三个本地脚本：`start.ps1`、`status.ps1`、`stop.ps1`，加一个 `serve_clean.py`（见下面两条踩坑）；模型权重与 HF 缓存放在 `D:\ai-models\kev\.hf-cache`。
> - 两个踩坑：① PyPI 上的 `kev` 是另一个无关项目（K.E.V. ORM），**必须从 `https://github.com/jaredpalmer/kev` 源码安装**；② 本机 `NO_PROXY` 里带 `[::1]`，httpx 会抛 `InvalidURL: Invalid port: ':1]'`，`serve_clean.py` 在 Python 侧清洗后再启动 `kev.serve`。
> - 后端接线写进了 `.env` 的 `ZHIYIN_DECISION_*`（与 `docker-compose.kev.yml` 叠加层同值），因此不带叠加层的 `docker compose up -d` 也不会丢；已验证 `kev_smoke.py` 的采用、低置信度回退、重复消息幂等三项全部通过。


## 启动

1. 启动已安装的本机 Kev（当前目录 `E:\ai-models\kev`，执行 `start.ps1`）。等待 `http://127.0.0.1:8009/v1/models` 返回 `kev-latest`；以返回的 device、backend 为准，不要求固定 CPU。仅有进程不代表模型已加载。
2. 首次部署或代码变更后构建并启动后端：

```powershell
docker compose -f docker-compose.yml -f docker-compose.kev.yml build zhiyin-flash
docker compose -f docker-compose.yml -f docker-compose.kev.yml up -d
```

3. 将既有 PostgreSQL 中的两项试点配置定向切到 active，然后重启后端：

```powershell
uv run --with asyncpg python scripts/integrations/kev/kev_config.py active
docker compose -f docker-compose.yml -f docker-compose.kev.yml restart zhiyin-flash
```

新数据库会从 JSON 种子得到 active 配置；已有数据库必须运行上述脚本。不要为这两项配置执行全量 `--resync-registry`。

### 旧草稿策略迁移（保留已有分类规则）

旧数据库可能使用 `status=draft`、`min_confidence`、`min_probability` 和 `prompt_version`。当前路由要求 confirmed 状态及新字段；仅打开功能开关或把 mode 改成 active 不足以启用。

在配置了当前数据库连接的后端环境运行：

```powershell
python zhiyin-src/template/scripts/migrate_decision_routing.py
python zhiyin-src/template/scripts/migrate_decision_routing.py --apply --backup decision-routing-before.json
```

第一条仅预览，第二条显式启用并迁移这一条策略。备份文件必须不存在；保留原阈值及分类规则，拒绝新旧阈值冲突和不合法候选。此脚本不打开功能开关，须另核对 `decision_intent_routing` 为 true。切换脚本 `kev_config.py` 则使用仓库种子重建策略，两者用途不同。

## 路由口径

- 关键词命中与明确点选均跳过 Kev。
- 自由输入只有在开关开启、模式为 active、消息不超过 6000 字，并且 `confidence >= 0.55`、首选概率 `>= 0.70` 时采用 Kev。
- `unclear`、低置信度、非法响应、网络错误或超过配置的 `ZHIYIN_DECISION_TIMEOUT_S` 均沿用原流程；以运行配置为准，不把超时回退算作 Kev 已采用。
- `shadow` 会调用并记录，但永不采用；`off` 完全不调用。
- 决策依据写在 ANSWER 行为日志的 `payload.intent_decision`。

## 切换和恢复

```powershell
uv run --with asyncpg python scripts/integrations/kev/kev_config.py shadow
uv run --with asyncpg python scripts/integrations/kev/kev_config.py off
uv run --with asyncpg python scripts/integrations/kev/kev_config.py restore
```

脚本第一次修改前将原值保存为 `scripts/kev-config-backup.json`，且只修改 `decision_intent_routing` 和 `decision_routing`。每次切换后重启后端，或调用项目已有的配置重载入口。

## 真实联调

脚本会创建测试账号、验证 active 采用、低置信度回退和重复消息幂等：

```powershell
uv run --with asyncpg python scripts/integrations/kev/kev_smoke.py
```

验证 Kev 停止后的安全回退：先将服务保持 active，停止 Kev，再执行：

```powershell
uv run --with asyncpg python scripts/integrations/kev/kev_smoke.py --expect-kev-down
```

查看后端日志：

```powershell
docker logs --tail 200 zhiyin-flash
```

其中每个新消息会输出一条 `decision_routing` 记录，可检查最终意图、候选、来源、是否采用、回退原因、confidence、概率和 Kev 延迟；日志不会包含用户消息正文。

## 关闭顺序

1. `python scripts/integrations/kev/kev_config.py off`。
2. 重启职引后端，使动态配置生效。
3. 停止 Kev。

只停止 Kev 不会令职引接口失败，但每条未命中关键词的自由输入都会等待决策超时后再回退。
