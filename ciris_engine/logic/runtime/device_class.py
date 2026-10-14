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
from ciris_engine.schemas.services.resources_core import DeviceClass

logger = logging.getLogger(__name__)

DEVICE_CLASS_ENV = "CIRIS_DEVICE_CLASS"


class HostDeviceClass(str, Enum):
    """The device classes the agent itself declares for the node it starts."""

    LAPTOP = "laptop"
    SERVER = "server"


def resolve_device_class() -> DeviceClass:
    """The device class this runtime is on, resolved the way the node resolves it.

    Android/iOS builds are ``phone``; otherwise a valid ``CIRIS_DEVICE_CLASS``
    (which ``declare_device_class`` sets before the runtime starts); otherwise
    ``server``. Used to pick the device-sized resource budget.
    """
    if is_android() or is_ios():
        return DeviceClass.PHONE
    declared = (os.environ.get(DEVICE_CLASS_ENV) or "").strip().lower()
    try:
        return DeviceClass(declared)
    except ValueError:
        return DeviceClass.SERVER


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


def agent_owns_process() -> bool:
    """True only when this process is the agent's own to end (CIRISAgent#1240).

    The agent may end its process only as a headless server under a supervisor
    (``ciris-server`` / ``main.py`` in a container or under systemd), where
    exiting is how the supervisor learns the agent stopped. Everywhere else the
    process belongs to someone else and must outlive a shutdown:

    * Android (Chaquopy) and iOS (BeeWare): the agent is a thread of the host app;
      ending the process is the user's app vanishing, and the host cannot restart
      the interpreter;
    * the desktop install (``laptop`` class: ``ciris-agent`` or the client's own
      spawn, CIRISClient#153), whose process also carries the folded node (4243)
      the client talks to.

    **Fails closed**: ``platform_detection.is_desktop()`` is a positive allow-list
    (an unrecognised platform is not desktop) and only an explicit or defaulted
    ``server`` device class counts, so anything uncertain gets the embedded answer
    -- stop the runtime and :8080, and return.
    """
    from ciris_engine.logic.utils.platform_detection import is_desktop

    if not is_desktop():
        return False
    return resolve_device_class() == DeviceClass.SERVER
