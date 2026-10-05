"""Tell the CIRIS node this agent starts what kind of device it runs on.

From ciris-server 0.5.220 (persist v53, S1, CC 3.3.7) replication of a person's
SELF and FAMILY content follows each node's device class, and a ``server``-class
node no longer receives it. The server resolves the class as: a valid
``CIRIS_DEVICE_CLASS`` -> an Android/iOS build is ``phone`` -> otherwise
``server``. So a person's own desktop running the agent must say ``laptop``, or it
stops receiving that person's notes and self files.

The node runs in (or is spawned from) the agent's process, so the agent declares
the class in its own environment before the node starts:

* ``laptop`` -- the ``ciris-agent`` desktop install (with or without AI);
* ``server`` -- headless / hosted (``--server``, ``ciris-server``, ``main.py`` in a
  container);
* nothing on Android/iOS -- the server already resolves those builds to ``phone``.

An existing value always wins: the client's own desktop spawn sets ``laptop``
(CIRISClient#153) and an operator may set it explicitly. The agent's own key keeps
its ``agent`` class; that is a different key and is not affected here.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Optional

from ciris_engine.logic.utils.path_resolution import is_android, is_ios

logger = logging.getLogger(__name__)

DEVICE_CLASS_ENV = "CIRIS_DEVICE_CLASS"


class HostDeviceClass(str, Enum):
    """The device classes the agent itself declares for the node it starts."""

    LAPTOP = "laptop"
    SERVER = "server"


def declare_device_class(default: HostDeviceClass) -> Optional[str]:
    """Set ``CIRIS_DEVICE_CLASS`` for the node this process starts, unless already decided.

    Returns the class now in effect, or None when the server is left to resolve it
    (Android/iOS builds, which it resolves to ``phone``).
    """
    existing = (os.environ.get(DEVICE_CLASS_ENV) or "").strip()
    if existing:
        return existing
    if is_android() or is_ios():
        return None
    os.environ[DEVICE_CLASS_ENV] = default.value
    logger.info("Node device class: %s=%s (declared by the agent)", DEVICE_CLASS_ENV, default.value)
    return default.value
