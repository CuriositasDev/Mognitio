#!/usr/bin/env python3
"""Generate the short local-node radix memo used only while pruning forests."""
import argparse
import importlib.util
from pathlib import Path
BASE = Path(__file__).with_name("generate-int-map.py")
TARGET = Path(__file__).resolve().parents[2] / "compiler/mgnc/src/PruneMemo/map.mgn"
def generate():
    spec = importlib.util.spec_from_file_location("int_map_generator", BASE)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    generator.LEVELS, generator.LAST, generator.LIMIT = 8, 7, 65536
    code = generator.generate().replace("namespace Mgnc\\IntMap;", "namespace Mgnc\\PruneMemo;")
    code = code.replace("use Mgnc\\Data\\{Diagnostic,Span,problem};", "use Mgnc\\Data\\{Diagnostic,Span,problem};\nuse Mgnc\\IntMap\\{Map as FullMap,create as fullCreate,get as fullGet,put as fullPut};")
    code = code.replace("public type Entry=product{key:Int;value:Int;};\n", "")
    code = code.replace("large:List<Entry>;", "large:FullMap;")
    code = code.replace("large:List<Entry>[]", "large:fullCreate()")
    old = "  loop over(table->large as entry:Entry){branch when{entry->key==key=>{return Result<Int,Diagnostic>::Ok(entry->value);},else=>unit};};return Result<Int,Diagnostic>::Ok(-2);"
    assert code.count(old) == 1
    code = code.replace(old, "  return fullGet(table->large,key);")
    old = "  var large:List<Entry>=List<Entry>[];var found:Bool=false;\n  loop over(table->large as entry:Entry){branch when{entry->key==key=>{large=large->append(Entry{key:key,value:value});found=true;},else=>{large=large->append(entry);}};};\n  branch when{!found=>{large=large->append(Entry{key:key,value:value});},else=>unit};return Result<Map,Diagnostic>::Ok(Map{small:table->small,large:large});"
    assert code.count(old) == 1
    code = code.replace(old, "  return Result<Map,Diagnostic>::Ok(Map{small:table->small,large:try fullPut(table->large,key,value)});")
    code = code.replace("// Generated fixed-field radix tree. Empty subtrees are shared immutable values.", "// Pruning memo: eight radix levels for local node IDs; larger keys use IntMap.\n// Empty subtrees and fallback maps are immutable, including retained snapshots.")
    assert "Entry" not in code
    return code

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--target", type=Path, default=TARGET)
    args = parser.parse_args()
    result = generate()
    if args.check:
        assert args.target.read_text() == result
    else:
        args.target.parent.mkdir(parents=True, exist_ok=True)
        args.target.write_text(result)
    print("PRUNE_MEMO_REPRODUCIBLE")
if __name__ == "__main__":
    main()
