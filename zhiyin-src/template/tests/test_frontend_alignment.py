"""Contract guards for the selected sidebar frontend; transport behavior uses Node tests."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "zhiyin-src/template"
WEB = ROOT / "zhiyin-src/template/zhiyin-web"


def test_inventory_covers_every_controller():
    expected = set()
    for p in (TEMPLATE / "zhiyin-api/zhiyin_api/controllers").glob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                if (
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr in ("get", "post", "put", "patch", "delete")
                    and d.args
                    and isinstance(d.args[0], ast.Constant)
                ):
                    expected.add(d.func.attr.upper() + " /api/v1" + d.args[0].value)
    rows = json.loads(
        (ROOT / "docs/前端/后端接入/后端接口与模型.json").read_text(encoding="utf-8")
    )["endpoints"]
    assert expected == {r["id"] for r in rows}
    for r in rows:
        if r["scope"] == "服务间调用":
            assert "/source-worker/" in r["path"] or "/executor/" in r["path"]
        else:
            assert r["frontend"], r["id"]
            assert all((ROOT / f).is_file() for f in r["frontend"]), r["id"]


def test_student_operations_match_backend():
    spec = json.loads((TEMPLATE / "contracts/openapi.json").read_text(encoding="utf-8"))["paths"]
    ops = json.loads((WEB / "src/api/operations.json").read_text())
    for key, op in ops.items():
        assert op["method"].lower() in spec["/api/v1" + op["path"]], key
    student = {
        (m.upper(), p)
        for p, ms in spec.items()
        if p.startswith("/api/v1/app/") and "/config/" not in p
        for m in ms
        if m in ("get", "post", "patch", "put", "delete")
    }
    assert student == {(o["method"], "/api/v1" + o["path"]) for o in ops.values()}


def test_no_fake_service_or_query_auth():
    client = (WEB / "src/api/backend-client.ts").read_text(encoding="utf-8")
    router = (WEB / "src/router.ts").read_text(encoding="utf-8")
    assert (
        "demo-service" not in client and "auth.restore()" in router and "to.query.as" not in router
    )
    assert not (WEB / "src/lib/demo-service.ts").exists()
    assert not (WEB / "src/data/demo-fixtures.ts").exists()


def test_single_frontend_preserves_classic_portal_and_brands():
    assert (TEMPLATE / "zhiyin-web/src").is_dir()
    assert not (ROOT / "redesign-demo").exists()
    assert not (ROOT / "frontend").exists()
    assert "dockerfile: zhiyin-src/template/zhiyin-web/Dockerfile" in (ROOT / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    theme = (WEB / "src/lib/theme.ts").read_text(encoding="utf-8")
    assert "'blue'" in theme and "'red'" in theme and "dataset.accent" in theme
    classic = (WEB / "src/views/PortalClassicView.vue").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in classic and "animateMotion" in classic


def test_chat_preserves_retry_identity_and_real_task_ids():
    chat = (WEB / "src/views/ConversationView.vue").read_text(encoding="utf-8")
    chat = "".join(chat.split())
    for code in [
        "client_msg_id:crypto.randomUUID()",
        # 重试必须复用失败时那条请求的 client_msg_id（身份不变），而不是新建一条
        "retried=retry?(failedRequest??failedSend.value?.request??null):null",
        "demo.state.currentSessionId!==sessionId",
        "watch(()=>demo.state.currentSessionId,",
        "selectedOption.value=null;failedRequest=null;pending.value=null",
        "controller?.abort()",
        "toggleTask(turn.guideTask.task_id)",
        "backendClient.actionDone({task_id:id",
    ]:
        assert code in chat


def test_accessibility_primitives_present():
    css = "".join(p.read_text(encoding="utf-8") for p in (WEB / "src/styles").glob("*.css"))
    assert "prefers-reduced-motion" in css and "focus-visible" in css and "dvh" in css
    popover = (WEB / "src/components/DetailPopover.vue").read_text(encoding="utf-8")
    assert (
        "aria-expanded" in popover and "aria-controls" in popover and "escape-key-down" in popover
    )
