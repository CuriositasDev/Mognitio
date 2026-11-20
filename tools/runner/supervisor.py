"""Supervise one native test child using the runner's private descriptor layout."""
from contextlib import contextmanager, ExitStack
import errno
import fcntl
import os
import selectors
import signal

from .events import Events


@contextmanager
def _defer_interrupts():
    # The CLI runner owns one child and runs on the main thread. Publish ownership
    # before delivering signals that can unwind Python frames.
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM, signal.SIGHUP})
    try:
        yield previous
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _pipe(stack):
    ends = os.pipe2(os.O_CLOEXEC)
    try:
        handles = []
        for fd, mode in zip(ends, ("rb", "wb")):
            high_fd = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 6)
            try:
                handle = os.fdopen(high_fd, mode, buffering=0)
            except BaseException:
                os.close(high_fd)
                raise
            handles.append(stack.enter_context(handle))
        return handles
    finally:
        for fd in ends:
            os.close(fd)


def _close_actions():
    if hasattr(os, "POSIX_SPAWN_CLOSEFROM"):
        return [(os.POSIX_SPAWN_CLOSEFROM, 6)]
    # Python 3.12 does not expose addclosefrom_np. The single-threaded runner
    # creates all its own descriptors with CLOEXEC. Close inherited ones too.
    actions = []
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        if fd >= 6:
            try:
                if os.get_inheritable(fd):
                    actions.append((os.POSIX_SPAWN_CLOSE, fd))
            except OSError as error:
                # listdir's own directory descriptor was already closed.
                if error.errno != errno.EBADF:
                    raise
    return actions


def supervise(image, arguments, outcome, application, diagnostic):
    """Mutate outcome in place. Renderers receive bounded chunks of bytes."""
    events = Events(outcome)
    pid = None
    status = None
    with ExitStack() as stack:
        try:
            with _defer_interrupts() as original_mask:
                channels = {}
                sources = []
                for fd in range(1, 6):
                    read, write = _pipe(stack)
                    child, parent = (read, write) if fd == 4 else (write, read)
                    sources.append(child)
                    channels[fd] = parent
                actions = [(os.POSIX_SPAWN_OPEN, 0, "/dev/null", os.O_RDONLY, 0)]
                actions.extend((os.POSIX_SPAWN_DUP2, handle.fileno(), fd)
                               for fd, handle in enumerate(sources, 1))
                actions.extend(_close_actions())
                pid = os.posix_spawn(image, [os.fspath(image), *arguments], os.environ,
                                     file_actions=actions, setsigmask=original_mask)
                for child in sources:
                    child.close()
            with selectors.DefaultSelector() as poll:
                for fd in (1, 2, 3, 5):
                    stream = channels[fd]
                    os.set_blocking(stream.fileno(), False)
                    poll.register(stream, selectors.EVENT_READ, fd)

                def read_channel(fd):
                    stream = channels[fd]
                    if stream.closed:
                        return None
                    try:
                        data = os.read(stream.fileno(), 4096)
                    except BlockingIOError:
                        return None
                    if not data:
                        poll.unregister(stream)
                        stream.close()
                        if fd == 3:
                            events.eof = True
                            events.commit(status)
                    return data

                def drain_application(fd):
                    data = read_channel(fd)
                    if data:
                        application("stdout" if fd == 1 else "stderr", data)
                    return bool(data)

                while poll.get_map() or pid is not None:
                    if pid is not None:
                        with _defer_interrupts():
                            waited, raw = os.waitpid(pid, os.WNOHANG)
                            if waited:
                                pid = None
                                status = os.waitstatus_to_exitcode(raw)
                    events.commit(status)
                    if not poll.get_map() and pid is None:
                        break
                    ready = {key.data for key, mask in poll.select(0.02)}
                    if 3 in ready:
                        data = read_channel(3)
                        if data:
                            events.feed(data)
                    if events.ready and outcome.state == "not_run" and pid is not None and not events.eof:
                        with _defer_interrupts():
                            if os.write(channels[4].fileno(), b"\x01") != 1:
                                raise OSError("Cannot delegate test execution")
                            outcome.state = "running"
                        channels[4].close()
                    for fd in (1, 2):
                        if fd in ready:
                            drain_application(fd)
                    if 5 in ready:
                        data = read_channel(5)
                        if data:
                            # The runtime starts writing diagnostics after all application
                            # writes. Drain bytes already accepted by either pipe first.
                            for fd in (1, 2):
                                while drain_application(fd):
                                    pass
                            diagnostic(data)
                events.commit(status)
        finally:
            with _defer_interrupts():
                try:
                    if pid is not None:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        os.waitpid(pid, 0)
                finally:
                    outcome.abort()
