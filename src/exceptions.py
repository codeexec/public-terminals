"""
Custom application exceptions
"""

class SandboxError(Exception):
    """Base exception for all sandbox-related errors"""
    pass


class ContainerError(SandboxError):
    """Base exception for container-related errors"""
    pass


class ContainerCreationError(ContainerError):
    """Raised when container creation fails"""
    pass


class ContainerDeletionError(ContainerError):
    """Raised when container deletion fails"""
    pass


class ContainerStatusError(ContainerError):
    """Raised when container status retrieval fails"""
    pass


class DatabaseError(SandboxError):
    """Base exception for database-related errors"""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails"""
    pass


class ConfigurationError(SandboxError):
    """Raised when application configuration is invalid"""
    pass


class AuthenticationError(SandboxError):
    """Raised when authentication fails"""
    pass


class SandboxNotFoundError(SandboxError):
    """Raised when a sandbox is not found"""
    pass


class SandboxLimitReachedError(SandboxError):
    """Raised when maximum sandbox limit is reached"""
    pass
