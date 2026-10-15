#!/usr/bin/env python3
"""Recheck the frozen formal matrix after fixing late-reap deadline enforcement."""
import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from v150_budget import load_budget,within_budget

root=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser()
p.add_argument("--evidence",type=Path,default=root/"verification/v1.5.0-formal-performance")
p.add_argument("--output",type=Path)
a=p.parse_args()
def read(name):return json.loads((a.evidence/name).read_text())
def sha(data):return hashlib.sha256(data).hexdigest()
budget_hash="49f2ce1d984122ec7aa81c66b234e3b6c62abcd68a2dbffe799666519b4e043f"
fixture_hash="8e310e4d01a75deb988ce309ebef348bb693f1123c19f3c700d662c2fde4f9e8"
assert sha((a.evidence/"budget.json").read_bytes())==budget_hash
assert sha((a.evidence/"semantic-fixtures.json").read_bytes())==fixture_hash
for entry in read("export.json")["files"]:
    raw=(a.evidence/entry["path"]).read_bytes()
    assert sha(raw)==entry["published_sha256"] and len(raw)==entry["bytes"]
identity=read("identity.json")
manifest=read("semantic-fixtures.json")
budget=load_budget(read("budget.json"),compiler_sha256=identity["compiler_sha256"],
                   fixture_sha256=fixture_hash,manifest=manifest,
                   seed_sha256=identity["seed_receipt"]["sha256"])
assert budget["source_inventory_sha256"]==identity["inventory_sha256"]
result=read("formal.json")
assert result["stage"]=="formal" and result["passed"] and result["full_profile_selected"]
assert result["budget_sha256"]==budget_hash and result["fixture_manifest_sha256"]==fixture_hash
assert result["compiler_sha256"]==identity["compiler_sha256"]
assert result["profile"]["cell_limits"]==budget["cells"]
assert [c["name"] for c in result["cells"]]==[c["name"] for c in manifest["cells"]]
payloads=read("formal-streams.json")["streams"]
streams={entry["path"]:entry for entry in payloads}
assert len(payloads)==len(streams)==944
rows=[];seen=set()
for cell,fixture in zip(result["cells"],manifest["cells"]):
    limits=budget["cells"][cell["name"]]
    runs=cell["runs"]
    assert cell["completed"] and cell["budget_passed"]
    assert [r["kind"] for r in runs]==["warmup","run-1","run-2","run-3"]
    assert within_budget(runs,limits),cell["name"]
    for run in runs:
        seconds=run["seconds"]
        assert type(seconds) in (int,float) and math.isfinite(seconds)
        assert 0<=seconds<=limits["wall_cutoff_seconds"],(cell["name"],run["kind"])
        assert run["exit"]==fixture["expected_exit"] and run["signal"] is None
        assert run["input_unchanged"] and run["input_failure"] is None
        assert run["peak_rss_bytes"]==run["peak_rss_raw"]*1024
        values={}
        assert set(run["streams"])=={"stdout","stderr"}
        for name,meta in run["streams"].items():
            path=cell["name"]+"/"+run["kind"]+"/"+name
            entry=streams[path];raw=bytes.fromhex(entry["hex"]);seen.add(path)
            assert sha(raw)==entry["sha256"]==meta["sha256"]
            assert len(raw)==entry["bytes"]==meta["bytes"]
            values[name]=raw
        assert values["stdout"]==b""
        if fixture["expected_exit"]==0:assert values["stderr"]==b""
        else:assert ("mgnc: "+fixture["phase"]+":").encode() in values["stderr"]
        detail=fixture.get("detail") or {}
        if detail.get("primary_start") is not None:
            assert ("[%s,%s)"%(detail["primary_start"],detail["primary_end"])).encode() in values["stderr"]
    assert cell["wall_median_seconds"]==statistics.median(r["seconds"] for r in runs[1:])
    assert cell["rss_max_bytes"]==max(r["peak_rss_bytes"] for r in runs[1:])
    rows.append(dict(name=cell["name"],runs=4,maximum_all_run_seconds=max(r["seconds"] for r in runs),
                     wall_cutoff_seconds=limits["wall_cutoff_seconds"],passed=True))
assert seen==set(streams) and len(rows)==118
audit=dict(original_measurement_revision=read("runner.json")["revision"],
           compiler_sha256=identity["compiler_sha256"],budget_sha256=budget_hash,
           fixture_manifest_sha256=fixture_hash,formal_record_sha256=sha((a.evidence/"formal.json").read_bytes()),
           cells=rows,runs=472,streams=944,deadline_violations=0,passed=True,
           new_performance_measurements=False)
if a.output:a.output.write_text(json.dumps(audit,indent=2)+"\n")
print("V150_FORMAL_RECHECK_OK cells=118 runs=472 streams=944 deadline_violations=0")
