from enum import Enum


class ToolState(Enum):
    """Status of a background tool."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SystemTool(Enum):
    """System tools are tools that are used to manage the background tool manager."""

    TASK_STATUS = "task_status"
    TASK_CANCEL = "task_cancel"


# Call-id prefix for detached background work spawned by a tool (not by a model
# function call). Results with this prefix must never be sent back as
# function_call_output; the realtime handler announces them via a plain message.
DETACHED_CALL_ID_PREFIX = "detached::"
