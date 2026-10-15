"""导出 / 校验接口契约快照（`contracts/openapi.json`）。

用法：

    python scripts/export_openapi.py            # 按代码现状覆盖快照
    python scripts/export_openapi.py --check    # 只校验，不一致则退出 1（CI 用）

为什么要入库一份快照、怎么保证不漂移，见 `zhiyin_api/contract.py` 的模块 docstring。
一句话：**代码是唯一事实来源**，快照是它的导出物，前端类型由快照生成——
于是"后端改了字段、前端没跟上"在 CI 就会失败，不再靠人记得重新生成。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = TEMPLATE_ROOT / "contracts" / "openapi.json"

# 让脚本不装包也能跑（与 pyproject 的 [tool.pytest.ini_options].pythonpath 同一份口径）
SOURCE_DIRS = (
    "zhiyin-kernel",
    "zhiyin-api",
    "zhiyin-business",
    "zhiyin-orchestration",
    "zhiyin-data-sdk",
    "zhiyin-infrastructure",
    "zhiyin-boot",
)


def _ensure_importable() -> None:
    for name in SOURCE_DIRS:
        path = str(TEMPLATE_ROOT / name)
        if path not in sys.path:
            sys.path.append(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export_openapi", description="职引 · 接口契约快照")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只校验快照与代码是否一致（不一致时退出 1，且不写文件）",
    )
    parser.add_argument(
        "--out",
        default=str(CONTRACT_PATH),
        help="快照路径，默认 contracts/openapi.json",
    )
    args = parser.parse_args(argv)

    _ensure_importable()
    from zhiyin_api.contract import build_openapi_schema, contract_is_stale, write_contract

    target = Path(args.out)

    if args.check:
        if not target.is_file():
            print(f"缺少接口契约快照：{target}", file=sys.stderr)
            print("请运行：python scripts/export_openapi.py", file=sys.stderr)
            return 1
        stale = contract_is_stale(target)
        if stale:
            print("接口契约快照与代码不一致：", file=sys.stderr)
            for item in stale:
                print(f"  - {item}", file=sys.stderr)
            print("请运行：python scripts/export_openapi.py", file=sys.stderr)
            return 1
        print(f"接口契约快照与代码一致：{target}")
        return 0

    write_contract(target)
    schema = build_openapi_schema()
    print(f"已写入 {target}")
    print(f"  接口 {len(schema.get('paths', {}))} 条，DTO {len(schema.get('components', {}).get('schemas', {}))} 个")
    print("下一步：cd ../../redesign-demo && npm run gen:api")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
