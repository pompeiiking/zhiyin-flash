"""Merge independent edits while rejecting conflicting fields inside the write lock."""

from zhiyin_kernel.errors import DuplicateResource


def merge_form(current, expected, desired):
    if current == desired:
        return desired
    if expected is None:
        if current is not None:
            raise DuplicateResource("设置已在其他页面创建，请重新读取后核对；当前输入未保存。")
        return desired
    if current is None:
        raise DuplicateResource("原记录已发生变化，请重新读取后核对；当前输入未保存。")
    merged = dict(current)
    for key, value in desired.items():
        if value == expected.get(key):
            continue
        if current.get(key) != expected.get(key) and current.get(key) != value:
            raise DuplicateResource("同一项内容已在其他页面修改。你的输入仍保留，请核对最新记录后再保存。")
        merged[key] = value
    return merged
