"""Strict module input/output contract checks and local JSON pointer bindings."""
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from zhiyin_kernel.errors import InvalidRequest


def validate_contract(schema: dict, value: Any, label: str):
    try:
        errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
                        key=lambda error: str(list(error.absolute_path)))
    except Exception as exc:
        raise InvalidRequest(f"{label} Schema 无法解析：{exc}") from exc
    if errors:
        details = [f"{label}/{ '/'.join(str(part) for part in error.absolute_path)}: {error.message}" for error in errors[:10]]
        raise InvalidRequest("；".join(details))


def resolve_binding(reference: str, inputs: dict, outputs: dict):
    source, separator, pointer = reference.partition("/")
    if source == "$input":
        value = inputs
    elif source in outputs:
        value = outputs[source]
    else:
        raise InvalidRequest(f"绑定来源不存在：{reference}")
    if separator:
        for raw in pointer.split("/"):
            key = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
                value = value[int(key)]
            else:
                raise InvalidRequest(f"绑定字段不存在：{reference}")
    return value


def schema_at_path(schema: dict, path: list[str], label: str):
    """Resolve provable object/array paths; open schemas remain runtime checks."""
    root, current = schema, schema
    for token in [*path, None]:
        seen = set()
        while isinstance(current, dict) and "$ref" in current:
            reference = current["$ref"]
            if reference in seen or not reference.startswith("#/"):
                return None
            seen.add(reference)
            current = root
            for key in reference[2:].split("/"):
                key = key.replace("~1", "/").replace("~0", "~")
                if not isinstance(current, dict) or key not in current:
                    raise InvalidRequest(f"{label} 的 Schema 引用不存在")
                current = current[key]
        if token is None:
            if not isinstance(current, dict):
                return None
            return {**current, "$defs": root.get("$defs", {})}
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or any(key in current for key in ("anyOf", "oneOf", "allOf")):
            return None
        if current.get("type") == "array":
            if not token.isdigit():
                raise InvalidRequest(f"{label} 的数组绑定必须使用数字下标")
            prefix = current.get("prefixItems", [])
            current = prefix[int(token)] if int(token) < len(prefix) else current.get("items", {})
        elif current.get("type") == "object" or "properties" in current:
            properties = current.get("properties", {})
            if token in properties:
                current = properties[token]
            elif current.get("additionalProperties") is False:
                raise InvalidRequest(f"{label} 引用了 Schema 中不存在的字段：{token}")
            else:
                current = current.get("additionalProperties", {})
        elif "type" in current:
            raise InvalidRequest(f"{label} 不能从标量继续读取字段")
        else:
            return None
    return None


def validate_bindings(target: dict, inputs: dict, bindings: dict, source_schema):
    """Reject statically evident bad inputs before a workflow is published."""
    target = schema_at_path(target, [], "input") or {}
    missing = set(target.get("required", [])) - set(inputs) - set(bindings)
    if missing:
        raise InvalidRequest(f"节点缺少必填输入或绑定：{', '.join(sorted(missing))}")
    for field, value in inputs.items():
        if field in bindings:
            continue
        contract = schema_at_path(target, [field], f"input.{field}")
        if contract:
            validate_contract(contract, value, f"input.{field}")
    for field, reference in bindings.items():
        expected = schema_at_path(target, [field], f"input.{field}")
        actual = source_schema(reference)
        if not actual or not expected:
            continue
        expected_type, actual_type = expected.get("type"), actual.get("type")
        expected_types = {expected_type} if isinstance(expected_type, str) else set(expected_type or [])
        actual_types = {actual_type} if isinstance(actual_type, str) else set(actual_type or [])
        if "number" in expected_types:
            expected_types.add("integer")
        if actual_types and expected_types and not actual_types.issubset(expected_types):
            raise InvalidRequest(f"绑定 {reference} 与 input.{field} 类型不兼容")
    if not bindings:
        validate_contract(target, inputs, "input")
