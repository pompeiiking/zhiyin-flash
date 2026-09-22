# 职引 · 一键重新部署（Windows）
#
# 与 部署说明.md 第一节的四条命令逐条对应，顺序不能改：
# 先建库与 Redis，再把策略/配置/用户数据迁进去，最后起应用与前端。
# 反过来的话应用会先按空库建表并种下默认配置，迁移随后以 replace 覆盖 ——
# 结果一样，但中间会多出一段"模型不可用"的启动，排查时容易误判。

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$dsn = "postgresql://zhiyin:zhiyin@postgres:5432/zhiyin"

# 部署前的两处人工确认。放在这里而不是"写在文档里"，是因为这两条都属于
# "不报错的错"：密钥没换看不出来，嵌入没接上也只在用的时候少一句依据。
$envFile = Join-Path (Get-Location) ".env"
if (-not (Test-Path -LiteralPath $envFile)) { throw "缺少 .env（compose 需要它提供 ZHIYIN_AUTH_JWT_SECRET）" }
$envText = Get-Content -LiteralPath $envFile -Raw -Encoding UTF8

# ① 令牌签名密钥：出厂值是占位串。占位串等于"所有人都知道你的签名密钥"。
$secretLine = [regex]::Match($envText, "(?m)^\s*ZHIYIN_AUTH_JWT_SECRET\s*=\s*(.+?)\s*$")
if (-not $secretLine.Success) { throw ".env 里没有 ZHIYIN_AUTH_JWT_SECRET" }
$secret = $secretLine.Groups[1].Value.Trim()
if ($secret -eq "change-me-in-production-32bytes-min" -or $secret.Length -lt 32) {
    throw @"
请先把 .env 里的 ZHIYIN_AUTH_JWT_SECRET 换成一段随机串（至少 32 个字符）。
生成一条：
  powershell -NoProfile -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"
换完之后：库里已有的登录令牌会失效（用户重新登录一次即可），其余数据不受影响。
"@
}

Write-Host "[1/4] 构建镜像（应用 + 前端）…"
docker compose build
if ($LASTEXITCODE -ne 0) { throw "镜像构建失败" }

Write-Host "[2/4] 起 postgres 与 redis…"
docker compose up -d postgres redis
if ($LASTEXITCODE -ne 0) { throw "基础设施启动失败" }

Write-Host "[3/4] 导入迁移文件（策略与配置 + 用户数据）…"
docker compose run --rm zhiyin-flash python scripts/migrate_db.py import --dsn $dsn --in /migration/migration.json
if ($LASTEXITCODE -ne 0) { throw "迁移导入失败" }

Write-Host "[4/4] 起应用与前端…"
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "应用启动失败" }

Write-Host ""
Write-Host "完成。前端 http://127.0.0.1:5173 ；接口文档 http://127.0.0.1:8000/api/v1/docs"
Write-Host "自查：docker compose run --rm zhiyin-flash python scripts/migrate_db.py verify --dsn $dsn --in /migration/migration.json"
