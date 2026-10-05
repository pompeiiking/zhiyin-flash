from zhiyin_kernel.modules import ModuleContext, ModuleResult


def validate(result: dict) -> dict:
    value = ModuleResult.model_validate(result)
    data = value.data
    if not isinstance(data.get("items"), list) or not isinstance(data.get("unlocked"), int):
        raise ValueError("完成记录数据格式错误")
    if data["unlocked"] != sum(bool(x.get("unlocked")) for x in data["items"]):
        raise ValueError("完成记录数量不一致")
    return value.model_dump()


async def load(context: ModuleContext) -> dict:
    data = await context.read("achievements.read")
    return validate({"data": data, "sources": ["职引行为日志与成就规则"], "empty": not data.get("items")})
