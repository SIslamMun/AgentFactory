"""Custom exception hierarchy for AgentFactory."""


class IOWarpError(Exception):
    """Base exception for all IOWarp-related errors."""


class BridgeConnectionError(IOWarpError):
    """Failed to connect to or communicate with the ZeroMQ bridge."""


class CacheError(IOWarpError):
    """Error interacting with the memcached cache layer."""


class URIResolveError(IOWarpError):
    """Failed to resolve a URI scheme (mem::, folder::, etc.)."""


class BlueprintError(IOWarpError):
    """Error loading or validating an agent blueprint."""


class PipelineError(IOWarpError):
    """Error in pipeline definition, validation, or execution."""
