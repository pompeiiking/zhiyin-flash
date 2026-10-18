"""Shared input boundaries for conversation reads and writes."""
from __future__ import annotations

import re
from zhiyin_kernel.privacy import SENSITIVE as SENSITIVE
INJECTION = re.compile(
    r"忽略.{0,8}(?:规则|指令|限制)|跳过.{0,6}(?:确认|规则)"
    r"|覆盖.{0,6}(?:规则|设定)|(?:系统|开发者|管理员)(?:提示|指令|消息)"
)


def action_text(text: str) -> str:
    """Commands inside quotations/third-party speech are data, not authority."""
    text = re.sub(r'[「『“"\'].*?[」』”"\']', '【引用内容】', text, flags=re.S)
    clauses = re.split(r"[，,。；;\n]", text)
    return "，".join(clause for clause in clauses if not re.search(
        r"(?:同学|室友|朋友|别人|老师|辅导员|导师|家长|父母|领导|面试官|同事|网友|系统)"
        r".{0,12}(?:说|让我|叫我|转告|转述|建议|问)|(?:原话|写着|截图|聊天记录|邮件|公告|原文里)", clause
    ))


def forbids_profile_write(text: str) -> bool:
    for clause in re.split(r"[，,。；;\n]", text):
        if not re.search(r"不要|别|无需|不必|不想|不用|先不|暂不", clause):
            continue
        if re.search(r"(?:不要|别|无需|不必|不想|不用|先不|暂不).{0,30}(?:画像|经历|个人信息|资料|专业|学校|年级)", clause):
            return True
        if re.fullmatch(r"\s*(?:先|暂时)?(?:不要|别|不用|先不|暂不)(?:保存|记录|写入)[了。！!\s]*", clause):
            return True
    return False


def positive_year(text: str) -> str | None:
    if re.search(r"如果|假如|假设|要是", text) or forbids_profile_write(text):
        return None
    text = re.sub(r"(?:不是|不再是|并非|还没到|还不是)\s*大[一二三四]", "", text)
    for pattern in (
        r"(?:我现在|目前|现在|已经|今年|刚|开学)(?:是|读|上|升|在)?[^。；\n]{0,6}?(大[一二三四])",
        r"我(?:是|读|上)(大[一二三四])",
        r"(?:改|调|更新|换|设置|更正)(?:成|为|到)?[^。；\n]{0,6}?(大[一二三四])",
    ):
        hit = re.search(pattern, text)
        if hit:
            return hit.group(1)
    return None


def task_intent(text: str) -> bool | None:
    text = action_text(text) if not re.search(r"「|“", text) else text
    if re.search(r"如果|假如|假设|要是", text) and not re.search(r"已经|刚刚|确实", text):
        return None
    if re.search(r"(?:不要|别|不用|先不|暂不).{0,8}(?:标记|勾|完成|修改|改|恢复)", text):
        return None
    if re.search(r"恢复|撤销|取消完成|取消勾选|改回|点错|标错|没做完|还没做|未完成|没有完成", text):
        return False
    if re.search(r"(?:做完|完成|搞定|勾掉|划掉|写完|投完|弄完)(?:了|啦|了的)?[吗么？?]", text):
        return None
    if re.search(r"讨论|怎么完成|怎样完成|如何完成|是否|有没有完成", text):
        return None
    if re.search(r"做完|完成了|完成啦|已完成|搞定|勾掉|划掉|写完了|投完了|弄完了|已经做|已做|已经投|已投|标记.{0,8}完成", text):
        return True
    if re.search(r"完成$|完成[，,。！!]", text):
        return True
    return None
