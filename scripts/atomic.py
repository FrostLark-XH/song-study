#!/usr/bin/env python3
"""Atomic file output: write to a temp file in the target directory, then swap.

Failure keeps the previous file intact — a half-written output never replaces a
good one. All three generators (md/docx/pptx) and build_all route through here.
"""

import os
import tempfile


def atomic_replace(path: str, write_fn) -> None:
    """Write content via ``write_fn(tmp_path)``, then atomically swap into place.

    ``write_fn`` receives a temp path in the same directory (so ``os.replace``
    is an atomic rename on the same filesystem) and writes the full content. On
    any error the temp file is removed and the previous target, if present, is
    left untouched.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_",
                               suffix=os.path.splitext(path)[1])
    os.close(fd)
    try:
        write_fn(tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
