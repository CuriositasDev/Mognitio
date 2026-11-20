"""Exercise idle fallback accounting and descendants owned by a non-main thread."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/lsp"))
import budget


def must_exceed(observer):
    try:
        observer.check()
    except RuntimeError as error:
        assert "memory budget exceeded" in str(error)
    else:
        raise AssertionError("Expected the live session to exceed its RSS limit")


def run():
    baseline = set(os.listdir("/proc/self/fd"))
    with patch.object(budget.MemoryBudget, "_setup_group"):
        observer = budget.MemoryBudget()
    try:
        # An idle tick must read its existing handles and observe current RSS.
        with patch.object(Path, "read_text", side_effect=AssertionError("transient proc open")):
            observer.check()
            with patch.object(budget, "LIMIT", 0):
                must_exceed(observer)

        @contextmanager
        def child_using_memory():
            code = "import sys; a = bytearray(64 << 20); print('ready', flush=True); sys.stdin.read()"
            with subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as child:
                try:
                    assert child.stdout.readline() == b"ready\n"
                    yield
                finally:
                    child.stdin.close()

        rss = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        with patch.object(budget, "LIMIT", rss + (32 << 20)):
            with child_using_memory():
                must_exceed(observer)
            observer.check()

            ready = threading.Event()
            stop = threading.Event()

            def own_child():
                with child_using_memory():
                    ready.set()
                    stop.wait(15)

            worker = threading.Thread(target=own_child)
            worker.start()
            try:
                assert ready.wait(10)
                must_exceed(observer)
            finally:
                stop.set()
                worker.join(10)
            assert not worker.is_alive()
        observer.check()
    finally:
        observer.close()
    assert set(os.listdir("/proc/self/fd")) == baseline
    print("PASS idle RSS, main- and other-thread child RSS and descriptor cleanup")


if __name__ == "__main__":
    run()
