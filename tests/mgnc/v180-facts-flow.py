#!/usr/bin/env python3
"""Compile fixed bitmap and flow oracles, preserving source closure and raw evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/mgnc/harnesses/v180-facts"
sys.path.insert(0, str(ROOT / "tests/mgnc"))
from v180_observer import observe

EXPECTED = {
    "facts": "FACTS_ORACLE_OK equal=132 define=258\n",
    "edit": "EDIT_ORACLE_OK equal=132 define=258\n",
    "editsequence": "EDIT_SEQUENCE_OK sequences=18 reads=3759\nCACHED_READ_BOUNDARY_OK cases=6 reads=9\n",
    "compaction": "BOUNDED_FLOW_OK cases=22\n",
    "dataflow": "V160_DATAFLOW_OK valid=3 rejected=8\nV160_DATAFLOW_WIDE_OK valid=3 rejected=5\n",
}
THRESHOLD = "branch when{outgoing->values->count/2>=order->count=>{outgoing=try compact(outgoing,order);},else=>unit};"
APPEND = "outgoing=Flow{heads:try put(outgoing->heads,current,outgoing->values->count),values:push<Facts>(outgoing->values,next)};"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            info = path.stat()
            result[str(path.relative_to(root))] = dict(
                sha256=sha(path), size=info.st_size, mode=info.st_mode,
                mtime_ns=info.st_mtime_ns)
    return result


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def make_fixture(source, destination, kind, mutation=None):
    harness = (ROOT / "tests/mgnc/harnesses/v160-dataflow.mgn"
               if kind == "dataflow" else FIXTURES / (kind + "-oracle.mgn"))
    entry = harness.read_text()
    namespaces = {}
    for path in sorted((source / "src").rglob("*.mgn")):
        namespace = re.search(r"namespace\s+([\w\\]+)\s*;", path.read_text())[1]
        namespaces.setdefault(namespace, []).append(path)
    selected = set()
    visited = set()
    pending = re.findall(r"use\s+(Mgnc(?:\\\w+)*)\\\{", entry)
    while pending:
        namespace = pending.pop()
        if namespace in visited:
            continue
        visited.add(namespace)
        for path in namespaces[namespace]:
            selected.add(path)
            pending += re.findall(r"use\s+(Mgnc(?:\\\w+)*)\\\{", path.read_text())
    destination.mkdir()
    for path in sorted(selected | {source / "mognitio.toml"}):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    if kind == "compaction":
        module = destination / "src/WholeDataflow/dataflow.mgn"
        adapter = (FIXTURES / "compaction-adapter.mgn").read_text()
        original = module.read_text()
        # Check both production update statements before testing the private helper.
        for statement in [THRESHOLD, APPEND]:
            assert original.count(statement) == adapter.count(statement) == 1
        module.write_text(original + adapter)
    shutil.copy2(harness, destination / "src/mgnc.mgn")
    if mutation:
        path = destination / mutation.get("file", "src/Facts/facts.mgn")
        content = path.read_text()
        assert content.count(mutation["old"]) == mutation["count"]
        path.write_text(content.replace(mutation["old"], mutation["new"]))
    return sorted(str(path.relative_to(source)) for path in selected)


def checked(command, directory, timeout, rss_limit, code, stdout):
    observation = observe(command, directory, timeout=timeout, rss_limit=rss_limit, interval=.01)
    save(directory / "result.json", dict(command=command, observation=observation))
    assert observation["exit"] == code
    assert all(observation[key] is None for key in ["signal", "cutoff", "harness_failure"])
    assert observation["descendant_residue"] == observation["unreaped_descendants"] == 0
    assert (directory / "stdout").read_bytes() == stdout
    assert (directory / "stderr").read_bytes() == b""
    return observation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT / "compiler/mgnc")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--program-mode", choices=["0700", "0755"], required=True)
    parser.add_argument("--mutants", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    source, compiler, output = (args.source.resolve(), args.compiler.resolve(), args.output.resolve())
    assert not output.exists()
    output.mkdir(parents=True)
    before = inventory(source)
    compiler_hash = sha(compiler)
    fixtures_before = inventory(FIXTURES)
    jobs = [dict(name=kind, oracle=kind, expected_stdout=expected, expected_exit=0)
            for kind, expected in EXPECTED.items()]
    if args.mutants:
        mutations = json.loads((FIXTURES / "mutants.json").read_text())
        assert len(mutations) == 19
        jobs += [dict(job, expected_exit=1) for job in mutations]
    save(output / "plan.json", dict(jobs=jobs, source=before, compiler_sha256=compiler_hash,
                                   fixtures=fixtures_before, program_mode=args.program_mode))
    records = []
    for job in jobs:
        case = output / job["name"]
        case.mkdir()
        fixture = case / "compiler"
        selection = make_fixture(source, fixture, job["oracle"], job.get("mutation"))
        inputs = inventory(fixture)
        save(case / "inputs.json", inputs)
        record = dict(name=job["name"], oracle=job["oracle"], product_files=selection,
                      expected_exit=job["expected_exit"], expected_stdout=job["expected_stdout"])
        if not args.prepare_only:
            command = [str(compiler), "build", str(fixture / "mognitio.toml"),
                       "-o", str(case / "build/program")]
            checked(command, case / "build", 900, 8 * 1024**3, 0, b"")
            program = case / "build/program"
            assert program.read_bytes()[:4] == b"\x7fELF"
            assert stat.S_IMODE(program.stat().st_mode) == int(args.program_mode, 8)
            checked([str(program)], case / "run", 180, 2 * 1024**3,
                    job["expected_exit"], job["expected_stdout"].encode())
            record["program_sha256"] = sha(program)
        assert inventory(fixture) == inputs and inventory(source) == before
        assert sha(compiler) == compiler_hash and inventory(FIXTURES) == fixtures_before
        records.append(record)
        save(case / "completion.json", record)
    report = dict(status="PreparedNotRun" if args.prepare_only else "FactsAndFlowOraclesPassed",
                  records=records, positive=5, mutations=19 if args.mutants else 0,
                  compiler_sha256=compiler_hash, source=before,
                  scope="Fixed independent golden values and exact first mutation failures. "
                        "Complete namespace files; compaction export appended to intact product module. "
                        "Private helper checks complement end-to-end dataflow and verifier regressions. "
                        "Implementation gate only, not performance or final candidate acceptance.")
    save(output / "completion.json", report)
    print(json.dumps(dict(status=report["status"],positive=5,mutations=report["mutations"])))


if __name__ == "__main__":
    main()
