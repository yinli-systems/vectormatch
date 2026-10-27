#!/usr/bin/env python3
"""Record actual test counts (including skips), not a synthetic GitHub status."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
suites = []
for path in sorted(root.glob("*/build/test-results/*/TEST-*.xml")):
    suite = ET.parse(path).getroot()
    suites.append(dict(path=path.relative_to(root).as_posix(),
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       name=suite.get("name"),
                       **{key: int(suite.get(key, "0")) for key in ("tests", "failures", "errors", "skipped")}))
logs = {p.relative_to(root).as_posix(): dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted((root / "runtime/ci").glob("*.log"))}
result = dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              sourceCommit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              runner="self-hosted-existing-prepaid-cpu", runId=os.getenv("GITHUB_RUN_ID"),
              suites=suites, totals={key: sum(s[key] for s in suites) for key in ("tests", "failures", "errors", "skipped")}, logs=logs,
              scope="Test report only. Actual GitHub step/job conclusions determine CI success; no performance or production certification.")
out = root / "runtime/ci"; out.mkdir(parents=True, exist_ok=True)
(out / "SUMMARY.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result["totals"]))
summary = os.getenv("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a") as stream:
        stream.write("Existing CPU correctness: `" + result["sourceCommit"] + "`\n\nJUnit counts: `" + json.dumps(result["totals"]) + "`. See actual steps for Python, PostgreSQL, failover and web results.\n")
