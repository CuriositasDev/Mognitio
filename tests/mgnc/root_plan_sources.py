"""Stage the actual transitive compiler imports for root-plan oracle probes."""
from pathlib import Path
import re
import shutil


def prepare(root: Path, harness_name: str, project: Path):
    compiler = root / "compiler/mgnc"
    sources = {}
    for original in sorted((compiler / "src").rglob("*.mgn")):
        text = original.read_text()
        match = re.search(r"namespace ([A-Za-z0-9_\\]+);", text)
        if match:
            sources.setdefault(match.group(1), []).append((original, text))
    reference = root / "tests/mgnc/harnesses/v160-root-reference.mgn"
    assert "Mgnc\\RootReference" not in sources, "test oracle namespace collision"
    sources["Mgnc\\RootReference"] = [(reference, reference.read_text())]
    harness = (root / "tests/mgnc/harnesses" / harness_name).read_text()
    imports = lambda text: re.findall(r"use (Mgnc\\[A-Za-z0-9_\\]+)\\\{", text)
    pending, selected = imports(harness), {}
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        assert name in sources, name
        selected[name] = sources[name]
        for original, text in sources[name]:
            pending.extend(imports(text))
    assert {"Mgnc\\RootReference", "Mgnc\\WholeRoots", "Mgnc\\WholeRootCheck", "Mgnc\\WholeLayoutCheck"} <= selected.keys()
    (project / "src").mkdir(parents=True)
    shutil.copyfile(compiler / "mognitio.toml", project / "mognitio.toml")
    shutil.copyfile(root / "tests/mgnc/harnesses" / harness_name, project / "src/mgnc.mgn")
    for name, parts in selected.items():
        for original, text in parts:
            relative = Path("RootReference/verify.mgn") if name == "Mgnc\\RootReference" else original.relative_to(compiler / "src")
            target = project / "src" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            assert target.read_bytes() == original.read_bytes(), target
    return selected
