"""Preview/apply only the dialogue prompts; preserve all other registry rows.

Run --local against the local Docker database, or inside the deployed container.
An apply writes a dated rollback file before updating the selected rows.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit

TEMPLATE = Path(__file__).resolve().parents[1]
for package in TEMPLATE.glob("zhiyin-*"):
    if package.is_dir():
        sys.path.insert(0, str(package))


async def main(args):
    import asyncpg
    from zhiyin_boot import Settings
    settings = Settings.from_env()
    dsn = settings.postgres_dsn
    if args.local:
        parsed = urlsplit(dsn)
        if parsed.hostname not in {"postgres", "zhiyin-flash-postgres", "localhost", "127.0.0.1"}:
            raise RuntimeError("--local requires the local development database")
        credentials = parsed.netloc.rsplit("@", 1)[0] if "@" in parsed.netloc else ""
        dsn = urlunsplit(parsed._replace(netloc=(credentials + "@" if credentials else "") + "127.0.0.1:55432"))
    source = json.loads((TEMPLATE / "data/registry/prompts.json").read_text(encoding="utf-8"))
    wanted = {p["code"]: p for p in source["items"] if p["code"].startswith("conversation.")}
    connection = await asyncpg.connect(dsn, timeout=10)
    try:
        async with connection.transaction():
            rows = await connection.fetch("SELECT code, content, params FROM ai_prompt_template WHERE code = ANY($1::text[]) FOR UPDATE", list(wanted))
            if len(rows) != len(wanted):
                raise RuntimeError("Start the new application first to seed missing dialogue prompts")
            changed = [r for r in rows if r["content"] != wanted[r["code"]]["content"]
                       or json.loads(r["params"]) != wanted[r["code"]].get("params", {})]
            print(json.dumps({"apply": args.apply, "changed": [r["code"] for r in changed]}))
            if changed and args.apply:
                folder = TEMPLATE / "output"
                folder.mkdir(exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup = folder / f"dialogue-prompts-{stamp}.json"
                backup.write_text(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2), encoding="utf-8")
                for row in changed:
                    prompt = wanted[row["code"]]
                    await connection.execute("UPDATE ai_prompt_template SET content=$2, params=$3::jsonb, updated_at=NOW() WHERE code=$1",
                        row["code"], prompt["content"], json.dumps(prompt.get("params", {})))
                print(json.dumps({"rollback_file": str(backup)}))
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
