"""Validate frozen formal-budget identities and classify complete measurements."""
import math
import re
import statistics


def load_budget(record, *, compiler_sha256, fixture_sha256, manifest, seed_sha256):
    if record.get("schema") != 1 or record.get("status") != "accepted":
        raise ValueError("formal budget must be an accepted schema-1 record")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", record.get("accepted_at", "")):
        raise ValueError("formal budget needs an adoption date")
    expected = {
        "compiler_sha256": compiler_sha256,
        "fixture_manifest_sha256": fixture_sha256,
        "seed_archive_sha256": seed_sha256,
    }
    names = [cell["name"] for cell in manifest["cells"]]
    if len(names) != 118 or len(set(names)) != 118 or not {"C0", "C1"} <= set(names):
        raise ValueError("formal measurement requires all 118 distinct cells")
    c1 = next(cell for cell in manifest["cells"] if cell["name"] == "C1")
    expected["source_inventory_sha256"] = c1["inventory_sha256"]
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError("formal budget candidate, seed or fixture identity mismatch")
    if record.get("warmups") != 1 or record.get("recorded_runs") != 3:
        raise ValueError("formal measurement requires one warm-up and three runs")
    if set(record.get("cells", {})) != set(names):
        raise ValueError("formal budget must cover exactly the fixture cells")
    fields = {"wall_median_seconds", "rss_max_bytes", "wall_cutoff_seconds",
              "observed_rss_cutoff_bytes"}
    for limits in record["cells"].values():
        if set(limits) != fields:
            raise ValueError("formal budget fields are incomplete")
        for key, value in limits.items():
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("formal budgets must be finite positive numbers")
            if key.endswith("_bytes") and type(value) is not int:
                raise ValueError("formal memory limits must use integer bytes")
        if (limits["wall_median_seconds"] > limits["wall_cutoff_seconds"]
                or limits["rss_max_bytes"] > limits["observed_rss_cutoff_bytes"]):
            raise ValueError("formal cutoff is below its acceptance budget")
    return record


def within_budget(runs, limits):
    if ([run["kind"] for run in runs] != ["warmup", "run-1", "run-2", "run-3"]
            or not all(run["correct"] and run["input_unchanged"]
                       and run["cutoff"] is None and run["harness_failure"] is None
                       for run in runs)):
        return False
    measured = runs[1:]
    values = [run["seconds"] for run in measured] + [
        run["peak_rss_bytes"] for run in measured]
    if not all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in values):
        return False
    return (statistics.median(run["seconds"] for run in measured)
            <= limits["wall_median_seconds"]
            and max(run["peak_rss_bytes"] for run in measured) <= limits["rss_max_bytes"])
