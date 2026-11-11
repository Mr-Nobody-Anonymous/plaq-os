"""Plaq-OS Agent Runtime, 7-Stage Execution Loop, Tool Registry & Human Approval Gates."""

from plaq_agent_runtime.approvals import ApprovalManager
from plaq_agent_runtime.loop import AgentRuntime, TaskResult
from plaq_agent_runtime.queue import BackgroundTaskQueue, get_queue
from plaq_agent_runtime.registry import (
    ToolContext,
    ToolEntry,
    ToolRegistry,
    create_default_tool_registry,
)

__version__ = "0.3.0"

__all__ = [
    "AgentRuntime",
    "TaskResult",
    "ApprovalManager",
    "ToolRegistry",
    "ToolContext",
    "ToolEntry",
    "create_default_tool_registry",
    "BackgroundTaskQueue",
    "get_queue",
]
