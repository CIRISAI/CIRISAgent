"""Out-of-band activation hook for the CIRIS in-process memory probe.

`site` imports any module named `sitecustomize` it finds on `sys.path`, before
application code runs.  Putting *this directory* on PYTHONPATH is therefore the
whole activation mechanism -- nothing in the shipped engine imports the probe,
and an unset CIRIS_MEMPROBE makes this file a no-op:

    PYTHONPATH=tools/memprobe CIRIS_MEMPROBE=1 python main.py --adapter api

The directory deliberately has no __init__.py: it is a path entry, not a package.
"""

import os

if os.environ.get("CIRIS_MEMPROBE"):
    try:
        import ciris_memprobe

        ciris_memprobe.install()
    except Exception as exc:  # never break the process we are measuring
        import sys

        print(f"[memprobe] install failed: {exc}", file=sys.stderr)
