"""Check the compiler's ordered suite metadata before assigning child ordinals."""
from pathlib import PurePosixPath

from ..runner.suite import Case, Span
from .client import WorkerError, decimal


def span(path, values):
    if not path or "\0" in path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
        raise WorkerError("Invalid source path in test plan")
    start, end, line, column = (decimal(value, 999999999) for value in values)
    if start >= end or line == 0 or column == 0:
        raise WorkerError("Invalid source span in test plan")
    return Span(path, line, column, start, end)


def cases_from(fields):
    _, count, site_count = fields[:3]
    count, site_count = decimal(count, 9999999), decimal(site_count, 9999999)
    if len(fields) != 3 + 8 * count + 5 * site_count:
        raise WorkerError("Incomplete test metadata")
    first_site = 3 + 8 * count
    sites = tuple(span(fields[i], fields[i + 1:i + 5]) for i in range(first_site, len(fields), 5))
    cases = []
    previous = None
    for i in range(3, first_site, 8):
        ordinal, path, namespace, name = fields[i:i + 4]
        declaration = span(path, fields[i + 4:i + 8])
        order = (path.encode(), declaration.start)
        if ordinal != str(len(cases)) or not namespace or not name or (previous is not None and previous >= order):
            raise WorkerError("Invalid test identity or ordering")
        previous = order
        cases.append(Case(f"{path}::{namespace}::{name}", declaration, sites))
    return cases
