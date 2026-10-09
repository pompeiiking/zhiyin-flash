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


def validate(result: dict) -> dict:
    value = ModuleResult.model_validate(result)
    data = Progress.model_validate(value.data)
    if data.total != len(data.tasks) or data.completed != sum(t.done for t in data.tasks):
        raise ValueError("进度必须与已有任务状态一致")
    value.data = data.model_dump()
    return value.model_dump()


async def load(context: ModuleContext) -> dict:
    plan = await context.read("plan.read")
    tasks = [{"task_id": t["task_id"], "text": t["text"], "phase": p["name"], "done": t["done"]}
             for p in plan.get("phases", []) for t in p.get("tasks", [])]
    return validate({"data": {"has_plan": plan.get("has_plan", False), "tasks": tasks,
                             "total": len(tasks), "completed": sum(t["done"] for t in tasks)},
                     "sources": ["职引已保存的行动计划"], "empty": not tasks})
