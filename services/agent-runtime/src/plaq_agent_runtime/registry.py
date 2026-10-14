"""Typed Tool Registry enforcing 6 permission tiers, parameter validation, secret scrubbing, and audit logging."""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from pydantic import BaseModel, ValidationError

from plaq_contracts.common import PlaqBaseModel
from plaq_contracts.tool import (
    DEFAULT_TOOL_TIERS,
    PermissionTier,
    ToolDefinition,
    ToolRequest,
    ToolResult,
)
from plaq_control_plane.redact import SecretRedactor
from plaq_sandbox.guard import PathTraversalError

from plaq_agent_runtime.tools.workspace_tools import (
    WorkspaceListParams,
    WorkspacePatchParams,
    WorkspaceReadParams,
    WorkspaceWriteParams,
    workspace_list,
    workspace_patch,
    workspace_read,
    workspace_write,
)
from plaq_agent_runtime.tools.git_tools import (
    GitBranchParams,
    GitDiffParams,
    git_branch,
    git_diff,
)
from plaq_agent_runtime.tools.terminal_tools import (
    TerminalRunParams,
    TestsRunParams,
    terminal_run,
    tests_run,
)
from plaq_agent_runtime.tools.quantum_tools import (
    QuantumCompileParams,
    QuantumEstimateParams,
    QuantumSimulateParams,
    quantum_compile,
    quantum_estimate,
    quantum_simulate,
)
from plaq_agent_runtime.tools.artifact_tools import (
    ArtifactPublishParams,
    artifacts_publish,
)


@dataclass
class ToolContext:
    """Execution context provided to tool handlers."""
    workspace_path: Path
    task_id: str
    step_id: Optional[str] = None
    sandbox_manager: Optional[Any] = None
    artifact_service: Optional[Any] = None
    control_plane: Optional[Any] = None
    allowed_tiers: Optional[Set[Union[PermissionTier, str]]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolEntry:
    """Registered tool entry with metadata and invocation handler."""
    definition: ToolDefinition
    handler: Callable[[Any, ToolContext], ToolResult]
    param_model: Optional[Type[BaseModel]] = None


class ToolRegistry:
    """Central typed tool registry enforcing permission tiers, validation, and audit trail logging."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolEntry] = {}

    def register(
        self,
        definition: ToolDefinition,
        handler: Callable[[Any, ToolContext], ToolResult],
        param_model: Optional[Type[BaseModel]] = None,
    ) -> None:
        """Register a tool with its schema definition and execution handler."""
        self._tools[definition.name] = ToolEntry(
            definition=definition,
            handler=handler,
            param_model=param_model,
        )

    def register_decorator(
        self,
        name: str,
        tier: Union[PermissionTier, str],
        description: str = "",
        requires_approval: bool = False,
        timeout_sec: float = 30.0,
        param_model: Optional[Type[BaseModel]] = None,
    ) -> Callable[[Callable], Callable]:
        """Decorator for registering a tool function."""
        tier_enum = PermissionTier(tier) if isinstance(tier, str) else tier

        def decorator(fn: Callable) -> Callable:
            schema = param_model.model_json_schema() if param_model else {}
            definition = ToolDefinition(
                name=name,
                description=description or (fn.__doc__ or ""),
                tier=tier_enum,
                parameters_schema=schema,
                requires_approval=requires_approval,
                timeout_sec=timeout_sec,
            )
            self.register(definition, fn, param_model)
            return fn

        return decorator

    def get_tool(self, name: str) -> Optional[ToolEntry]:
        """Retrieve tool entry by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        """List definitions of all registered tools."""
        return [entry.definition for entry in self._tools.values()]

    def get_tier_map(self) -> Dict[str, str]:
        """Return map of tool names to their string permission tiers."""
        return {
            name: entry.definition.tier.value if hasattr(entry.definition.tier, "value") else str(entry.definition.tier)
            for name, entry in self._tools.items()
        }

    def execute(self, request: ToolRequest, context: ToolContext) -> ToolResult:
        """Validate, authorize, execute, scrub, and audit log a tool invocation."""
        t0 = time.perf_counter()
        tool_entry = self._tools.get(request.tool_name)
        if not tool_entry:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool not found: '{request.tool_name}'",
                duration_ms=0.0,
                exit_code=1,
                modified_files=[],
            )

        # 1. Permission Tier Enforcement
        if context.allowed_tiers is not None:
            allowed_values = {
                t.value if hasattr(t, "value") else str(t)
                for t in context.allowed_tiers
            }
            tool_tier_val = (
                tool_entry.definition.tier.value
                if hasattr(tool_entry.definition.tier, "value")
                else str(tool_entry.definition.tier)
            )
            if tool_tier_val not in allowed_values:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Permission denied: Tool '{request.tool_name}' requires tier '{tool_tier_val}', but allowed tiers are {sorted(allowed_values)}",
                    duration_ms=0.0,
                    exit_code=1,
                    modified_files=[],
                )

        # 2. Parameter Validation
        if isinstance(request.parameters, dict):
            parsed_params = dict(request.parameters)
        elif isinstance(request.parameters, str):
            parsed_params = ToolRequest.parse_params(request.parameters)
        else:
            parsed_params = {}
        if tool_entry.param_model:
            try:
                validated_params = tool_entry.param_model(**parsed_params)
            except ValidationError as val_err:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Parameter validation failed for tool '{request.tool_name}': {val_err}",
                    duration_ms=0.0,
                    exit_code=1,
                    modified_files=[],
                )
        else:
            validated_params = parsed_params

        # 3. Execution with Exception Safety
        try:
            result = tool_entry.handler(validated_params, context)
            if not isinstance(result, ToolResult):
                result = ToolResult(
                    success=True,
                    output=str(result),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    exit_code=0,
                    modified_files=[],
                )
        except PathTraversalError as pte:
            result = ToolResult(
                success=False,
                output="",
                error=f"Path traversal detected: {pte}",
                duration_ms=(time.perf_counter() - t0) * 1000,
                exit_code=1,
                modified_files=[],
            )
        except subprocess.TimeoutExpired as te:
            result = ToolResult(
                success=False,
                output="",
                error=f"Execution timed out after {te.timeout}s",
                duration_ms=(time.perf_counter() - t0) * 1000,
                exit_code=-1,
                modified_files=[],
            )
        except Exception as exc:
            result = ToolResult(
                success=False,
                output="",
                error=f"Tool '{request.tool_name}' failed with error: {exc}",
                duration_ms=(time.perf_counter() - t0) * 1000,
                exit_code=1,
                modified_files=[],
            )

        duration_ms = (time.perf_counter() - t0) * 1000
        if result.duration_ms <= 0:
            result.duration_ms = duration_ms

        # 4. Secret Scrubbing & Audit Logging
        redacted_params = SecretRedactor.redact_json(parsed_params)
        redacted_output = SecretRedactor.redact_text(result.output or "")

        if context.control_plane is not None and hasattr(context.control_plane, "record_audit"):
            try:
                context.control_plane.record_audit(
                    task_id=context.task_id,
                    tool_name=request.tool_name,
                    parameters=redacted_params,
                    output=redacted_output,
                    exit_code=result.exit_code if result.exit_code is not None else (0 if result.success else 1),
                    duration_ms=result.duration_ms,
                    modified_files=result.modified_files,
                )
            except Exception:
                pass

        return result


def create_default_tool_registry() -> ToolRegistry:
    """Instantiate and populate ToolRegistry with all 12 standard Plaq-OS tools."""
    registry = ToolRegistry()

    # 1. Read-Only Tier
    registry.register(
        ToolDefinition(
            name="workspace.list",
            description="List directory files and folders safely within workspace.",
            tier=PermissionTier.READ_ONLY,
            parameters_schema=WorkspaceListParams.model_json_schema(),
            timeout_sec=10.0,
        ),
        workspace_list,
        WorkspaceListParams,
    )
    registry.register(
        ToolDefinition(
            name="workspace.read",
            description="Read file content safely within workspace.",
            tier=PermissionTier.READ_ONLY,
            parameters_schema=WorkspaceReadParams.model_json_schema(),
            timeout_sec=15.0,
        ),
        workspace_read,
        WorkspaceReadParams,
    )

    # 2. Workspace Write Tier
    registry.register(
        ToolDefinition(
            name="workspace.write",
            description="Write or overwrite file safely within workspace.",
            tier=PermissionTier.WORKSPACE_WRITE,
            parameters_schema=WorkspaceWriteParams.model_json_schema(),
            timeout_sec=15.0,
        ),
        workspace_write,
        WorkspaceWriteParams,
    )
    registry.register(
        ToolDefinition(
            name="workspace.patch",
            description="Apply substring or unified diff patch safely within workspace.",
            tier=PermissionTier.WORKSPACE_WRITE,
            parameters_schema=WorkspacePatchParams.model_json_schema(),
            timeout_sec=15.0,
        ),
        workspace_patch,
        WorkspacePatchParams,
    )

    # 3. Git Isolated Tier
    registry.register(
        ToolDefinition(
            name="git.diff",
            description="Run git diff in repository or isolated worktree.",
            tier=PermissionTier.GIT_ISOLATED,
            parameters_schema=GitDiffParams.model_json_schema(),
            timeout_sec=15.0,
        ),
        git_diff,
        GitDiffParams,
    )
    registry.register(
        ToolDefinition(
            name="git.branch",
            description="List, show current, or create git branch in worktree.",
            tier=PermissionTier.GIT_ISOLATED,
            parameters_schema=GitBranchParams.model_json_schema(),
            timeout_sec=15.0,
        ),
        git_branch,
        GitBranchParams,
    )

    # 4. Process Sandbox Tier
    registry.register(
        ToolDefinition(
            name="terminal.run",
            description="Execute shell command inside isolated subprocess sandbox.",
            tier=PermissionTier.PROCESS_SANDBOX,
            parameters_schema=TerminalRunParams.model_json_schema(),
            timeout_sec=30.0,
        ),
        terminal_run,
        TerminalRunParams,
    )
    registry.register(
        ToolDefinition(
            name="tests.run",
            description="Run pytest suite inside isolated subprocess sandbox.",
            tier=PermissionTier.PROCESS_SANDBOX,
            parameters_schema=TestsRunParams.model_json_schema(),
            timeout_sec=60.0,
        ),
        tests_run,
        TestsRunParams,
    )

    # 5. Quantum Engine Tier
    registry.register(
        ToolDefinition(
            name="quantum.compile",
            description="Synthesize quantum circuit and decompose single-qubit rotations into T-gates.",
            tier=PermissionTier.QUANTUM_ENGINE,
            parameters_schema=QuantumCompileParams.model_json_schema(),
            timeout_sec=60.0,
        ),
        quantum_compile,
        QuantumCompileParams,
    )
    registry.register(
        ToolDefinition(
            name="quantum.estimate",
            description="Evaluate fault-tolerant resource requirements and solve surface code distance.",
            tier=PermissionTier.QUANTUM_ENGINE,
            parameters_schema=QuantumEstimateParams.model_json_schema(),
            timeout_sec=30.0,
        ),
        quantum_estimate,
        QuantumEstimateParams,
    )
    registry.register(
        ToolDefinition(
            name="quantum.simulate",
            description="Simulate rotated surface code stabilizer syndrome measurements and MWPM decoding.",
            tier=PermissionTier.QUANTUM_ENGINE,
            parameters_schema=QuantumSimulateParams.model_json_schema(),
            timeout_sec=120.0,
        ),
        quantum_simulate,
        QuantumSimulateParams,
    )

    # 6. Privileged Tier
    registry.register(
        ToolDefinition(
            name="artifacts.publish",
            description="Publish verified report or dataset to content-addressable storage.",
            tier=PermissionTier.PRIVILEGED,
            parameters_schema=ArtifactPublishParams.model_json_schema(),
            requires_approval=False,
            timeout_sec=30.0,
        ),
        artifacts_publish,
        ArtifactPublishParams,
    )

    return registry
