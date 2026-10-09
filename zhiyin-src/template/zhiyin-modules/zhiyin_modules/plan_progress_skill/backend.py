"""Read-only skill using the same saved task states as the plan business service."""
from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.modules import ModuleContext, ModuleResult


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    text: str
    phase: str = ""
    done: bool


class Progress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    has_plan: bool
    tasks: list[Task] = Field(default_factory=list)
    total: int = Field(ge=0)
    completed: int = Field(ge=0)
    summary: str = ""


def validate(result: dict) -> dict:
    value = ModuleResult.model_validate(result)
    data = Progress.model_validate(value.data)
    if data.total != len(data.tasks) or data.completed != sum(task.done for task in data.tasks):
        raise ValueError("进度必须与已有任务状态一致")
    data.summary = (f"你的计划共有 {data.total} 项任务，目前已完成 {data.completed} 项。"
                    if data.has_plan else "你还没有已保存的行动计划。")
    value.data = data.model_dump()
    return value.model_dump()


async def load(context: ModuleContext) -> dict:
    plan = await context.read("plan.read")
    tasks = [{"task_id": task["task_id"], "text": task["text"], "phase": phase["name"], "done": task["done"]}
             for phase in plan.get("phases", []) for task in phase.get("tasks", [])]
    actual = {"expected_total": len(tasks), "expected_completed": sum(task["done"] for task in tasks)}
    for field, value in actual.items():
        if field in context.input and context.input[field] != value:
            raise ValueError(f"上游输入 {field} 与当前保存的计划不一致，请重新读取")
    return validate({"data": {"has_plan": plan.get("has_plan", False), "tasks": tasks,
                              "total": len(tasks), "completed": sum(task["done"] for task in tasks)},
                     "sources": ["职引已保存的行动计划"], "empty": not tasks})
