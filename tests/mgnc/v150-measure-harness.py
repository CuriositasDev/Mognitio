#!/usr/bin/env python3
"""Exercise reap metrics, captured streams, deadlines and observed RSS cutoffs."""
import sys,tempfile
from unittest.mock import patch
from pathlib import Path
from v150_measurelib import observe
with tempfile.TemporaryDirectory() as temporary:
 root=Path(temporary)
 fast=observe([sys.executable,"-c","import sys;print('out');print('err',file=sys.stderr);sys.exit(42)"],root/"exit")
 assert fast["exit"]==42 and fast["signal"] is None and fast["cutoff"] is None and fast["harness_failure"] is None,fast
 assert fast["peak_rss_bytes"]==fast["peak_rss_raw"]*1024 and fast["peak_rss_bytes"]>0,fast
 assert (root/"exit/stdout").read_bytes()==b"out\n" and (root/"exit/stderr").read_bytes()==b"err\n"
 wall=observe([sys.executable,"-c","import time;time.sleep(10)"],root/"wall",timeout=.15)
 assert wall["cutoff"]=="wall" and wall["signal"]==9 and wall["harness_failure"] is None,wall
 rss=observe([sys.executable,"-c","import time;x=bytearray(64*1024*1024);time.sleep(10)"],root/"rss",rss_limit=32*1024**2)
 assert rss["cutoff"]=="rss" and rss["signal"]==9 and rss["last_sample"]["rss_bytes"]>32*1024**2,rss
 assert rss["peak_rss_bytes"]>32*1024**2,rss
 # Force the kernel's mm-release window independently of actual scheduling.
 def no_rss(path,*args,**kwargs):return "State:\\tR (running)\\n"
 with patch.object(Path,"read_text",no_rss):
  exiting=observe([sys.executable,"-c","pass"],root/"exit-race")
  unavailable=observe([sys.executable,"-c","import time;time.sleep(10)"],root/"unavailable")
 assert exiting["exit"]==0 and exiting["harness_failure"] is None,exiting
 assert exiting["peak_rss_bytes"]>0 and exiting["last_sample"] is None,exiting
 assert unavailable["harness_failure"]=="RuntimeError: process RSS unavailable beyond exit grace" and unavailable["signal"]==9,unavailable
 print("V150_MEASUREMENT_HARNESS_OK exit=true streams=true wait4=true wall=true rss=true exit_race=true unavailable=true")
