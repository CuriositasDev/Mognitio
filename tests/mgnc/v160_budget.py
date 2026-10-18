"""Require an explicitly adopted, complete candidate-bound measurement budget."""
import math, re
from v150_budget import within_budget

def load_budget(record, identity, manifest):
    if record.get("schema") != 1 or record.get("status") != "accepted":
        raise ValueError("formal budget is not accepted")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", record.get("accepted_at","")):
        raise ValueError("formal budget needs an adoption date")
    if any(record.get(key) != value for key,value in identity.items()):
        raise ValueError("formal budget identity mismatch")
    names = [c["name"] for c in manifest["cells"]]
    if len(names)!=103 or len(set(names))!=103 or set(record.get("cells",{}))!=set(names):
        raise ValueError("formal budget must cover all 103 measurement cells")
    if record.get("warmups")!=1 or record.get("recorded_runs")!=3:
        raise ValueError("formal budget requires one warm-up and three recorded runs")
    fields={"wall_median_seconds","rss_max_bytes","wall_cutoff_seconds","observed_rss_cutoff_bytes"}
    for limits in record["cells"].values():
        if set(limits)!=fields: raise ValueError("incomplete formal limits")
        for key,value in limits.items():
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError("formal limits must be finite positive numbers")
            if key.endswith("_bytes") and type(value)!=int:
                raise ValueError("memory limits require integer bytes")
        if limits["wall_median_seconds"]>limits["wall_cutoff_seconds"] or limits["rss_max_bytes"]>limits["observed_rss_cutoff_bytes"]:
            raise ValueError("cutoff below acceptance limit")
    return record
