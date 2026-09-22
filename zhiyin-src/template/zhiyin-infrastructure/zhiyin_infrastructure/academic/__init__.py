"""课表与成绩单的导入解析（学生自己带数据进来）。

入口两个：
- `ManualAcademicImporter`：实现 data_sdk 的导入契约（形态分流 + 报错分流）；
- `parsers`：纯函数，按名字读页面 / 表格 / JSON（可单测，不联网）。

这里**没有**登录、没有 outbound 请求、没有凭据 —— 这条路是产品有意选的：
用户的校内账号密码不该经我们的手。
"""

from zhiyin_infrastructure.academic.importer import ManualAcademicImporter

__all__ = [
    "ManualAcademicImporter",
]
