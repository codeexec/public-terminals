"""
Application constants and enums
"""

from enum import Enum


class SandboxStatus(str, Enum):
    """Sandbox status enumeration"""

    PENDING = "PENDING"
    STARTING = "STARTING"
    STARTED = "STARTED"
    STOPPED = "STOPPED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class SandboxType(str, Enum):
    """Sandbox type enumeration"""

    TERMINAL = "TERMINAL"
    JUPYTERLITE = "JUPYTERLITE"


# Common Labels
LABEL_APP = "sandbox-server"
LABEL_SANDBOX_ID = "sandbox_id"
LABEL_SANDBOX_TYPE = "sandbox_type"
