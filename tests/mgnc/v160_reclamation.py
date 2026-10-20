"""Validate adopted checkpoint criteria independently of the lifetime observer."""
import hashlib
import json
from pathlib import Path


def validate(budget, report):
    if budget.get("schema") != 1 or budget.get("status") != "accepted":
        raise ValueError("unaccepted budget")
    if not report.get("complete"):
        raise ValueError("incomplete observations")
    for key in ("compiler_sha256", "fixture_manifest_sha256"):
        if report.get(key) != budget.get(key):
            raise ValueError("observation identity mismatch")
    criteria = budget["reclamation"]
    expected = {
        (program, (str(count),))
        for program in ("lifetime-bounded", "lifetime-retained")
        for count in criteria["bounded_counts"]
    } | {
        ("io-resource", (str(count), mode))
        for count in criteria["io_counts"] for mode in criteria["io_modes"]
    }
    rows = report["records"]
    keys = [(row["program"], tuple(row["arguments"])) for row in rows]
    if len(keys) != 15 or len(set(keys)) != 15 or set(keys) != expected:
        raise ValueError("observation membership mismatch")
    builds = report["builds"]
    if len(builds) != 3 or {x["program"] for x in builds} != {x[0] for x in expected}:
        raise ValueError("build membership mismatch")
    for row in builds + rows:
        if (row.get("status"), row.get("exit"), row.get("stdout_hex"),
                row.get("stderr_hex")) != ("Passed", 0, "", ""):
            raise ValueError("failed observation or build")
    series = {}
    bounded = criteria["bounded_and_io"]
    retained = criteria["retained"]
    for row in rows:
        program = row["program"]
        count = int(row["arguments"][0])
        high, heap = row["high"], row["heap"]
        for value in [high["mapped"], high["live"], high["fds"],
                      heap["resources"], heap["collections"]]:
            if type(value) is not int or value < 0:
                raise ValueError("invalid observation number")
        if heap["resources"] != criteria["final_resources"]:
            raise ValueError("owned resource leak")
        fd_limit = criteria["io_fd_max"] if program == "io-resource" else criteria["bounded_and_retained_fd_max"]
        if high["fds"] > fd_limit:
            raise ValueError("descriptor limit exceeded")
        if high["mapped"] == 0 or high["fds"] == 0:
            raise ValueError("missing runtime observation")
        if program == "lifetime-retained":
            if high["live"] == 0:
                raise ValueError("retained live control missing")
            limit = retained["mapped_and_gc_live_max_bytes_per_iteration"] * count + retained["fixed_allowance_bytes"]
            if high["mapped"] > limit or high["live"] > limit:
                raise ValueError("retained envelope exceeded")
        elif high["mapped"] > bounded["mapped_max_bytes"] or high["live"] > bounded["gc_live_max_bytes"]:
            raise ValueError("bounded envelope exceeded")
        key = (program, row["arguments"][1] if program == "io-resource" else "")
        series.setdefault(key, []).append((count, high))
    for (program, mode), samples in series.items():
        samples.sort()
        if program == "lifetime-retained":
            for (_, left), (_, right) in zip(samples, samples[1:]):
                if any(right[key] < left[key] * retained["successive_mapped_and_gc_live_min_ratio"]
                       for key in ("mapped", "live")):
                    raise ValueError("retained growth control missing")
        elif max(x["mapped"] for _, x in samples) - min(x["mapped"] for _, x in samples) > bounded["mapped_series_spread_max_bytes"]:
            raise ValueError("bounded mapped accumulation")
    return {"observations": len(rows), "series": len(series), "criteria_satisfied": True}


def verify_raw(directory, report):
    directory = Path(directory).resolve()
    for row in report["records"]:
        path = directory / row["observation"]
        if path.parent.resolve() != directory:
            raise ValueError("observation outside evidence directory")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["observation_sha256"]:
            raise ValueError("raw observation digest mismatch")
        data = json.loads(raw)
        if data["exit"] != 0 or data["heap"] != row["heap"] or data["high"] != row["high"]:
            raise ValueError("raw observation differs from summary")
    for row in report["builds"]:
        if hashlib.sha256((directory / row["program"]).read_bytes()).hexdigest() != row["artifact_sha256"]:
            raise ValueError("observed artifact changed")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    args = parser.parse_args()
    budget = json.loads(args.budget.read_text())
    report = json.loads((args.observations / "results.json").read_text())
    verify_raw(args.observations, report)
    print(json.dumps(validate(budget, report), sort_keys=True))
