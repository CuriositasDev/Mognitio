#!/usr/bin/env python3
"""Apply the v1.5 initializer contract to preserved v1.3/v1.4 review sources."""
import json,sys
from pathlib import Path
import review
original=review.fixtures
migrations={
 "function-infix":"A general Function-valued initializer is parsed before checking its invalid operator.",
 "helper-infix":"The full semantic profile checks the initializer expression before native selection.",
 "function-postfix":"Calling a Function expression is parsed; the wrong arity is a type error under C150-C07."
}
def fixtures():
 rows=original()
 for row in rows:
  if row["name"] in migrations:row["phase"]="type"
 return rows
review.fixtures=fixtures
try:review.main()
except SystemExit as result:
 path=Path(sys.argv[sys.argv.index("--evidence")+1])
 if path.exists():
  evidence=json.loads(path.read_text());evidence["semantic_profile"]="1.5";evidence["diagnostic_migrations"]=[{"fixture":name,"previous_phase":"parse","expected_phase":"type","reason":reason} for name,reason in migrations.items()]
  path.write_text(json.dumps(evidence,indent=2)+"\n")
 raise
