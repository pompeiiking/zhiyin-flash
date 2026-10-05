"""Exercise the real public conversation API with the authorized module tool."""
import json
from pathlib import Path
from uuid import uuid4

from module_executor import request, read_env

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8014"


def main():
    env = read_env(ROOT / ".platform/workbench.env")
    auth = request(BASE, "/api/v1/app/auth/login", body={"account": "admin", "password": env["PLATFORM_ACCOUNT_PASSWORD"]})
    user = request(BASE, "/api/v1/app/auth/login", body={"account": "module_developer", "password": env["PLATFORM_ACCOUNT_PASSWORD"]})
    def api(path, body=None, method=None):
        return request(BASE, "/api/v1" + path, token=(auth if path.startswith('/developer') else user)["token"], body=body, method=method, timeout=180)
    module = next(m for m in api("/developer/modules") if m["manifest"]["id"] == "action_progress")
    policy = module["policy"]
    agents = [a["id"] for a in api("/developer/context")["agents"]]
    granted = api("/developer/modules/action_progress/policy", {**policy, "agents": agents}, "PUT")
    try:
        session = api("/app/task/enter", {"task_code": "how_to_act"})
        task_id = session["task_id"]
        before = api("/app/modules/action_progress/data")
        message = {"task_id": task_id,
            "message": "请调用行动计划进度工具读取我已经保存的计划，并展示进度卡，告诉我已完成多少项、总共多少项。不要新建或修改计划。",
            "client_msg_id": "module_accept_" + uuid4().hex}
        reply = api("/app/conversation/message", message)
        expected = api("/app/modules/action_progress/data")
        cards = [r for message in reply.get("messages", []) for r in message.get("renderables", []) if r["kind"] == "module.action_progress"]
        evidence = {"task_id": task_id, "reply": reply, "expected": expected,
                    "module_card_matches_database": bool(cards) and cards[0]["payload"] == expected}
        path = ROOT / ".platform/acceptance/conversation.json"
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        assert evidence["module_card_matches_database"], "Conversation did not return the expected module card; inspect evidence"
        assert before == expected and not reply["changed_assets"], "Read-only module query replaced business data"
        turns = api(f"/app/sessions/{task_id}/turns")
        assert any("module.action_progress" in json.dumps(t) for t in turns), "Conversation card was not persisted"
        replay = api("/app/conversation/message", message)
        assert replay["messages"][0]["renderables"] == reply["messages"][0]["renderables"]
        print("PASS real conversation API, module card, source data and persisted turn")
    finally:
        api("/developer/modules/action_progress/policy", {**policy, "revision": granted["revision"]}, "PUT")


if __name__ == "__main__":
    main()
