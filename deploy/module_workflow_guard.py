"""Hold a target database publication lock across a whole-application cutover.

The fixed helper is sent to the candidate container, so historical images do not
need to contain deployment tooling. It never runs workflows or reads user data.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path


WORKFLOW_PUBLICATION_LOCK = 741517501
PREFIX = "ZHIYIN_WORKFLOW_GUARD="


def validate_snapshots(service, rows):
    """Validate published definitions only; never call the workflow runner."""
    from zhiyin_kernel.modules import ModuleFlowDefinition

    checks = []
    for row in rows:
        raw = row["definition"]
        raw = json.loads(raw) if isinstance(raw, str) else raw
        item = {"workflow_id": row["id"], "revision": row["published_revision"],
                "passed": False, "nodes": []}
        if isinstance(raw, dict):
            for node in raw.get("nodes", []):
                item["nodes"].append({"node_id": node.get("id"), "module_id": node.get("module_id"),
                                      "module_version": node.get("module_version")})
        try:
            service.validate(ModuleFlowDefinition.model_validate(raw))
            item["passed"] = True
        except Exception as exc:  # noqa: BLE001 - Every invalid snapshot blocks activation.
            item["error"] = str(exc)
        checks.append(item)
    return {"passed": all(item["passed"] for item in checks), "workflows": checks}


async def container_main():
    """Linux container entry point. EOF/heartbeat expiry always closes the session."""
    import asyncio
    import sys

    import asyncpg
    from zhiyin_boot.container import build_container
    from zhiyin_boot.settings import Settings

    def emit(kind, **values):
        print(PREFIX + json.dumps({"type": kind, **values}, ensure_ascii=False), flush=True)

    connection = None
    try:
        if os.environ.get("ZHIYIN_MODULE_ENV") != "staging" or os.environ.get("ZHIYIN_RUN_BACKGROUND_WORKERS") != "0":
            raise RuntimeError("工作流发布检查只允许在目标 staging 应用槽执行")
        settings = Settings.from_env()
        if not settings.use_postgres:
            raise RuntimeError("工作流发布锁需要真实 PostgreSQL")
        container = build_container(settings)
        service = container.extra["module_platform"].flows
        connection = await asyncpg.connect(settings.postgres_dsn, timeout=10, command_timeout=10)
        if not await connection.fetchval("SELECT to_regclass('public.biz_module_runtime_revision')"):
            raise RuntimeError("目标数据库缺少发布版本围栏，请先升级平台基线")
        reader = asyncio.StreamReader()
        await asyncio.get_running_loop().connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
        deadline = time.monotonic() + 60
        while not await connection.fetchval("SELECT pg_try_advisory_lock($1)", WORKFLOW_PUBLICATION_LOCK):
            if time.monotonic() >= deadline or reader.at_eof():
                raise RuntimeError("工作流发布锁等待超时或宿主已退出")
            await asyncio.sleep(.2)
        # No lazy repository pool is used: that pool performs schema DDL. This
        # transaction can only SELECT published snapshots and validate schemas.
        async with connection.transaction(readonly=True):
            rows = await connection.fetch("""SELECT w.id,w.published_revision,v.definition
                FROM biz_module_workflow w LEFT JOIN biz_module_workflow_version v
                ON v.workflow_id=w.id AND v.revision=w.published_revision
                WHERE w.published_revision IS NOT NULL ORDER BY w.id""")
            report = validate_snapshots(service, rows)
        emit("READY", report=report)
        if not report["passed"]:
            return
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            line = await asyncio.wait_for(reader.readline(), timeout=15)
            if not line:
                break
            message = json.loads(line)
            operation = message.get("operation")
            if operation == "PING":
                await connection.fetchval("SELECT 1")
                emit("PONG")
            elif operation == "RELEASE":
                break
            elif operation == "FENCE":
                import re
                revision = message.get("revision", "")
                if not re.fullmatch(r"[a-f0-9]{40}", revision):
                    raise RuntimeError("发布版本围栏需要完整 SHA")
                # Platform control metadata only; no business rows are changed.
                await connection.execute("""INSERT INTO biz_module_runtime_revision(id,active_revision)
                    VALUES(1,$1) ON CONFLICT(id) DO UPDATE
                    SET active_revision=EXCLUDED.active_revision,updated_at=now()""", revision)
                emit("FENCED", revision=revision)
            else:
                raise RuntimeError("未知工作流发布锁操作")
    except Exception as exc:  # noqa: BLE001 - Keep credentials out of host diagnostics.
        emit("ERROR", error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
    finally:
        if connection is not None:
            await connection.close(timeout=5)
        emit("RELEASED")


class WorkflowPublicationGuard:
    def __init__(self, executor, container_id):
        if len(container_id) != 64 or any(character not in "abcdef0123456789" for character in container_id):
            raise ValueError("工作流锁必须绑定已核对的容器 ID")
        self.ex = executor
        self.container_id = container_id
        self.process = None
        self.messages = queue.Queue()
        self.write_lock = threading.Lock()
        self.stopping = threading.Event()
        self.failed = ""
        self.last_seen = time.monotonic()
        self.pump = None
        self.report = None
        self.reader = None

    def send(self, operation, **values):
        with self.write_lock:
            self.process.stdin.write(json.dumps({"operation": operation, **values}) + "\n")
            self.process.stdin.flush()

    def read(self):
        for line in self.process.stdout:
            if line.startswith(PREFIX):
                try:
                    message = json.loads(line[len(PREFIX):])
                except ValueError:
                    self.failed = "工作流锁返回无效协议"
                    return
                self.last_seen = time.monotonic()
                if message.get("type") != "PONG":
                    self.messages.put(message)
        self.messages.put({"type": "ERROR", "error": "工作流发布锁辅助进程提前退出"})

    def maintain(self):
        while not self.stopping.wait(2):
            if self.ex.lost.is_set() or self.process.poll() is not None or time.monotonic() - self.last_seen > 12:
                self.failed = "工作流发布锁会话中断或执行租约失效"
                try:
                    self.process.stdin.close()
                except OSError:
                    pass
                return
            try:
                self.send("PING")
            except (OSError, ValueError):
                self.failed = "工作流发布锁心跳发送失败"
                return

    def receive(self, kind, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ex.lost.is_set() or self.failed:
                raise RuntimeError(self.failed or "执行租约失效")
            try:
                message = self.messages.get(timeout=.2)
            except queue.Empty:
                continue
            if message.get("type") == kind:
                return message
            if message.get("type") in {"ERROR", "RELEASED"}:
                raise RuntimeError(message.get("error", "工作流发布锁已释放"))
        raise RuntimeError("工作流发布锁通信超时")

    def acquire(self):
        # Trusted source, not uploaded command text. Docker exec inherits only
        # this verified target container's DSN; no secret enters the CLI.
        source = Path(__file__).read_text(encoding="utf-8")
        command = source + "\nimport asyncio\nasyncio.run(container_main())\n"
        self.process = subprocess.Popen(["docker", "exec", "-i", self.container_id, "python", "-u", "-c", command],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        try:
            message = self.receive("READY", 85)
            report = message["report"]
            self.report = report
            if not report.get("passed"):
                failures = [item for item in report["workflows"] if not item["passed"]]
                raise RuntimeError("已发布工作流与候选版本不兼容：" + json.dumps(failures, ensure_ascii=False))
            self.pump = threading.Thread(target=self.maintain, daemon=True)
            self.pump.start()
            return report
        except BaseException:
            self.close()
            raise

    def assert_alive(self):
        if self.failed or self.ex.lost.is_set() or self.process.poll() is not None:
            raise RuntimeError(self.failed or "工作流发布锁已失效")

    def fence(self, revision):
        self.assert_alive()
        self.send("FENCE", revision=revision)
        if self.receive("FENCED", 12).get("revision") != revision:
            raise RuntimeError("工作流发布版本围栏写入不一致")

    def close(self):
        self.stopping.set()
        if self.pump:
            self.pump.join(timeout=3)
        if self.process is None:
            return
        try:
            if self.process.poll() is None and not self.process.stdin.closed:
                self.send("RELEASE")
                self.process.stdin.close()
            self.process.wait(timeout=18)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
        finally:
            if self.reader:
                self.reader.join(timeout=2)
            self.process.stdout.close()
