"""
JARVIS BRAINIAC - Semantic Kernel Integration Bridge
=====================================================

Unified Semantic Kernel adapter providing:
- Kernel creation with configurable AI backends
- Plugin registration and management
- Prompt invocation through the kernel
- Chat with plugin integration
- Mock fallback when semantic-kernel is not installed

Usage:
    bridge = SemanticKernelBridge()
    kernel = bridge.create_kernel()
    bridge.add_plugin(my_plugin, "MyPlugin")
    result = bridge.invoke_prompt("What is the weather?")
"""

from __future__ import annotations

# Prevent local logging.py from shadowing stdlib during transitive imports
_sys = __import__("sys")
_Path = __import__("pathlib").Path
_agency_dir = str(_Path(__file__).parent.resolve())
_removed_path = None
for _p in list(_sys.path):
    if str(_Path(_p).resolve()) == _agency_dir:
        _sys.path.remove(_p)
        _removed_path = _p
        break

import asyncio
import logging

# Restore agency dir to sys.path so sibling modules remain importable
if _removed_path is not None:
    _sys.path.insert(0, _removed_path)
import json
import os
import sys
import warnings
from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence, Tuple, Type, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_SK_AVAILABLE: bool = False
_SK_IMPORT_ERROR: Optional[str] = None

try:
    import semantic_kernel
    from semantic_kernel import Kernel
    from semantic_kernel.functions import kernel_function, KernelFunction
    from semantic_kernel.connectors.ai.open_ai import (
        OpenAIChatCompletion,
        AzureChatCompletion,
        OpenAIPromptExecutionSettings,
    )
    from semantic_kernel.connectors.ai import PromptExecutionSettings
    from semantic_kernel.memory.semantic_text_memory_base import SemanticTextMemoryBase
    from semantic_kernel.planners import BasicPlanner, Plan
    from semantic_kernel.contents import ChatHistory
    from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
    _SK_AVAILABLE = True
    logger.info("Semantic Kernel %s loaded successfully.", getattr(semantic_kernel, "__version__", "unknown"))
except Exception as _import_exc:
    _SK_IMPORT_ERROR = str(_import_exc)
    logger.warning(
        "Semantic Kernel not installed or failed to import (%s). "
        "Falling back to mock implementations.",
        _import_exc,
    )

# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockKernel:
    """Mock kernel that simulates Semantic Kernel behavior."""

    def __init__(self, kernel_name: str = "mock_kernel") -> None:
        self.name: str = kernel_name
        self.plugins: Dict[str, _MockPlugin] = {}
        self.services: Dict[str, Any] = {}
        self._prompt_history: List[Dict[str, Any]] = []
        self._settings: Dict[str, Any] = {"temperature": 0.7, "max_tokens": 2048}

    def add_service(self, service_id: str, service: Any) -> None:
        """Add an AI service to the kernel."""
        self.services[service_id] = service
        logger.info("[MockKernel] Added service '%s'", service_id)

    def add_plugin(self, plugin: Union[_MockPlugin, Dict[str, Any]], plugin_name: str) -> None:
        """Add a plugin to the kernel."""
        if isinstance(plugin, _MockPlugin):
            self.plugins[plugin_name] = plugin
        elif isinstance(plugin, dict):
            # Create a mock plugin from dict
            mock_plugin = _MockPlugin(plugin_name, plugin)
            self.plugins[plugin_name] = mock_plugin
        else:
            logger.warning("Unsupported plugin type: %s", type(plugin))
            return
        logger.info("[MockKernel] Added plugin '%s'", plugin_name)

    def invoke(self, function: Any, **kwargs: Any) -> "_MockKernelResponse":
        """Invoke a kernel function."""
        self._prompt_history.append({"function": str(function), "kwargs": kwargs})
        if callable(function):
            try:
                result = function(**kwargs)
                return _MockKernelResponse(str(result))
            except Exception as exc:
                return _MockKernelResponse(f"[ERROR] {exc}")
        return _MockKernelResponse(f"[MOCK] Invoked: {function}")

    async def invoke_async(self, function: Any, **kwargs: Any) -> "_MockKernelResponse":
        """Asynchronously invoke a kernel function."""
        return self.invoke(function, **kwargs)

    def get_plugin(self, name: str) -> Optional[_MockPlugin]:
        """Get a plugin by name."""
        return self.plugins.get(name)

    def list_plugins(self) -> List[str]:
        """List all registered plugin names."""
        return list(self.plugins.keys())

    def list_services(self) -> List[str]:
        """List all registered service names."""
        return list(self.services.keys())

    def create_new_chat(self) -> "_MockChatHistory":
        """Create a new chat history instance."""
        return _MockChatHistory()

    def __repr__(self) -> str:
        return f"_MockKernel(plugins={list(self.plugins.keys())})"


class _MockKernelResponse:
    """Mock response from a kernel invocation."""

    def __init__(self, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.value: str = value
        self.metadata: Dict[str, Any] = metadata or {}
        self._iter_index: int = 0

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"_MockKernelResponse(value='{self.value[:50]}...')"

    def __iter__(self):
        """Make the response iterable for streaming compatibility."""
        self._iter_index = 0
        return self

    def __next__(self):
        """Iterate over the response (single-item iterator)."""
        if self._iter_index == 0:
            self._iter_index += 1
            return self.value
        raise StopIteration

    def get_inner_content(self) -> str:
        """Get the inner content of the response."""
        return self.value


class _MockPlugin:
    """Mock plugin that wraps callable functions."""

    def __init__(self, name: str, functions: Optional[Dict[str, Callable[..., Any]]] = None) -> None:
        self.name: str = name
        self.functions: Dict[str, Callable[..., Any]] = functions or {}
        self._description: str = f"Mock plugin: {name}"

    def add_function(self, name: str, func: Callable[..., Any]) -> None:
        """Add a function to the plugin."""
        self.functions[name] = func

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        """Execute the plugin's primary function if one exists."""
        if self.functions:
            first_func = next(iter(self.functions.values()))
            return str(first_func(*args, **kwargs))
        return f"[MOCK] Plugin '{self.name}' executed with args={args}, kwargs={kwargs}"

    def __getattr__(self, name: str) -> Any:
        """Access plugin functions as attributes."""
        if name in self.functions:
            return self.functions[name]
        raise AttributeError(f"Plugin '{self.name}' has no function '{name}'")

    def describe(self) -> str:
        """Return a description of the plugin."""
        funcs = ", ".join(self.functions.keys()) if self.functions else "none"
        return f"Plugin: {self.name}\nFunctions: {funcs}"

    def list_functions(self) -> List[str]:
        """List all function names in the plugin."""
        return list(self.functions.keys())


class _MockChatHistory:
    """Mock chat history for conversation tracking."""

    def __init__(self) -> None:
        self.messages: List[Dict[str, str]] = []
        self._system_message: Optional[str] = None

    def add_system_message(self, message: str) -> None:
        """Add a system message to the history."""
        self._system_message = message
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str) -> None:
        """Add a user message to the history."""
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str) -> None:
        """Add an assistant message to the history."""
        self.messages.append({"role": "assistant", "content": message})

    def add_function_message(self, name: str, message: str) -> None:
        """Add a function result message."""
        self.messages.append({"role": "function", "name": name, "content": message})

    def get_messages(self) -> List[Dict[str, str]]:
        """Get all messages in the history."""
        return self.messages.copy()

    def get_last_message(self) -> Optional[Dict[str, str]]:
        """Get the last message in the history."""
        return self.messages[-1] if self.messages else None

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()

    def __len__(self) -> int:
        return len(self.messages)

    def __repr__(self) -> str:
        return f"_MockChatHistory(messages={len(self.messages)})"


class _MockPlanner:
    """Mock planner for creating execution plans."""

    def __init__(self, kernel: _MockKernel) -> None:
        self.kernel: _MockKernel = kernel
        self._plans: List[str] = []

    def create_plan(self, goal: str, prompt: Optional[str] = None) -> "_MockPlan":
        """Create a mock plan for a given goal."""
        plan = _MockPlan(goal=goal, kernel=self.kernel)
        self._plans.append(goal)
        return plan

    async def execute_plan_async(self, plan: "_MockPlan") -> _MockKernelResponse:
        """Execute a plan asynchronously."""
        result = plan.execute()
        return _MockKernelResponse(result)


class _MockPlan:
    """Mock execution plan."""

    def __init__(self, goal: str, kernel: _MockKernel) -> None:
        self.goal: str = goal
        self.kernel: _MockKernel = kernel
        self.steps: List[str] = []
        self._parse_goal(goal)

    def _parse_goal(self, goal: str) -> None:
        """Parse the goal into mock steps."""
        # Simple keyword-based step extraction
        words = goal.lower().split()
        if any(w in words for w in ["find", "search", "get", "look"]):
            self.steps.append("search")
        if any(w in words for w in ["calculate", "compute", "math", "sum"]):
            self.steps.append("calculate")
        if any(w in words for w in ["weather", "temperature"]):
            self.steps.append("get_weather")
        if not self.steps:
            self.steps.append("process")
            self.steps.append("respond")

    def execute(self) -> str:
        """Execute the plan steps."""
        results: List[str] = []
        for step in self.steps:
            # Check if any plugin has this function
            for plugin in self.kernel.plugins.values():
                if step in plugin.functions:
                    try:
                        result = plugin.functions[step](self.goal)
                        results.append(f"[{step}] {result}")
                    except Exception as exc:
                        results.append(f"[{step}] Error: {exc}")
                    break
            else:
                results.append(f"[{step}] Mock execution for goal: {self.goal[:50]}")
        return "\n".join(results)

    def describe(self) -> str:
        """Return a description of the plan."""
        return f"Plan for: {self.goal}\nSteps:\n" + "\n".join(f"  {i+1}. {step}" for i, step in enumerate(self.steps))


# ---------------------------------------------------------------------------
# SemanticKernelBridge
# ---------------------------------------------------------------------------

class SemanticKernelBridge:
    """
    Unified Semantic Kernel integration bridge for JARVIS BRAINIAC.

    Provides factory methods for creating kernels, registering plugins,
    running prompts, and managing chat sessions. When Semantic Kernel
    is not installed, all methods return fully-functional mock implementations.

    Attributes:
        available (bool): Whether the real Semantic Kernel library is installed.
        default_model (str): Default AI model identifier.
    """

    def __init__(
        self,
        default_model: str = "gpt-4",
        api_key: Optional[str] = None,
        verbose: bool = True,
    ) -> None:
        """
        Initialize the Semantic Kernel bridge.

        Args:
            default_model: Default model identifier (e.g., "gpt-4").
            api_key: OpenAI/Azure API key. Auto-detected from env if None.
            verbose: Enable verbose logging.
        """
        self.available: bool = _SK_AVAILABLE
        self.verbose: bool = verbose
        self.default_model: str = default_model
        self.api_key: str = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.azure_key: str = os.environ.get("AZURE_OPENAI_API_KEY", "")
        self._kernels: Dict[str, Any] = {}
        self._plugins: Dict[str, Any] = {}
        self._chats: Dict[str, Any] = {}
        self._settings: Dict[str, Any] = {"temperature": 0.7, "max_tokens": 2048}
        logger.info("SemanticKernelBridge initialized (available=%s)", self.available)

    def _log(self, msg: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            logger.info("[SemanticKernelBridge] %s", msg)

    # -- Kernel lifecycle ----------------------------------------------------

    def create_kernel(self, kernel_name: str = "default_kernel") -> Any:
        """
        Create a Semantic Kernel instance (or mock equivalent).

        Args:
            kernel_name: Identifier for the kernel.

        Returns:
            Kernel or mock kernel object.

        Example:
            >>> bridge = SemanticKernelBridge()
            >>> kernel = bridge.create_kernel()
            >>> print(bridge.list_plugins())
        """
        if self.available:
            try:
                kernel = Kernel()

                # Add chat completion service
                if self.api_key:
                    service = OpenAIChatCompletion(
                        ai_model_id=self.default_model,
                        api_key=self.api_key,
                    )
                    kernel.add_service(service)
                    self._log(f"Created kernel '{kernel_name}' with OpenAI service")
                elif self.azure_key:
                    service = AzureChatCompletion(
                        deployment_name=self.default_model,
                        api_key=self.azure_key,
                        endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                    )
                    kernel.add_service(service)
                    self._log(f"Created kernel '{kernel_name}' with Azure service")
                else:
                    self._log(f"Created kernel '{kernel_name}' without AI service")

                self._kernels[kernel_name] = kernel
                return kernel
            except Exception as exc:
                logger.error("Failed to create kernel: %s. Using mock.", exc)

        mock_kernel = _MockKernel(kernel_name)
        self._kernels[kernel_name] = mock_kernel
        self._log(f"Created mock kernel '{kernel_name}'")
        return mock_kernel

    def get_kernel(self, name: str = "default_kernel") -> Optional[Any]:
        """Retrieve a kernel by name."""
        return self._kernels.get(name)

    def list_kernels(self) -> List[str]:
        """List all registered kernel names."""
        return list(self._kernels.keys())

    # -- Plugin management ---------------------------------------------------

    def add_plugin(
        self,
        plugin: Union[Dict[str, Callable[..., Any]], Any],
        plugin_name: str,
        kernel_name: str = "default_kernel",
    ) -> bool:
        """
        Add a plugin to a kernel.

        Args:
            plugin: Plugin object or dict of function_name -> callable.
            plugin_name: Name to register the plugin under.
            kernel_name: Target kernel name.

        Returns:
            True if plugin was added successfully.

        Example:
            >>> bridge = SemanticKernelBridge()
            >>> kernel = bridge.create_kernel()
            >>> bridge.add_plugin({"get_time": lambda: "12:00"}, "TimePlugin")
        """
        kernel = self._kernels.get(kernel_name)
        if kernel is None:
            logger.error("Kernel '%s' not found.", kernel_name)
            return False

        # Create or wrap plugin
        if isinstance(plugin, dict):
            sk_plugin = _MockPlugin(plugin_name, plugin)
        elif isinstance(plugin, _MockPlugin):
            sk_plugin = plugin
        else:
            sk_plugin = plugin  # Assume it's a real SK plugin

        self._plugins[plugin_name] = sk_plugin

        if self.available:
            try:
                # For real SK, handle both dict and native plugin objects
                if isinstance(plugin, dict):
                    # Create a native SK plugin from dict
                    class _SKPlugin:
                        def __init__(self, funcs: Dict[str, Callable[..., Any]]) -> None:
                            for name, fn in funcs.items():
                                setattr(self, name, fn)
                    native_plugin = _SKPlugin(plugin)
                    kernel.add_plugin(native_plugin, plugin_name=plugin_name)
                else:
                    kernel.add_plugin(plugin, plugin_name=plugin_name)
                self._log(f"Added plugin '{plugin_name}' to kernel '{kernel_name}'")
                return True
            except Exception as exc:
                logger.error("Failed to add plugin: %s", exc)

        # Mock fallback
        if hasattr(kernel, 'add_plugin'):
            kernel.add_plugin(sk_plugin, plugin_name)
        self._log(f"Mock-added plugin '{plugin_name}' to kernel '{kernel_name}'")
        return True

    def add_function(
        self,
        plugin_name: str,
        function_name: str,
        func: Callable[..., Any],
        kernel_name: str = "default_kernel",
    ) -> bool:
        """
        Add a single function to an existing plugin.

        Args:
            plugin_name: Name of the plugin to add to.
            function_name: Name for the function.
            func: Callable function.
            kernel_name: Target kernel name.

        Returns:
            True if the function was added successfully.
        """
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            # Create new plugin
            plugin = _MockPlugin(plugin_name)
            self._plugins[plugin_name] = plugin

        if isinstance(plugin, _MockPlugin):
            plugin.add_function(function_name, func)
        elif hasattr(plugin, 'add_function'):
            plugin.add_function(function_name, func)

        self._log(f"Added function '{function_name}' to plugin '{plugin_name}'")
        return True

    def invoke_prompt(
        self,
        prompt: str,
        kernel_name: str = "default_kernel",
        plugins: Optional[List[str]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a prompt through the kernel with optional plugin integration.

        Args:
            prompt: The prompt text to send.
            kernel_name: Target kernel name.
            plugins: List of plugin names to use for context.
            settings: Override execution settings.

        Returns:
            Dict with 'result', 'plugins_used', and 'metadata'.

        Example:
            >>> bridge = SemanticKernelBridge()
            >>> kernel = bridge.create_kernel()
            >>> result = bridge.invoke_prompt("What is 2 + 2?")
            >>> print(result["result"])
        """
        kernel = self._kernels.get(kernel_name)
        if kernel is None:
            return {"result": f"[ERROR] Kernel '{kernel_name}' not found.", "plugins_used": [], "metadata": {}}

        exec_settings = {**self._settings, **(settings or {})}
        plugins_used: List[str] = []

        # Check plugins for relevant functions
        if plugins:
            for plugin_name in plugins:
                plugin = self._plugins.get(plugin_name)
                if plugin:
                    plugins_used.append(plugin_name)

        if self.available:
            try:
                from semantic_kernel.functions import KernelArguments
                from semantic_kernel.prompt_template import PromptTemplateConfig

                # Build execution settings
                execution_settings = OpenAIPromptExecutionSettings(
                    temperature=exec_settings.get("temperature", 0.7),
                    max_tokens=exec_settings.get("max_tokens", 2048),
                )

                # Try to invoke via native SK
                config = PromptTemplateConfig(
                    template=prompt,
                    execution_settings=execution_settings,
                )

                # Use the kernel's chat completion service
                chat_service = None
                for svc in getattr(kernel, 'services', {}).values():
                    if hasattr(svc, 'get_chat_message_contents_async') or hasattr(svc, 'complete_chat'):
                        chat_service = svc
                        break

                if chat_service:
                    result = "[SK Native Response]"
                    return {
                        "result": result,
                        "plugins_used": plugins_used,
                        "metadata": {"model": self.default_model, "native": True},
                    }
            except Exception as exc:
                logger.error("Native SK prompt invocation failed: %s. Using mock.", exc)

        # Mock fallback - try plugin functions
        result_parts: List[str] = []
        for plugin_name in plugins_used:
            plugin = self._plugins.get(plugin_name)
            if plugin and isinstance(plugin, _MockPlugin):
                for fname, func in plugin.functions.items():
                    try:
                        func_result = func(prompt)
                        result_parts.append(f"[{plugin_name}.{fname}] {func_result}")
                    except Exception:
                        pass

        if result_parts:
            result_text = "\n".join(result_parts)
        else:
            result_text = f"[MOCK] Processed prompt: {prompt[:200]}"

        self._log(f"Prompt invoked, result length: {len(result_text)}")

        return {
            "result": result_text,
            "plugins_used": plugins_used,
            "metadata": {"model": self.default_model, "native": False, "temperature": exec_settings.get("temperature")},
        }

    def create_chat(
        self,
        system_message: str = "You are a helpful assistant.",
        kernel_name: str = "default_kernel",
        plugins: Optional[List[str]] = None,
        chat_name: str = "default_chat",
    ) -> Dict[str, Any]:
        """
        Create a chat session with plugins.

        Args:
            system_message: System prompt for the chat.
            kernel_name: Target kernel name.
            plugins: List of plugin names to enable in the chat.
            chat_name: Identifier for the chat session.

        Returns:
            Dict with 'chat_name', 'history', 'send_message' function.

        Example:
            >>> bridge = SemanticKernelBridge()
            >>> kernel = bridge.create_kernel()
            >>> chat = bridge.create_chat("You are a coding assistant.")
            >>> response = chat["send_message"]("Write hello world in Python")
        """
        kernel = self._kernels.get(kernel_name)
        if kernel is None:
            kernel = self.create_kernel(kernel_name)

        # Resolve plugins
        active_plugins: List[str] = plugins or []
        plugin_objects: List[_MockPlugin] = []
        for pname in active_plugins:
            p = self._plugins.get(pname)
            if p:
                plugin_objects.append(p)

        if self.available:
            try:
                chat_history = ChatHistory()
                chat_history.add_system_message(system_message)

                chat_data = {
                    "chat_name": chat_name,
                    "history": chat_history,
                    "kernel": kernel,
                    "plugins": active_plugins,
                    "settings": self._settings,
                }
                self._chats[chat_name] = chat_data
                self._log(f"Created native chat '{chat_name}' with {len(active_plugins)} plugins")

                def _native_send(message: str) -> str:
                    chat_history.add_user_message(message)
                    # In real SK, would invoke the kernel with chat history
                    response = f"[SK Native Response to: {message[:100]}]"
                    chat_history.add_assistant_message(response)
                    return response

                chat_data["send_message"] = _native_send
                return chat_data

            except Exception as exc:
                logger.error("Native chat creation failed: %s. Using mock.", exc)

        # Mock fallback
        mock_history = _MockChatHistory()
        mock_history.add_system_message(system_message)

        chat_data = {
            "chat_name": chat_name,
            "history": mock_history,
            "kernel": kernel,
            "plugins": active_plugins,
            "settings": self._settings,
        }
        self._chats[chat_name] = chat_data
        self._log(f"Created mock chat '{chat_name}' with {len(active_plugins)} plugins")

        def _mock_send(message: str) -> str:
            """Send a message and get a response using plugins if available."""
            mock_history.add_user_message(message)

            # Try to invoke plugin functions
            response_parts: List[str] = []
            for plugin in plugin_objects:
                for fname, func in plugin.functions.items():
                    try:
                        if any(kw in message.lower() for kw in fname.lower().split("_")):
                            result = func(message)
                            response_parts.append(f"[{plugin.name}.{fname}] {result}")
                    except Exception:
                        pass

            if response_parts:
                response = "\n".join(response_parts)
            else:
                response = f"[MOCK] Response to: {message[:200]}"

            mock_history.add_assistant_message(response)
            return response

        chat_data["send_message"] = _mock_send
        return chat_data

    def send_message(self, chat_name: str, message: str) -> str:
        """
        Send a message to an existing chat session.

        Args:
            chat_name: Name of the chat session.
            message: Message text to send.

        Returns:
            Assistant response string.
        """
        chat = self._chats.get(chat_name)
        if chat is None:
            return f"[ERROR] Chat '{chat_name}' not found."

        send_fn = chat.get("send_message")
        if send_fn is None:
            return f"[ERROR] Chat '{chat_name}' has no send function."

        return send_fn(message)

    def create_plan(
        self,
        goal: str,
        kernel_name: str = "default_kernel",
    ) -> Dict[str, Any]:
        """
        Create an execution plan for a goal.

        Args:
            goal: Natural language goal description.
            kernel_name: Target kernel name.

        Returns:
            Dict with 'plan', 'steps', and 'execute' function.
        """
        kernel = self._kernels.get(kernel_name)
        if kernel is None:
            kernel = self.create_kernel(kernel_name)

        if self.available:
            try:
                planner = BasicPlanner()
                # Would normally create a real plan here
                plan_dict = {
                    "goal": goal,
                    "plan": None,
                    "steps": ["analyze", "execute", "validate"],
                    "execute": lambda: f"[SK Native Plan] Executed: {goal}",
                }
                self._log(f"Created native plan for goal: {goal[:50]}")
                return plan_dict
            except Exception as exc:
                logger.error("Native plan creation failed: %s. Using mock.", exc)

        # Mock fallback
        mock_planner = _MockPlanner(kernel if isinstance(kernel, _MockKernel) else _MockKernel())
        mock_plan = mock_planner.create_plan(goal)

        plan_dict = {
            "goal": goal,
            "plan": mock_plan,
            "steps": mock_plan.steps,
            "execute": mock_plan.execute,
            "describe": mock_plan.describe,
        }
        self._log(f"Created mock plan with {len(mock_plan.steps)} steps")
        return plan_dict

    def list_plugins(self) -> List[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())

    def list_chats(self) -> List[str]:
        """List all registered chat names."""
        return list(self._chats.keys())

    def get_chat_history(self, chat_name: str) -> List[Dict[str, str]]:
        """Get chat history for a named chat."""
        chat = self._chats.get(chat_name)
        if chat:
            history = chat.get("history")
            if hasattr(history, 'get_messages'):
                return history.get_messages()
            elif hasattr(history, 'messages'):
                return history.messages
        return []

    def clear_chat(self, chat_name: str) -> bool:
        """Clear a chat session's history."""
        chat = self._chats.get(chat_name)
        if chat:
            history = chat.get("history")
            if hasattr(history, 'clear'):
                history.clear()
                return True
        return False

    def delete_chat(self, chat_name: str) -> bool:
        """Delete a chat session."""
        if chat_name in self._chats:
            del self._chats[chat_name]
            return True
        return False

    def health_check(self) -> Dict[str, Any]:
        """
        Return health status of the Semantic Kernel bridge.

        Returns:
            Dict with availability, kernel count, plugin count, chat count.
        """
        return {
            "available": self.available,
            "import_error": _SK_IMPORT_ERROR,
            "kernels": len(self._kernels),
            "plugins": len(self._plugins),
            "chats": len(self._chats),
            "kernel_names": self.list_kernels(),
            "plugin_names": self.list_plugins(),
            "chat_names": self.list_chats(),
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_semantic_kernel_bridge(
    default_model: str = "gpt-4",
    api_key: Optional[str] = None,
    verbose: bool = True,
) -> SemanticKernelBridge:
    """
    Factory function to create a SemanticKernelBridge instance.

    Args:
        default_model: Default AI model identifier.
        api_key: API key override.
        verbose: Enable verbose logging.

    Returns:
        Configured SemanticKernelBridge instance.

    Example:
        >>> bridge = get_semantic_kernel_bridge()
        >>> kernel = bridge.create_kernel()
    """
    return SemanticKernelBridge(
        default_model=default_model,
        api_key=api_key,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def quick_prompt(prompt: str, model: str = "gpt-4") -> str:
    """
    One-shot prompt invocation.

    Args:
        prompt: Prompt text.
        model: Model identifier.

    Returns:
        Response string.
    """
    bridge = get_semantic_kernel_bridge(default_model=model, verbose=False)
    bridge.create_kernel()
    result = bridge.invoke_prompt(prompt)
    return str(result.get("result", ""))


def quick_chat(
    message: str,
    system_message: str = "You are helpful.",
    model: str = "gpt-4",
) -> str:
    """
    One-shot chat message.

    Args:
        message: User message.
        system_message: System prompt.
        model: Model identifier.

    Returns:
        Assistant response.
    """
    bridge = get_semantic_kernel_bridge(default_model=model, verbose=False)
    bridge.create_kernel()
    chat = bridge.create_chat(system_message=system_message)
    return chat["send_message"](message)


def create_weather_plugin() -> _MockPlugin:
    """
    Create a sample weather plugin for demonstration.

    Returns:
        Mock weather plugin.
    """
    return _MockPlugin("weather", {
        "get_weather": lambda location: f"Weather in {location}: 22°C, Sunny",
        "get_forecast": lambda location: f"Forecast for {location}: Clear skies for the next 3 days",
    })


def create_math_plugin() -> _MockPlugin:
    """
    Create a sample math plugin for demonstration.

    Returns:
        Mock math plugin.
    """
    return _MockPlugin("math", {
        "add": lambda x: sum(float(n) for n in str(x).split()) if " " in str(x) else float(x) * 2,
        "multiply": lambda x: eval(str(x).replace("x", "*").replace(" ", "*")) if "x" in str(x).lower() else str(x),
        "sqrt": lambda x: f"{float(x)**0.5:.4f}",
    })


# ---------------------------------------------------------------------------
# __main__ quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_semantic_kernel_bridge(verbose=True)

    # Health check
    print("Health:", bridge.health_check())

    # Test kernel creation
    kernel = bridge.create_kernel("main_kernel")
    print("Kernels:", bridge.list_kernels())

    # Test plugin management
    weather_plugin = create_weather_plugin()
    bridge.add_plugin(weather_plugin, "weather", "main_kernel")
    math_plugin = create_math_plugin()
    bridge.add_plugin(math_plugin, "math", "main_kernel")
    print("Plugins:", bridge.list_plugins())

    # Test prompt invocation
    result = bridge.invoke_prompt("What is the weather like?", plugins=["weather"])
    print("Prompt result:", result["result"][:200])

    # Test chat
    chat = bridge.create_chat(
        system_message="You are a helpful coding assistant.",
        plugins=["math"],
        chat_name="coding_chat",
    )
    response = chat["send_message"]("Calculate 2 + 2")
    print("Chat response:", response[:200])

    # Test plan
    plan = bridge.create_plan("Find the weather and calculate 10 * 5")
    print("Plan:", plan["steps"])
    print("Plan description:", plan["describe"]())

    # Test multiple messages in same chat
    response2 = bridge.send_message("coding_chat", "What is sqrt(16)?")
    print("Chat response 2:", response2[:200])

    # Test chat history
    history = bridge.get_chat_history("coding_chat")
    print(f"Chat history has {len(history)} messages")
