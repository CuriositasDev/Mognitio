"""Bounded fresh-process observations with process-group cleanup checks."""
import ctypes, os, signal, time
from v150_measurelib import observe as observe_process

def observe(command, directory, *, timeout=900.0, rss_limit=4096*1024**2, interval=.01):
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) or libc.prctl(36, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), "cannot establish child reaping")
    # The original observer owns and reaps its direct child. As a subreaper,
    # this supervisor can also reap descendants orphaned by a failed command.
    before = set(int(x) for x in open("/proc/self/task/"+str(os.getpid())+"/children").read().split())
    try:
        result = observe_process(command, directory, timeout=timeout, rss_limit=rss_limit, interval=interval)
        child_file = "/proc/self/task/"+str(os.getpid())+"/children"
        children = set(int(x) for x in open(child_file).read().split()) - before
        residue = set(children)
        deadline = time.monotonic() + 2
        remaining = set(children)
        while remaining and time.monotonic() < deadline:
            for pid in list(remaining):
                try:
                    group = os.getpgid(pid)
                    if group != os.getpgrp(): os.killpg(group, signal.SIGKILL)
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError: pass
                try: os.waitpid(pid, os.WNOHANG)
                except ChildProcessError: pass
            remaining = set(int(x) for x in open(child_file).read().split()) - before
            residue.update(remaining)
            if remaining: time.sleep(.001)
        result.update(descendant_residue=len(residue), unreaped_descendants=len(remaining))
        if residue:
            result["harness_failure"] = result["harness_failure"] or "command left descendant processes"
        if remaining:
            result["harness_failure"] = "descendant reaping deadline"
        return result
    finally:
        libc.prctl(36, previous.value, 0, 0, 0)
