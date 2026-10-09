# Kev-0.8B 接入与联调说明

Kev 是独立的 System One 决策服务，只辅助职业意图分类；原聊天模型继续生成回复、报告和计划。模型权重与 PyTorch 不进入职引镜像。

## 启动

1. 启动本机 Kev，确认 `http://127.0.0.1:8009/v1/models` 返回 `kev-latest`、`device=cpu`、`backend=torch`。
2. 首次部署或代码变更后构建并启动后端：

```powershell
docker compose -f docker-compose.yml -f docker-compose.kev.yml build zhiyin-flash
docker compose -f docker-compose.yml -f docker-compose.kev.yml up -d
```

3. 将既有 PostgreSQL 中的两项试点配置定向切到 active，然后重启后端：

```powershell
uv run --with asyncpg python scripts/kev_config.py active
docker compose -f docker-compose.yml -f docker-compose.kev.yml restart zhiyin-flash
```

新数据库会从 JSON 种子得到 active 配置；已有数据库必须运行上述脚本。不要为这两项配置执行全量 `--resync-registry`。

## 路由口径

- 关键词命中与明确点选均跳过 Kev。
- 自由输入只有在开关开启、模式为 active、消息不超过 6000 字，并且 `confidence >= 0.55`、首选概率 `>= 0.70` 时采用 Kev。
- `unclear`、低阈值、非法响应、网络错误或超过 10 秒均沿用原流程。
- `shadow` 会调用并记录，但永不采用；`off` 完全不调用。
- 决策依据写在 ANSWER 行为日志的 `payload.intent_decision`。

## 切换和恢复

```powershell
uv run --with asyncpg python scripts/kev_config.py shadow
uv run --with asyncpg python scripts/kev_config.py off
uv run --with asyncpg python scripts/kev_config.py restore
```

脚本第一次修改前将原值保存为 `scripts/kev-config-backup.json`，且只修改 `decision_intent_routing` 和 `decision_routing`。每次切换后重启后端，或调用项目已有的配置重载入口。

## 真实联调

脚本会创建测试账号、验证 active 采用、低置信度回退和重复消息幂等：

```powershell
uv run --with asyncpg python scripts/kev_smoke.py
```

验证 Kev 停止后的安全回退：先将服务保持 active，停止 Kev，再执行：

```powershell
uv run --with asyncpg python scripts/kev_smoke.py --expect-kev-down
```

查看后端日志：

```powershell
docker logs --tail 200 zhiyin-flash
```

其中每个新消息会输出一条 `decision_routing` 记录，可检查最终意图、候选、来源、是否采用、回退原因、confidence、概率和 Kev 延迟；日志不会包含用户消息正文。

## 关闭顺序

1. `python scripts/kev_config.py off`。
2. 重启职引后端，使动态配置生效。
3. 停止 Kev。

只停止 Kev 不会令职引接口失败，但每条未命中关键词的自由输入都会等待决策超时后再回退。
