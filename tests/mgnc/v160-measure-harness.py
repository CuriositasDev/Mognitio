#!/usr/bin/env python3
"""Exercise real exit, timeout, RSS and surviving-descendant observations."""
import os, signal, sys, tempfile
from pathlib import Path
from v160_measurelib import observe

checks = 0
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    def run(name, code, **options):
        return observe([sys.executable, "-c", code], root/name, **options)
    result = run("normal", "import sys;print('out');sys.stderr.write('err');sys.exit(7)")
    assert result["exit"] == 7 and result["signal"] is None and result["cutoff"] is None
    assert result["harness_failure"] is None and result["descendant_residue"] == 0
    assert (root/"normal/stdout").read_bytes() == b"out\n"
    assert (root/"normal/stderr").read_bytes() == b"err"
    assert result["peak_rss_bytes"] > 0
    checks += 1
    result = run("timeout", "import time;time.sleep(20)", timeout=.1)
    assert result["signal"] == signal.SIGKILL and result["cutoff"] == "wall"
    assert result["harness_failure"] is None
    checks += 1
    result = run("rss", "import time;x=bytearray(64*1024*1024);time.sleep(20)", rss_limit=32*1024**2)
    assert result["signal"] == signal.SIGKILL and result["cutoff"] == "rss"
    assert result["peak_rss_bytes"] > 32*1024**2
    checks += 1
    result = run("residue", "import os,time;pid=os.fork();time.sleep(20) if pid==0 else os._exit(0)")
    assert result["exit"] == 0 and result["harness_failure"] == "command left descendant processes"
    assert result["descendant_residue"] == 1 and result["unreaped_descendants"] == 0
    checks += 1
    result = run("group-timeout", "import os,time;os.fork();time.sleep(20)", timeout=.1)
    assert result["signal"] == signal.SIGKILL and result["cutoff"] == "wall"
    assert result["descendant_residue"] == 1 and result["unreaped_descendants"] == 0
    checks += 1
print("V160_MEASURE_HARNESS_OK checks="+str(checks))
