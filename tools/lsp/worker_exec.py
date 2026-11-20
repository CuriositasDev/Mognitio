"""The worker cannot outlive its coordinator, including abrupt parent death."""
import ctypes
import os
import signal
import sys

parent = int(sys.argv[1])
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
    sys.exit(3)
if sys.argv[2] == "--argv0":
    os.execv(sys.argv[4], [sys.argv[3], *sys.argv[5:]])
os.execv(sys.argv[2], sys.argv[2:])
