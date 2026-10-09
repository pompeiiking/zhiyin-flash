"""Verify a committed platform baseline before the first blue-green handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from module_executor import Executor


class BaselineVerifier(Executor):
    def update(self, **values):
        return values

    def log(self, stage, message):
        print(f"[{stage}] {self.redact(str(message))[-2000:]}", flush=True)

    def verify(self, revision, output):
        self.job = {"id": uuid4().hex, "lease": uuid4().hex}
        report = {"revision": revision, "passed": False, "scope": "committed platform baseline"}
        try:
            checkout = self.checkout(revision)
            self.gates(checkout)
            self.log("building", self.compose(checkout, revision, "build", "api", "web"))
            report["dataflow"] = self.acceptance(checkout, revision)
            report["passed"] = True
        finally:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PASS committed platform baseline " + revision, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    BaselineVerifier(json.loads(args.config.read_text(encoding="utf-8"))).verify(args.revision, args.output)
