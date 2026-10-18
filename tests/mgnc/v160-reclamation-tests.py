#!/usr/bin/env python3
"""Reject corrupted evidence and violated reclamation criteria."""
import argparse
import copy
import json
from pathlib import Path
from v160_reclamation import validate, verify_raw

p = argparse.ArgumentParser()
p.add_argument("--budget", type=Path, required=True)
p.add_argument("--observations", type=Path, required=True)
a = p.parse_args()
budget = json.loads(a.budget.read_text())
report = json.loads((a.observations / "results.json").read_text())
verify_raw(a.observations, report)
validate(budget, report)


def row(data, program, count, mode=None):
    args = [str(count)] + ([mode] if mode else [])
    return next(r for r in data["records"] if r["program"] == program and r["arguments"] == args)


def bounded(data):
    return row(data, "lifetime-bounded", 10000)


def retained(data):
    return row(data, "lifetime-retained", 1000000)


def rejected(name, action, check):
    data = copy.deepcopy(report)
    action(data)
    try:
        check(data)
    except ValueError:
        print("PASS reject " + name)
    else:
        raise AssertionError("accepted " + name)


mutations = {
    "incomplete": lambda d: d.update(complete=False),
    "identity": lambda d: d.update(compiler_sha256="0" * 64),
    "missing-cell": lambda d: d["records"].pop(),
    "duplicate-cell": lambda d: d["records"].__setitem__(1, copy.deepcopy(d["records"][0])),
    "failed-run": lambda d: bounded(d).update(exit=1),
    "missing-build": lambda d: d["builds"].pop(),
    "resource-leak": lambda d: bounded(d)["heap"].update(resources=1),
    "fd-leak": lambda d: bounded(d)["high"].update(fds=4),
    "io-fd-leak": lambda d: row(d, "io-resource", 100, "success")["high"].update(fds=5),
    "bounded-mapped": lambda d: bounded(d)["high"].update(mapped=2097153),
    "bounded-live": lambda d: bounded(d)["high"].update(live=4097),
    "bounded-accumulation": lambda d: bounded(d)["high"].update(mapped=1),
    "retained-envelope": lambda d: retained(d)["high"].update(mapped=256 * 1000000 + 2097153),
    "retained-growth": lambda d: retained(d)["high"].update(live=row(d, "lifetime-retained", 100000)["high"]["live"]),
    "retained-zero": lambda d: retained(d)["high"].update(live=0),
    "invalid-number": lambda d: bounded(d)["high"].update(mapped=True),
    "missing-runtime": lambda d: bounded(d)["high"].update(fds=0),
}
for name, edit in mutations.items():
    rejected(name, edit, lambda d: validate(budget, d))

raw_mutations = {
    "raw-hash": lambda d: bounded(d).update(observation_sha256="0" * 64),
    "raw-path": lambda d: bounded(d).update(observation="../results.json"),
    "raw-summary": lambda d: bounded(d)["high"].update(mapped=1),
    "artifact": lambda d: d["builds"][0].update(artifact_sha256="0" * 64),
}
for name, edit in raw_mutations.items():
    rejected(name, edit, lambda d: verify_raw(a.observations, d))
print("V160_RECLAMATION_VALIDATOR_OK rejected=" + str(len(mutations) + len(raw_mutations)))
