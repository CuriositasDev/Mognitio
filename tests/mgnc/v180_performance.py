"""Strict aggregation for new native performance cells.

This module does not adopt budgets or verify raw files. Callers first bind the
candidate, input, target, observer and independent oracle to verified receipts.
Inherited cells retain their original aggregation policy.
"""
import math
import statistics
from v180_evidence import require

POLICY = "fresh-process-v2-tree"
KINDS = ["warmup", "run-1", "run-2", "run-3"]
LIMIT_FIELDS = ("wall_median_seconds", "rss_max_bytes",
                "wall_guard_seconds", "rss_guard_bytes")

def positive_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0

def validate_limits(limits):
    require(isinstance(limits, dict), "missing numerical limits")
    require(all(positive_number(limits.get(k)) for k in LIMIT_FIELDS),
            "limits must be finite positive numbers")
    require(limits["wall_guard_seconds"] >= limits["wall_median_seconds"],
            "wall guard is below the budget")
    require(limits["rss_guard_bytes"] >= limits["rss_max_bytes"],
            "RSS guard is below the budget")
    return True

def valid_sample(sample):
    if not isinstance(sample, dict):
        return False
    required = {"kind", "correct", "signal", "cutoff", "harness_failure",
                "descendant_residue", "unreaped_descendants", "observer_policy",
                "seconds", "peak_rss_bytes", "sampled_peak_rss_bytes",
                "rss_missing_samples"}
    if not required <= sample.keys():
        return False
    return (
        sample["correct"] is True
        and all(sample[k] is None for k in ("signal", "cutoff", "harness_failure"))
        and all(type(sample[k]) is int and sample[k] == 0
                for k in ("descendant_residue", "unreaped_descendants"))
        and sample["observer_policy"] == POLICY
        and positive_number(sample["seconds"])
        and type(sample["peak_rss_bytes"]) is int and sample["peak_rss_bytes"] > 0
        and (sample["sampled_peak_rss_bytes"] is None or
             type(sample["sampled_peak_rss_bytes"]) is int
             and sample["sampled_peak_rss_bytes"] > 0)
        and type(sample["rss_missing_samples"]) is int
        and sample["rss_missing_samples"] >= 0
    )

def score(runs, limits=None):
    """Keep the warmup mandatory, but aggregate exactly three recorded runs."""
    if limits is not None:
        validate_limits(limits)
    valid = (isinstance(runs, list) and len(runs) == 4
             and all(isinstance(x, dict) for x in runs)
             and [x.get("kind") for x in runs] == KINDS
             and all(valid_sample(x) for x in runs))
    if not valid:
        return dict(passed=False, correct=False,
                    within_budget=False if limits is not None else None)
    wall = statistics.median(x["seconds"] for x in runs[1:])
    rss = max(max(x["peak_rss_bytes"], x["sampled_peak_rss_bytes"] or 0)
              for x in runs[1:])
    within = limits is None or (wall <= limits["wall_median_seconds"]
                               and rss <= limits["rss_max_bytes"])
    return dict(passed=within, correct=True,
                within_budget=within if limits is not None else None,
                wall_median_seconds=wall, rss_max_bytes=rss)

def validate_budget_scope(manifest, budget, candidate, manifest_sha256):
    """Validate numerical scope after the caller verifies adoption provenance."""
    require(budget.get("status") == "Accepted", "budget is not accepted")
    require(budget.get("candidate") == candidate == manifest.get("candidate"),
            "budget candidate mismatch")
    require(budget.get("manifest_sha256") == manifest_sha256,
            "budget manifest mismatch")
    require(type(budget.get("warmups")) is int and budget["warmups"] == 1
            and type(budget.get("recorded_runs")) is int
            and budget["recorded_runs"] == 3, "budget measurement counts")
    require(budget.get("rss_metric") == "max(kernel_peak,sampled_tree_peak)",
            "budget RSS policy changed")
    cells = manifest["cells"]
    names = [x["name"] for x in cells]
    require(bool(names) and len(names) == len(set(names)), "duplicate/empty cell scope")
    require(isinstance(budget.get("cells"), dict)
            and set(budget["cells"]) == set(names), "budget cell scope differs")
    for cell in cells:
        value = budget["cells"][cell["name"]]
        validate_limits(value)
        require(value.get("group") == cell["group"], "budget group differs")
        require(isinstance(value.get("purpose"), str) and value["purpose"].strip(),
                "missing budget purpose")
    return True
