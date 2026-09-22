"""学信网在线验证报告核验客户端。

只做三件事：把码发出去、把页面读回来、把字段抠出来。
不做判断（"要不要写进画像"是业务层的事），不存原文。

页面结构说明
------------
学信网的验证页（`/xlcx/bg.do?vcode=…&srcid=bgcx`）是服务端渲染的：

- 码无效 / 报告过期 → 正文里是 `<div class="result-error">` + 一句中文说明；
- 码有效 → 正文里是报告本体，位置在 `class="m_cnt_m"` 与页脚
  `<div class="flex-base">` 之间。

**字段解析按标签取值，不按 DOM 结构取值。**
理由很实际：报告是"标签 + 值"的排版（姓名 / 性别 / 院校名称 / …），
而站点随时可能调整标签容器。锚在标签上，改版最多影响某一条；
锚在 `div:nth-child(3) > span` 这种结构上，一次改版就全废。
"""

from __future__ import annotations

import asyncio
import html as html_module
import re
from datetime import datetime, timezone

import httpx

from zhiyin_data_sdk.gateways.chsi import (
    ChsiField,
    ChsiReportKind,
    ChsiVerifyError,
    ChsiVerifyErrorKind,
)

DEFAULT_BASE_URL = "https://www.chsi.com.cn"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

"""在线验证码的合法形状（口径取自学信网验证页自带的校验规则）：
12 位纯数字，或 A / X 开头 + 15 位大写字母数字。"""
_CODE_PATTERNS = (re.compile(r"^\d{12}$"), re.compile(r"^[AX][A-Z0-9]{15}$"))

_SCRIPT_OR_STYLE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_TAG = re.compile(r"(?s)<[^>]+>")
_WS = re.compile(r"[ \t\u00a0\u3000]+")
_BLANK_LINES = re.compile(r"\n{2,}")

"""
标签 → 规范键。

顺序有意义：先长后短，避免"专业"把"专业名称"吃掉。
键名用英文小写下划线，直接就是画像字段键（业务层不再翻译一次）。
"""
_LABELS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("院校名称", "学校名称", "院校", "学校"), "school"),
    (("院系名称", "院系", "系别"), "department"),
    (("专业名称", "专业"), "major"),
    (("学历层次", "培养层次", "层次"), "degree_level"),
    (("学习形式", "办学形式"), "study_mode"),
    (("学籍状态", "学籍情況", "学籍情况"), "enrollment_status"),
    (("预计毕业日期", "预计毕业时间"), "expected_graduation"),
    (("入学日期", "入学时间"), "enrolled_at"),
    (("毕业日期", "毕业时间"), "graduated_at"),
    (("出生日期", "出生年月"), "birth_date"),
    (("身份证号", "证件号码"), "id_card"),
    (("学号",), "student_no"),
    (("学制",), "duration"),
    (("姓名",), "student_name"),
    (("性别",), "gender"),
    (("民族",), "ethnicity"),
    (("在线验证码", "验证码"), "chsi_code"),
    (("报告编号",), "chsi_report_no"),
    # 这两条本身也是有用的信息（报告什么时候核验的、能用到什么时候），
    # 同时它们还是"报告编号"这类值的天然右边界 —— 少一个就会把下一行吞进上一条。
    (("验证日期", "打印时间", "打印日期"), "verified_date"),
    (("有效期至", "有效期"), "valid_until"),
)

_KIND_HINTS: tuple[tuple[str, ChsiReportKind], ...] = (
    ("学籍在线验证报告", ChsiReportKind.ENROLLMENT),
    ("学历证书电子注册备案表", ChsiReportKind.EDUCATION),
    ("学位在线验证报告", ChsiReportKind.DEGREE),
)


class ChsiReportClient:
    """在线验证报告的取数与解析。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 20.0,
        request_interval_s: float = 0.5,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._request_interval_s = request_interval_s
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    @property
    def base_url(self) -> str:
        return self._base_url

    async def fetch_report_html(self, code: str) -> tuple[str, str]:
        """取验证页 HTML。返回 (html, 可回溯的核验入口)。

        注意返回的**不是**带 `vcode` 的那条地址：在线验证码等于这份报告的一把钥匙，
        谁拿到谁就能读到报告内容。那条链接我们只用一次，不进日志、不落库、不入画像
        （它会跟着 evidence 一起长期留存）。留作来源的是官方验证入口 ——
        拿着码去那里查，跟当时我们做的事完全一样。
        """
        url = f"{self._base_url}/xlcx/bg.do"
        params = {"vcode": code, "srcid": "bgcx"}
        await self._throttle()
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, follow_redirects=True, headers=_HEADERS
            ) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.text, f"{self._base_url}/xlcx/bgcx.jsp"
        except httpx.HTTPError as exc:
            raise ChsiVerifyError(
                "连不上学信网的核验服务，请稍后再试。",
                kind=ChsiVerifyErrorKind.UNREACHABLE,
                detail=str(exc),
            ) from exc

    async def _throttle(self) -> None:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            wait = self._request_interval_s - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = asyncio.get_running_loop().time()


# ---------------------------------------------------------------- 纯函数部分


def normalize_code(raw: str) -> str:
    """去掉用户粘贴时带进来的空格、连字符，统一大写。"""
    return re.sub(r"[\s\-_]", "", (raw or "")).upper()


def is_well_formed(code: str) -> bool:
    return any(pattern.match(code) for pattern in _CODE_PATTERNS)


def extract_report_block(page_html: str) -> str:
    """截出报告正文所在的那一段，去掉导航与页脚 —— 那里的"学籍查询"之类会干扰取值。"""
    start = page_html.find('class="m_cnt_m"')
    if start < 0:
        return page_html
    end = page_html.find('class="flex-base"', start)
    return page_html[start : end if end > 0 else len(page_html)]


def html_to_text(fragment: str) -> str:
    """HTML → 规整文本：块级标签补空格，实体解码，行尾留 \\n 便于分段。"""
    text = _SCRIPT_OR_STYLE.sub(" ", fragment)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|table)>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " ", text)
    text = _TAG.sub("", text)
    text = html_module.unescape(text)
    text = text.replace("\r", "")
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n", text).strip()


def detect_kind(text: str) -> ChsiReportKind:
    for hint, kind in _KIND_HINTS:
        if hint in text:
            return kind
    return ChsiReportKind.UNKNOWN


def detect_error(page_html: str) -> str:
    """页面是不是错误页？是就返回给用户看的那句话。"""
    marker = page_html.find('class="result-error"')
    if marker < 0:
        return ""
    # 从标记往回退到所在标签的开头，否则切出来的碎片里会留下 `class="result-error">`
    # 这种半截标签 —— 它不是标签（前面没有 `<`），清理规则不会管它。
    start = page_html.rfind("<", 0, marker)
    text = html_to_text(page_html[start if start >= 0 else marker : marker + 2000])
    # 错误块里的第一行有意义的文字就是结论（"此在线验证码无效。"之类）
    for line in text.split("\n"):
        line = line.strip()
        if line and "重新查询" not in line:
            return line
    return "此在线验证码无效。"


def classify_error(message: str) -> ChsiVerifyErrorKind:
    """把学信网的说法归类。过期和无效的处理方式不同：一个让用户重申请，一个让用户对一下码。"""
    if any(word in message for word in ("过期", "失效", "有效期", "已到期")):
        return ChsiVerifyErrorKind.EXPIRED
    return ChsiVerifyErrorKind.INVALID_CODE


def parse_fields(text: str) -> list[ChsiField]:
    """按标签取值。

    做法：在文本里找出所有"标签（可选冒号）"的位置，
    两个相邻标签之间的内容就是前一个标签的值。
    这样无论站点把标签放在 `<td>`、`<div>` 还是 `<span>` 里都能取到。
    """
    # 保留换行（它是"一条结束"的信号），其余空白压成单空格
    flat = re.sub(r"[^\S\n]+", " ", text)
    hits: list[tuple[int, int, str, str]] = []  # (start, end, key, label)

    for aliases, key in _LABELS:
        for alias in aliases:
            for match in re.finditer(re.escape(alias) + r"\s*[:：]?", flat):
                hits.append((match.start(), match.end(), key, alias))

    hits.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    # 同一位置重叠的标签只留最长的那个（"专业名称" 优先于 "专业"）
    fields: list[ChsiField] = []
    seen: set[str] = set()
    cursor = -1
    for index, (start, end, key, label) in enumerate(hits):
        if start < cursor or key in seen:
            continue

        # 右边界取三者最近的一个：下一个标签、本行行尾、文本结尾。
        # 行尾只在"这一行剩下点东西"时才算边界 ——
        # 有的版式把标签和值放在相邻的块里（换了行），那时值要跨过换行去取。
        limit = len(flat)
        for later_start, _, _, _ in hits[index + 1 :]:
            if later_start >= end:
                limit = later_start
                break
        line_end = flat.find("\n", end)
        if 0 <= line_end < limit and flat[end:line_end].strip(" :：|"):
            limit = line_end

        value = flat[end:limit].strip(" :：|\u00a0")
        value = re.sub(r"\s+", " ", value).strip()
        # 值不可能是整段文字：超过 60 字多半是把后面的正文一起吞进来了
        if not value or len(value) > 60:
            cursor = end
            continue
        seen.add(key)
        fields.append(ChsiField(key=key, label=label, value=value))
        cursor = end

    return fields


def parse_report(page_html: str, *, code: str) -> tuple[ChsiReportKind, list[ChsiField], str]:
    """页面 → (报告类型, 字段, 正文摘录)。错误页由调用方先拦掉。"""
    block = extract_report_block(page_html)
    text = html_to_text(block)
    return detect_kind(text), parse_fields(text), text[:2000]


def verified_at_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "DEFAULT_BASE_URL",
    "ChsiReportClient",
    "classify_error",
    "detect_error",
    "detect_kind",
    "extract_report_block",
    "html_to_text",
    "is_well_formed",
    "normalize_code",
    "parse_fields",
    "parse_report",
    "verified_at_now",
]
