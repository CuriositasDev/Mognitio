#!/usr/bin/env python3
"""Adversarial controls for fresh performance samples and purpose budgets."""
import copy
import unittest
from v180_performance import KINDS, score, validate_budget_scope

class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.runs = [dict(kind=kind, correct=True, signal=None, cutoff=None,
            harness_failure=None, descendant_residue=0, unreaped_descendants=0,
            observer_policy="fresh-process-v2-tree", seconds=seconds,
            peak_rss_bytes=kernel, sampled_peak_rss_bytes=sampled,
            rss_missing_samples=0)
            for kind,seconds,kernel,sampled in zip(KINDS,
                [100, 1, 9, 2], [999999, 10, 11, 12], [999999, 20, None, 15])]
        self.limit = dict(wall_median_seconds=2, rss_max_bytes=20,
                          wall_guard_seconds=10, rss_guard_bytes=30)
    def test_exact_median_and_max_without_warmup_or_outlier_removal(self):
        result = score(self.runs, self.limit)
        self.assertEqual(result, dict(passed=True, correct=True, within_budget=True,
                                      wall_median_seconds=2, rss_max_bytes=20))
        self.runs[2]["peak_rss_bytes"] = 31
        self.assertFalse(score(self.runs, self.limit)["passed"])
    def test_null_sampler_uses_kernel_without_subtracting_floor(self):
        for row in self.runs:row["sampled_peak_rss_bytes"] = None
        self.assertEqual(score(self.runs)["rss_max_bytes"], 12)
        self.assertIsNone(score(self.runs)["within_budget"])
    def test_invalid_warmup_cannot_be_dropped(self):
        changes = [("correct", False), ("correct", 1), ("signal", 9),
            ("cutoff", "wall"), ("harness_failure", "missing worker"),
            ("descendant_residue", 1), ("unreaped_descendants", 1),
            ("descendant_residue", False), ("observer_policy", "old"),
            ("seconds", 0), ("seconds", True), ("seconds", float("nan")),
            ("seconds", float("inf")), ("peak_rss_bytes", 0),
            ("peak_rss_bytes", None), ("sampled_peak_rss_bytes", 0),
            ("sampled_peak_rss_bytes", True), ("rss_missing_samples", -1),
            ("rss_missing_samples", False)]
        for key,value in changes:
            rows = copy.deepcopy(self.runs);rows[0][key] = value
            with self.subTest(key=key,value=value):self.assertFalse(score(rows)["correct"])
        rows = copy.deepcopy(self.runs);del rows[0]["cutoff"]
        self.assertFalse(score(rows)["correct"])
    def test_missing_duplicate_reordered_or_extra_run_rejected(self):
        for rows in [self.runs[1:], self.runs+[self.runs[-1]],
                     [self.runs[0],self.runs[2],self.runs[1],self.runs[3]],
                     [*self.runs[:3],self.runs[2]], [None]*4, None]:
            with self.subTest(rows=rows):self.assertFalse(score(rows)["passed"])
    def test_thresholds_and_guard_validation(self):
        for field in ["wall_median_seconds", "rss_max_bytes"]:
            limit = dict(self.limit);limit[field] -= 1
            self.assertFalse(score(self.runs, limit)["passed"])
        for field,value in [("wall_median_seconds",float("nan")),
                ("rss_max_bytes",False),("wall_guard_seconds",1),("rss_guard_bytes",19)]:
            limit=dict(self.limit);limit[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):score(self.runs,limit)
    def test_budget_scope_and_purpose_binding(self):
        manifest=dict(candidate="c"*64,cells=[dict(name="A/check",group="check")])
        budget=dict(status="Accepted",candidate=manifest["candidate"],
            manifest_sha256="d"*64,warmups=1,recorded_runs=3,
            rss_metric="max(kernel_peak,sampled_tree_peak)",
            cells={"A/check":dict(self.limit,group="check",purpose="Interactive validation")})
        def validate(b):return validate_budget_scope(manifest,b,manifest["candidate"],"d"*64)
        self.assertTrue(validate(budget))
        for field,value in [("status","Draft"),("candidate","e"*64),
            ("manifest_sha256","e"*64),("warmups",True),("recorded_runs",2),
            ("rss_metric","sampled-only"),("cells",{})]:
            changed=copy.deepcopy(budget);changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate(changed)
        for field,value in [("group","native"),("purpose","  ")]:
            changed=copy.deepcopy(budget);changed["cells"]["A/check"][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate(changed)
        manifest["cells"]*=2
        with self.assertRaises(ValueError):validate(budget)

if __name__ == "__main__":unittest.main()
