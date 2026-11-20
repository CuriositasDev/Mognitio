"""Materialize one captured LSP generation and project native compiler records."""
import json
from pathlib import Path, PurePosixPath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.selfhost.client import WorkerError, decimal, request


def snapshot_file(root, name, text):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name or not path.parts:
        raise WorkerError("Invalid path in captured snapshot")
    dest = root.joinpath(*path.parts)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as handle:
        handle.write(text.encode("utf-8", "strict"))
    dest.chmod(0o400)
    return str(dest)


def project(reply, names, texts, result):
    def source(name):
        name = names.get(name, name)
        if name not in texts:
            raise WorkerError("Compiler referred to a file outside this snapshot")
        return name

    def offsets(path, first, last):
        data = texts[path]
        start, end = decimal(first, 999999999), decimal(last, 999999999)
        if start > end or end > len(data) or any(pos < len(data) and data[pos] & 0xc0 == 0x80 for pos in (start, end)):
            raise WorkerError("Compiler range is outside the captured UTF-8 text")
        return start, end

    def diagnostic(name, phase, message, known, first, last):
        path = source(name)
        start, end = offsets(path, first, last) if known == "1" else (None, None)
        if known not in ("0", "1"):
            raise WorkerError("Invalid diagnostic position state")
        item = dict(path=path, phase=phase, message=message, start=start, end=end)
        rows = result["diagnostics"]
        for row in rows:
            if all(row.get(k) == v for k, v in item.items()):
                return row
        if len(rows) < 2001:
            rows.append(item)
        if len(result["diagnostics"]) >= 200:
            result["truncated"] = True
        return item

    def related(row, name, message, first, last):
        path = source(name)
        start, end = offsets(path, first, last)
        note = dict(path=path, message=message, start=start, end=end)
        notes = row.setdefault("related", [])
        if note not in notes:
            notes.append(note)

    if reply.status == "diagnostic":
        status, path, phase, message, known, start, end, *_ = reply.fields
        if status == "3":
            raise WorkerError("Compiler analysis failed internally")
        result["complete"] = False
        row = diagnostic(path, phase, message, known, start, end)
        for i in range(12, len(reply.fields), 6):
            related(row, *reply.fields[i:i+4])
        return

    if reply.status != "analysis":
        raise WorkerError("Expected a native analysis result")
    fields = reply.fields
    if fields[0] == "partial":
        result["complete"] = False
    i = 1
    row = None
    while i < len(fields):
        kind = fields[i]
        if kind == "D" and i + 7 <= len(fields):
            row = diagnostic(*fields[i+1:i+7])
            result["complete"] = False
            i += 7
        elif kind == "N" and i + 5 <= len(fields) and row is not None:
            related(row, *fields[i+1:i+5])
            i += 5
        elif kind == "T" and i + 6 <= len(fields):
            row = None
            name, first, last, role, modifiers = fields[i+1:i+6]
            path = source(name)
            start, end = offsets(path, first, last)
            rows = result["tokens"][path]
            if start == end or rows and start < rows[-1][1]:
                raise WorkerError("Overlapping or empty native token")
            rows.append([start, end, decimal(role, 10), decimal(modifiers, 7)])
            i += 6
        else:
            raise WorkerError("Incomplete native analysis record")


def analyze(compiler, build, generation, directory, snapshot):
    sources = snapshot["sources"]
    names = {}
    texts = {name:text.encode("utf-8", "strict") for name, text in sources.items()}
    result = {"tokens": {name:[] for name in sources}, "diagnostics": [], "complete": True}
    def query(profile, path):
        answer = request(compiler, build, profile, generation=str(generation), path=path, timeout=10)
        project(answer, names, texts, result)

    if snapshot.get("root") is not None:
        manifest = snapshot_file(directory, "mognitio.toml", snapshot["manifest"])
        names[manifest] = "mognitio.toml"
        texts["mognitio.toml"] = snapshot["manifest"].encode()
        (directory / "src").mkdir()
        for name, text in sources.items():
            if not name.startswith("src/") or not name.endswith(".mgn"):
                raise WorkerError("Unexpected captured project member")
            names[snapshot_file(directory, name, text)] = name
        query("analysis", manifest)
    else:
        for index, (uri, text) in enumerate(sources.items()):
            path = snapshot_file(directory, f"source-{index}.mgn", text)
            names[path] = uri
            query("syntax", path)
    return result


if __name__ == "__main__":
    result = analyze(sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4]), json.load(sys.stdin.buffer))
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
