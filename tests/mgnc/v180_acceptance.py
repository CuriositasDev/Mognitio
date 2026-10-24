"""Strict functional execution and inherited performance binding checks."""
from v180_evidence import canonical, digest, identity, require, valid_hash, validate_graph

BINDINGS = ("candidate", "cell", "generation", "producer", "source", "environment", "target")


def bytes_value(value):
    require(isinstance(value, str), "missing byte stream")
    try:
        result = bytes.fromhex(value)
    except ValueError as error:
        raise ValueError("invalid byte stream") from error
    require(result.hex() == value, "noncanonical byte stream")
    return result


def match_stream(actual, expected):
    require(isinstance(expected, dict) and bool(expected), "empty stream oracle")
    allowed = {"exact_hex", "contains_all_hex", "contains_any_hex"}
    require(set(expected) <= allowed, "unknown stream oracle")
    if "exact_hex" in expected:
        require(len(expected) == 1, "ambiguous exact stream oracle")
        return actual == bytes_value(expected["exact_hex"])
    for name in expected:
        values = expected[name]
        require(isinstance(values, list) and values, "empty diagnostic alternatives")
        needles = [bytes_value(value) for value in values]
        require(all(needles), "empty diagnostic fragment")
        if name == "contains_all_hex" and not all(x in actual for x in needles):
            return False
        if name == "contains_any_hex" and not any(x in actual for x in needles):
            return False
    return True


def evaluate_execution(store, contract, execution_id):
    """Use a previously fixed contract; a Passed label alone is never sufficient."""
    require(set(BINDINGS) <= contract.keys(), "incomplete cell binding")
    require(contract["generation"] in ("A", "B", "C"), "unknown generation")
    for field in ("candidate", "producer", "source", "environment", "expected"):
        valid_hash(contract[field])
    execution = store.get(execution_id, "Execution")
    require(all(execution.get(key) == contract[key] for key in BINDINGS),
            "execution cell/generation/environment/target binding mismatch")
    require(execution.get("expected") == contract["expected"], "expected identity changed")
    expected = store.get(contract["expected"], "Expected")
    require(type(expected.get("exit")) is int and 0 <= expected["exit"] <= 255,
            "invalid expected exit")
    require(isinstance(expected.get("observables"), dict), "missing observable contract")
    graph = contract.get("generation_graph")
    require(isinstance(graph, list) and contract["producer"] in graph, "missing producer graph")
    validate_graph(store, contract["candidate"], graph)
    edge = store.get(contract["producer"], "BuildEdge")
    require(edge["candidate"] == contract["candidate"] and edge["status"] == "Passed"
            and edge["role"] == contract["generation"], "wrong generation producer")
    store.get(contract["environment"], "Environment")
    store.get(contract["source"], "SourceSet")
    raw = store.get(execution["raw"], "Raw")
    require(isinstance(raw.get("files"), list), "missing raw ledger")
    entries = {item["path_b64"]: item for item in raw["files"]}
    require(len(entries) == len(raw["files"]), "duplicate raw path")
    streams = {}
    for name in ("stdout", "stderr"):
        content = bytes_value(execution.get(name + "_hex"))
        path = execution.get("stream_paths", {}).get(name)
        require(path in entries and entries[path].get("type") == "file", "raw stream absent")
        item = entries[path]
        require(item["sha256"] == digest(content) and item["bytes"] == len(content),
                "stream bytes do not match raw ledger")
        streams[name] = content
    require(execution["stream_paths"]["stdout"] != execution["stream_paths"]["stderr"],
            "stream paths aliased")
    require(execution.get("status") == "Passed", "unsuccessful execution cannot be promoted")
    clean = (execution.get("signal") is None and execution.get("cutoff") is None
             and execution.get("harness_failure") is None
             and execution.get("descendant_residue") == 0
             and execution.get("unreaped_descendants") == 0)
    require(all(key in execution for key in ("signal", "cutoff", "harness_failure")),
            "missing terminal outcome")
    correct = clean and type(execution.get("exit")) is int and execution["exit"] == expected["exit"]
    correct = correct and streams["stdout"] == bytes_value(expected["stdout_hex"])
    correct = correct and match_stream(streams["stderr"], expected["stderr"])
    actual = execution.get("observables")
    require(isinstance(actual, dict), "missing observed side effects")
    correct = correct and all(key in actual and canonical(actual[key]) == canonical(value)
                              for key, value in expected["observables"].items())
    return "Passed" if correct else "Failed"


def evaluate_matrix(store, contracts, execution_ids):
    require(bool(contracts), "empty acceptance matrix")
    require(all(key == value["cell"] for key, value in contracts.items()), "cell key mismatch")
    found = {}
    for key in execution_ids:
        execution = store.get(key, "Execution")
        cell = execution.get("cell")
        require(cell in contracts and cell not in found, "unexpected or duplicate execution")
        found[cell] = evaluate_execution(store, contracts[cell], key)
    return {key: found.get(key, "NotRun") for key in contracts}


def inherited_role(manifest, cell):
    """Derive roles from immutable command dependencies, not display names."""
    builders = {row["build_key"]: row for row in manifest["cells"] if row["build_key"]}
    require(len(builders) == sum(bool(row["build_key"]) for row in manifest["cells"]),
            "ambiguous old artifact key")
    active = set()
    def resolve(row):
        require(row["name"] not in active, "old producer cycle")
        active.add(row["name"])
        command = row["command"]
        dependencies = [part.split(":", 1)[1] for part in command
                        if part.startswith("$ARTIFACT:")]
        require(len(set(dependencies)) <= 1, "ambiguous measured dependency")
        if dependencies:
            key = dependencies[0]
            require(key in builders and row["artifact_dependency"] == key,
                    "missing or mismatched old producer")
            parent = builders[key]
            if key in ("B0", "B1"):
                require(parent["source"] == ("C0" if key == "B0" else "C1")
                        and parent["command"][0] == manifest["compiler"],
                        "wrong old compiler source/producer")
                result = "D0" if key == "B0" else "D1"
            else:
                result = "program:" + resolve(parent)
        elif row["group"] == "bootstrap":
            require(row["name"] == "S-build-A" and row["source"] == "C1"
                    and row["artifact_dependency"] is None, "wrong old bootstrap")
            result = "S17"
        else:
            require(command[0] == manifest["compiler"] and row["artifact_dependency"] is None,
                    "unrecognized old producer")
            result = "A"
        active.remove(row["name"])
        return result
    return resolve(cell)


def validate_inherited_mapping(manifest, budget, mapping, bindings):
    """Keep old criteria and the new producer graph as separate immutable objects."""
    require(mapping["manifest_sha256"] == identity(manifest), "old manifest changed")
    require(mapping["budget_sha256"] == identity(budget), "old budget changed")
    require(mapping["candidate"] == bindings["candidate"], "mixed mapped candidate")
    cells = {row["name"]: row for row in manifest["cells"]}
    require(len(cells) == len(manifest["cells"]), "duplicate old cell")
    require(set(mapping["cells"]) == set(cells) == set(budget["cells"]), "old scope changed")
    for name, cell in cells.items():
        row = mapping["cells"][name]
        role = inherited_role(manifest, cell)
        require(row["role"] == role and role in bindings["roles"], "wrong mapped producer")
        require(row["producer"] == bindings["roles"][role], "stale or substituted producer")
        require(row["source"] == cell["source"]
                and row["old_cell_sha256"] == identity(cell), "old input/expectation changed")
        require(row["limit"] == budget["cells"][name], "old threshold changed")
        require(row["measurement"] == bindings["measurement"], "old observer policy changed")
        require(row["includes_dependency_build"] is False, "dependency build mixed into measurement")
    return True
