"""A non-blocking file lock that works on Linux, macOS and Windows."""

from pathlib import Path


def acquire(path):
    """Take the lock, or return None if another process holds it.

    The mechanisms differ per system. If neither is available we carry on
    without a lock: doing something twice is untidy, refusing to do it at all
    would be worse.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(str(path), "a+")
    except Exception:
        return None

    try:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except ImportError:
        pass
    except Exception:
        handle.close()
        return None

    try:
        import msvcrt
    except ImportError:
        return handle

    try:
        # locking() locks one byte. A fresh empty file has none, so one is
        # written first.
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write("x")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except OSError:
        handle.close()
        return None
    except Exception:
        return handle


def release(handle):
    if handle is None:
        return
    try:
        handle.close()
    except Exception:
        pass
