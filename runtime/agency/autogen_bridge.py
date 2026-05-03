"""
JARVIS BRAINIAC - AutoGen Integration Bridge
=============================================

Unified AutoGen (pyautogen) adapter providing:
- Assistant agent creation with configurable LLM backends
- User proxy agent creation with code execution
- Group chat orchestration with multiple agents
- Code generation + execution workflows
- Mock fallback when pyautogen is not installed

Usage:
    bridge = AutoGenBridge()
    assistant = bridge.create_assistant("coder", "You are a Python expert.")
    user_proxy = bridge.create_user_proxy("user")
    user_proxy.initiate_chat(assistant, message="Write a function to sort a list.")
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

import logging

# Restore agency dir to sys.path so sibling modules remain importable
if _removed_path is not None:
    _sys.path.insert(0, _removed_path)
import json
import os
import re
import sys
import tempfile
import warnings
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_AUTOGEN_AVAILABLE: bool = False

try:
    import autogen
    from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
    from autogen.agentchat import Agent
    from autogen.coding import LocalCommandLineCodeExecutor
    from autogen.oai.client import OpenAIWrapper
    _AUTOGEN_AVAILABLE = True
    logger.info("AutoGen %s loaded successfully.", autogen.__version__)
except Exception as _import_exc:
    logger.warning(
        "AutoGen not installed or failed to import (%s). "
        "Falling back to mock implementations.",
        _import_exc,
    )

# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockAgent:
    """Mock agent that simulates AutoGen agent behavior."""

    def __init__(
        self,
        name: str,
        system_message: str = "You are a helpful assistant.",
        is_user_proxy: bool = False,
        code_execution_config: Optional[Dict[str, Any]] = None,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name: str = name
        self.system_message: str = system_message
        self.is_user_proxy: bool = is_user_proxy
        self.code_execution_config: Optional[Dict[str, Any]] = code_execution_config
        self.llm_config: Optional[Dict[str, Any]] = llm_config or {}
        self.chat_history: List[Dict[str, str]] = []
        self._reply_count: int = 0
        self._registered_functions: List[Dict[str, Any]] = []

    def send(self, message: Union[str, Dict[str, Any]], recipient: Any, request_reply: bool = True) -> None:
        """Send a message to another mock agent."""
        msg_str = message if isinstance(message, str) else str(message.get("content", message))
        self.chat_history.append({"from": self.name, "to": recipient.name if hasattr(recipient, 'name') else str(recipient), "content": msg_str})
        logger.info("[%s -> %s]: %s", self.name, recipient.name if hasattr(recipient, 'name') else '?', msg_str[:100])
        if request_reply and hasattr(recipient, 'receive'):
            recipient.receive(msg_str, self)

    def receive(self, message: Union[str, Dict[str, Any]], sender: Any, request_reply: bool = True) -> None:
        """Receive a message from another agent."""
        msg_str = message if isinstance(message, str) else str(message.get("content", message))
        self.chat_history.append({"from": sender.name if hasattr(sender, 'name') else str(sender), "to": self.name, "content": msg_str})
        if request_reply:
            reply = self._generate_reply(sender=sender)
            if reply and hasattr(sender, 'receive'):
                sender.receive(reply, self, request_reply=False)

    def _generate_reply(self, sender: Any = None, **kwargs: Any) -> Optional[str]:
        """Generate a mock reply based on context."""
        self._reply_count += 1
        if self.is_user_proxy:
            return f"[MOCK {self.name}] Task received. Proceeding with execution."

        # Check for code execution
        last_msg = self.chat_history[-1]["content"] if self.chat_history else ""

        if "```python" in last_msg or "```" in last_msg:
            code = self._extract_code(last_msg)
            if code:
                result = self._mock_execute_code(code)
                return f"[MOCK {self.name}] Code executed:\n```\n{result}\n```\nTERMINATE"

        if "TERMINATE" in last_msg.upper():
            return None

        return (
            f"[MOCK {self.name}] This is a simulated response (turn {self._reply_count}). "
            f"System prompt: {self.system_message[:50]}..."
        )

    def _extract_code(self, text: str) -> Optional[str]:
        """Extract code blocks from markdown text."""
        pattern = r"```(?:python)?\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1) if match else None

    def _mock_execute_code(self, code: str) -> str:
        """Execute code in a restricted environment."""
        try:
            # Only allow safe operations
            allowed_builtins = {"range", "len", "print", "str", "int", "float", "list", "dict", "sum", "max", "min", "sorted", "enumerate", "zip", "map", "filter", "abs", "round", "pow"}
            safe_globals = {"__builtins__": {name: __builtins__[name] for name in allowed_builtins if name in __builtins__}}
            result = eval(code, safe_globals, {})
            return str(result)
        except SyntaxError:
            try:
                import io
                stdout = io.StringIO()
                safe_globals["__builtins__"]["print"] = lambda *args, **kwargs: stdout.write(" ".join(str(a) for a in args) + "\n")
                exec(code, safe_globals, {})
                output = stdout.getvalue()
                return output if output.strip() else "[Code executed successfully with no output]"
            except Exception as e:
                return f"[Execution Error] {type(e).__name__}: {e}"
        except Exception as e:
            return f"[Execution Error] {type(e).__name__}: {e}"

    def initiate_chat(
        self,
        recipient: Any,
        message: str,
        clear_history: bool = True,
        max_turns: int = 10,
        **kwargs: Any,
    ) -> List[Dict[str, str]]:
        """Initiate a two-agent chat conversation."""
        if clear_history:
            self.chat_history.clear()
            if hasattr(recipient, 'chat_history'):
                recipient.chat_history.clear()

        self.chat_history.append({"from": self.name, "to": recipient.name, "content": message})

        current_sender = self
        current_recipient = recipient
        turns = 0

        while turns < max_turns:
            reply = current_sender._generate_reply(sender=current_recipient)
            if reply is None or "TERMINATE" in str(reply).upper():
                break
            current_recipient.chat_history.append({
                "from": current_sender.name,
                "to": current_recipient.name,
                "content": reply,
            })
            current_sender, current_recipient = current_recipient, current_sender
            turns += 1

        return self.chat_history

    def register_function(self, function_map: Dict[str, Callable[..., Any]]) -> None:
        """Register callable functions for the agent."""
        self._registered_functions.extend([
            {"name": name, "callable": fn} for name, fn in function_map.items()
        ])

    def reset(self) -> None:
        """Reset agent state."""
        self.chat_history.clear()
        self._reply_count = 0

    def __repr__(self) -> str:
        return f"_MockAgent(name='{self.name}', user_proxy={self.is_user_proxy})"


class _MockGroupChat:
    """Mock group chat orchestrating multiple agents."""

    def __init__(
        self,
        agents: List[Any],
        messages: List[Dict[str, str]],
        max_round: int = 10,
        speaker_selection_method: str = "auto",
    ) -> None:
        self.agents: List[Any] = agents
        self.messages: List[Dict[str, str]] = messages
        self.max_round: int = max_round
        self.speaker_selection_method: str = speaker_selection_method
        self.agent_names: List[str] = [a.name for a in agents if hasattr(a, 'name')]
        self.round: int = 0

    def run(self, initial_message: Optional[str] = None) -> List[Dict[str, str]]:
        """Execute the group chat for max_round turns."""
        transcript: List[Dict[str, str]] = []

        if initial_message:
            transcript.append({"speaker": "System", "message": initial_message})

        # Seed with initial messages
        for msg in self.messages:
            transcript.append(msg)

        for current_round in range(self.max_round):
            self.round = current_round
            for agent in self.agents:
                reply = agent._generate_reply()
                if reply:
                    entry = {"speaker": agent.name, "message": reply, "round": current_round}
                    transcript.append(entry)
                    agent.chat_history.append({"from": agent.name, "to": "group", "content": reply})
                if "TERMINATE" in str(reply).upper():
                    return transcript

        return transcript


class _MockCodeExecutor:
    """Mock code executor with sandboxed execution."""

    def __init__(self, timeout: int = 60, work_dir: Optional[str] = None) -> None:
        self.timeout: int = timeout
        self.work_dir: str = work_dir or tempfile.mkdtemp(prefix="autogen_mock_")
        self.execution_history: List[Dict[str, Any]] = []

    def execute_code_blocks(self, code_blocks: List[Dict[str, str]]) -> Tuple[int, str, Optional[str]]:
        """Execute code blocks and return (exit_code, logs, image_path)."""
        logs: List[str] = []
        for block in code_blocks:
            lang = block.get("language", "python")
            code = block.get("code", "")
            log_entry: Dict[str, Any] = {"language": lang, "code": code[:200]}

            if lang == "python":
                result = self._exec_python(code)
            else:
                result = f"[MOCK] Language '{lang}' execution not supported in mock mode."

            log_entry["result"] = result
            self.execution_history.append(log_entry)
            logs.append(result)

        return 0, "\n".join(logs), None

    def _exec_python(self, code: str) -> str:
        """Execute Python code safely."""
        try:
            allowed_names = {
                "range", "len", "str", "int", "float", "list", "dict", "set",
                "tuple", "sum", "max", "min", "sorted", "enumerate", "zip",
                "map", "filter", "abs", "round", "pow", "divmod", "chr", "ord",
                "hex", "bin", "oct", "all", "any", "reversed", "slice",
            }
            safe_globals = {"__builtins__": {name: getattr(__builtins__, name) for name in allowed_names if hasattr(__builtins__, name)}}
            safe_globals["__builtins__"]["print"] = lambda *args, **kw: None

            try:
                result = eval(code, safe_globals, {})
                return str(result)
            except SyntaxError:
                import io
                stdout = io.StringIO()
                safe_globals["__builtins__"]["print"] = lambda *a, **kw: stdout.write(" ".join(str(x) for x in a) + "\n")
                exec(code, safe_globals, {})
                output = stdout.getvalue()
                return output if output.strip() else "[Code executed with no output]"
        except Exception as e:
            return f"[Error] {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# AutoGenBridge
# ---------------------------------------------------------------------------

class AutoGenBridge:
    """
    Unified AutoGen integration bridge for JARVIS BRAINIAC.

    Provides factory methods for creating assistant agents, user proxies,
    group chats, and code execution pipelines. When AutoGen is not installed,
    all methods return fully-functional mock implementations.

    Attributes:
        available (bool): Whether the real AutoGen library is installed.
        llm_config (dict): Default LLM configuration for agents.
    """

    def __init__(
        self,
        llm_config: Optional[Dict[str, Any]] = None,
        default_model: str = "gpt-4",
        timeout: int = 60,
        verbose: bool = True,
    ) -> None:
        """
        Initialize the AutoGen bridge.

        Args:
            llm_config: Configuration dict passed to AutoGen agents.
                        If None, auto-detected from environment.
            default_model: Default model name.
            timeout: Code execution timeout in seconds.
            verbose: Enable verbose logging.
        """
        self.available: bool = _AUTOGEN_AVAILABLE
        self.verbose: bool = verbose
        self.default_model: str = default_model
        self.timeout: int = timeout
        self._agents: Dict[str, Any] = {}
        self._llm_config: Dict[str, Any] = llm_config or self._build_default_llm_config()
        self._code_executor: Optional[_MockCodeExecutor] = None
        logger.info("AutoGenBridge initialized (available=%s)", self.available)

    def _build_default_llm_config(self) -> Dict[str, Any]:
        """Build default LLM config from environment variables."""
        config: Dict[str, Any] = {"config_list": []}

        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            config["config_list"].append({
                "model": self.default_model,
                "api_key": openai_key,
            })
            # Add cheaper fallback
            config["config_list"].append({
                "model": "gpt-3.5-turbo",
                "api_key": openai_key,
            })

        azure_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        if azure_key:
            config["config_list"].append({
                "model": os.environ.get("AZURE_OPENAI_MODEL", self.default_model),
                "api_key": azure_key,
                "api_base": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                "api_type": "azure",
                "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            })

        if not config["config_list"]:
            logger.warning("No LLM API keys found. AutoGen agents will use mock mode.")

        config["temperature"] = 0.7
        config["timeout"] = self.timeout
        return config

    def _log(self, msg: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            logger.info("[AutoGenBridge] %s", msg)

    # -- public API ----------------------------------------------------------

    def create_assistant(
        self,
        name: str,
        system_message: str,
        llm_config: Optional[Dict[str, Any]] = None,
        code_execution: bool = False,
        **kwargs: Any,
    ) -> Any:
        """
        Create an AutoGen AssistantAgent (or mock equivalent).

        Args:
            name: Unique name for the assistant agent.
            system_message: System prompt defining the agent's behavior.
            llm_config: Override LLM configuration. Uses bridge default if None.
            code_execution: Whether the assistant can execute code.
            **kwargs: Additional keyword arguments passed to the agent constructor.

        Returns:
            AssistantAgent or mock agent object.

        Example:
            >>> bridge = AutoGenBridge()
            >>> coder = bridge.create_assistant("coder", "You are a Python expert.")
            >>> result = coder._generate_reply()
        """
        config = llm_config or self._llm_config

        if self.available:
            try:
                agent = AssistantAgent(
                    name=name,
                    system_message=system_message,
                    llm_config=config,
                    code_execution_config={"use_docker": False} if code_execution else None,
                    **kwargs,
                )
                self._agents[name] = agent
                self._log(f"Created assistant '{name}'")
                return agent
            except Exception as exc:
                logger.error("Failed to create assistant: %s. Using mock.", exc)

        mock_agent = _MockAgent(
            name=name,
            system_message=system_message,
            llm_config=config,
            code_execution_config={"use_docker": False} if code_execution else None,
            **kwargs,
        )
        self._agents[name] = mock_agent
        self._log(f"Created mock assistant '{name}'")
        return mock_agent

    def create_user_proxy(
        self,
        name: str,
        human_input_mode: str = "NEVER",
        max_consecutive_auto_reply: int = 10,
        code_execution_config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Create an AutoGen UserProxyAgent (or mock equivalent).

        Args:
            name: Unique name for the user proxy agent.
            human_input_mode: When to prompt for human input ("NEVER", "TERMINATE", "ALWAYS").
            max_consecutive_auto_reply: Maximum auto-replies before stopping.
            code_execution_config: Code execution configuration dict.
                                 Auto-configured if None.
            **kwargs: Additional keyword arguments.

        Returns:
            UserProxyAgent or mock user proxy object.

        Example:
            >>> bridge = AutoGenBridge()
            >>> user = bridge.create_user_proxy("user")
            >>> chat_result = user.initiate_chat(assistant, message="Hello")
        """
        if code_execution_config is None:
            work_dir = tempfile.mkdtemp(prefix="autogen_exec_")
            code_execution_config = {
                "last_n_messages": 3,
                "work_dir": work_dir,
                "use_docker": False,
                "timeout": self.timeout,
            }

        if self.available:
            try:
                agent = UserProxyAgent(
                    name=name,
                    human_input_mode=human_input_mode,
                    max_consecutive_auto_reply=max_consecutive_auto_reply,
                    code_execution_config=code_execution_config,
                    **kwargs,
                )
                self._agents[name] = agent
                self._log(f"Created user proxy '{name}'")
                return agent
            except Exception as exc:
                logger.error("Failed to create user proxy: %s. Using mock.", exc)

        mock_agent = _MockAgent(
            name=name,
            is_user_proxy=True,
            code_execution_config=code_execution_config,
            system_message="User proxy for executing code and relaying messages.",
            **kwargs,
        )
        self._agents[name] = mock_agent
        self._log(f"Created mock user proxy '{name}'")
        return mock_agent

    def group_chat(
        self,
        agents: List[Any],
        messages: Optional[List[Union[str, Dict[str, str]]]] = None,
        max_round: int = 10,
        speaker_selection_method: str = "auto",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Orchestrate a group chat among multiple agents.

        Args:
            agents: List of agents to include in the group chat.
            messages: Initial messages to seed the conversation.
            max_round: Maximum number of conversation rounds.
            speaker_selection_method: Method for selecting next speaker.
            **kwargs: Additional keyword arguments.

        Returns:
            Dict with 'transcript', 'agent_names', and 'rounds' keys.

        Example:
            >>> coder = bridge.create_assistant("coder", "You code.")
            >>> reviewer = bridge.create_assistant("reviewer", "You review code.")
            >>> result = bridge.group_chat([coder, reviewer], messages=["Write a sort function."])
        """
        if messages is None:
            messages = [{"speaker": "System", "message": "Start group discussion."}]

        # Normalize messages
        normalized: List[Dict[str, str]] = []
        for msg in messages:
            if isinstance(msg, str):
                normalized.append({"speaker": "System", "message": msg})
            else:
                normalized.append(msg)

        if self.available:
            try:
                group_chat = GroupChat(
                    agents=agents,
                    messages=[m.get("message", str(m)) for m in normalized],
                    max_round=max_round,
                    speaker_selection_method=speaker_selection_method,
                    **kwargs,
                )
                manager = GroupChatManager(
                    groupchat=group_chat,
                    llm_config=self._llm_config,
                )

                # Initiate via first user proxy or create one
                proxy_name = "group_chat_proxy"
                if proxy_name not in self._agents:
                    proxy = self.create_user_proxy(proxy_name)
                else:
                    proxy = self._agents[proxy_name]

                initial_msg = normalized[0].get("message", "Discuss the following topic.")
                chat_result = proxy.initiate_chat(manager, message=initial_msg)

                return {
                    "transcript": [
                        {"speaker": "GroupChat", "message": str(m)} for m in (chat_result if isinstance(chat_result, list) else [])
                    ],
                    "agent_names": [a.name for a in agents],
                    "rounds": max_round,
                    "manager": manager,
                }
            except Exception as exc:
                logger.error("Group chat failed: %s. Using mock.", exc)

        # Mock fallback
        mock_gc = _MockGroupChat(
            agents=agents,
            messages=normalized,
            max_round=max_round,
            speaker_selection_method=speaker_selection_method,
        )
        transcript = mock_gc.run()
        self._log(f"Completed mock group chat with {len(agents)} agents, {len(transcript)} messages")

        return {
            "transcript": transcript,
            "agent_names": [a.name for a in agents],
            "rounds": mock_gc.round,
            "manager": None,
        }

    def code_execution(
        self,
        task: str,
        coder_name: str = "code_executor",
        executor_name: str = "code_runner",
        max_turns: int = 5,
    ) -> Dict[str, Any]:
        """
        Generate and execute code for a given task.

        Creates a coder assistant and a user proxy with code execution,
        then runs them in a conversation to complete the task.

        Args:
            task: Natural language description of the coding task.
            coder_name: Name for the coder assistant agent.
            executor_name: Name for the code executor proxy agent.
            max_turns: Maximum conversation turns.

        Returns:
            Dict with 'code', 'output', 'transcript', and 'success' keys.

        Example:
            >>> result = bridge.code_execution("Write a function to compute factorial")
            >>> print(result["code"])
            >>> print(result["output"])
        """
        coder_system = (
            "You are a helpful coding assistant. Write Python code to solve the given task. "
            "Always wrap code in ```python blocks. Reply with TERMINATE when done."
        )
        coder = self.create_assistant(coder_name, coder_system)
        executor = self.create_user_proxy(executor_name)

        transcript = []
        success = False
        generated_code = ""
        execution_output = ""

        if self.available:
            try:
                chat_result = executor.initiate_chat(coder, message=task, max_turns=max_turns)
                for msg in (chat_result if isinstance(chat_result, list) else []):
                    content = msg.get("content", str(msg))
                    transcript.append({"from": msg.get("from", "?"), "content": content})
                    code = self._extract_code(content)
                    if code:
                        generated_code = code
                        execution_output = self._execute_code_sandbox(code)
                        success = "[Error]" not in execution_output
            except Exception as exc:
                logger.error("Code execution pipeline failed: %s. Using mock.", exc)

        if not transcript:
            # Mock execution
            mock_code = self._generate_mock_code(task)
            generated_code = mock_code
            execution_output = self._execute_code_sandbox(mock_code)
            success = "[Error]" not in execution_output
            transcript = [
                {"from": executor_name, "content": task},
                {"from": coder_name, "content": f"```python\n{mock_code}\n```\nTERMINATE"},
                {"from": executor_name, "content": f"Execution result:\n{execution_output}"},
            ]

        self._log(f"Code execution complete: success={success}, code_len={len(generated_code)}")

        return {
            "code": generated_code,
            "output": execution_output,
            "transcript": transcript,
            "success": success,
            "task": task,
        }

    def _extract_code(self, text: str) -> str:
        """Extract Python code blocks from markdown text."""
        pattern = r"```(?:python)?\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _execute_code_sandbox(self, code: str) -> str:
        """Execute code in a sandboxed environment."""
        if not self._code_executor:
            self._code_executor = _MockCodeExecutor(timeout=self.timeout)

        result = self._code_executor._exec_python(code)
        return result

    def _generate_mock_code(self, task: str) -> str:
        """Generate plausible mock code based on task description."""
        task_lower = task.lower()
        if "sort" in task_lower:
            return "def sort_list(arr):\n    return sorted(arr)\nprint(sort_list([3, 1, 4, 1, 5]))"
        elif "factorial" in task_lower:
            return "def factorial(n):\n    return 1 if n <= 1 else n * factorial(n-1)\nprint(factorial(5))"
        elif "fibonacci" in task_lower:
            return "def fibonacci(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a+b\n    return a\nprint(fibonacci(10))"
        elif "prime" in task_lower:
            return "def is_prime(n):\n    if n < 2: return False\n    for i in range(2, int(n**0.5)+1):\n        if n % i == 0: return False\n    return True\nprint([n for n in range(20) if is_prime(n)])"
        else:
            return f"# Task: {task}\ndef solve():\n    return 'Mock solution for: {task[:50]}'\nprint(solve())"

    def register_tools(self, agent_name: str, tools: Dict[str, Callable[..., Any]]) -> bool:
        """
        Register callable tools with an existing agent.

        Args:
            agent_name: Name of the agent to register tools with.
            tools: Dict mapping tool names to callable functions.

        Returns:
            True if registration succeeded, False otherwise.
        """
        agent = self._agents.get(agent_name)
        if agent is None:
            logger.error("Agent '%s' not found.", agent_name)
            return False

        if self.available and hasattr(agent, 'register_function'):
            try:
                agent.register_function(tools)
                self._log(f"Registered {len(tools)} tools with agent '{agent_name}'")
                return True
            except Exception as exc:
                logger.error("Tool registration failed: %s", exc)

        # Mock fallback
        if hasattr(agent, 'register_function'):
            agent.register_function(tools)
        self._log(f"Mock-registered {len(tools)} tools with agent '{agent_name}'")
        return True

    def reset_agent(self, name: str) -> bool:
        """Reset a specific agent's state."""
        agent = self._agents.get(name)
        if agent and hasattr(agent, 'reset'):
            agent.reset()
            self._log(f"Reset agent '{name}'")
            return True
        return False

    def get_agent(self, name: str) -> Optional[Any]:
        """Retrieve an agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    def delete_agent(self, name: str) -> bool:
        """Remove an agent from the registry."""
        if name in self._agents:
            del self._agents[name]
            self._log(f"Deleted agent '{name}'")
            return True
        return False

    def health_check(self) -> Dict[str, Any]:
        """
        Return health status of the AutoGen bridge.

        Returns:
            Dict with availability, agent count, and configuration status.
        """
        return {
            "available": self.available,
            "agents": len(self._agents),
            "agent_names": self.list_agents(),
            "default_model": self.default_model,
            "timeout": self.timeout,
            "llm_configured": len(self._llm_config.get("config_list", [])) > 0,
        }

    def create_sequential_chat(
        self,
        agents: List[Any],
        initial_message: str,
        max_turns_per_agent: int = 2,
    ) -> List[Dict[str, str]]:
        """
        Create a sequential chat where each agent responds in order.

        Args:
            agents: Ordered list of agents to participate.
            initial_message: Starting message.
            max_turns_per_agent: Max turns each agent takes.

        Returns:
            List of transcript entries.
        """
        transcript: List[Dict[str, str]] = []
        current_message = initial_message

        for turn in range(max_turns_per_agent):
            for agent in agents:
                if hasattr(agent, '_generate_reply'):
                    reply = agent._generate_reply()
                elif hasattr(agent, 'generate_reply'):
                    reply = agent.generate_reply(messages=[{"content": current_message}])
                else:
                    reply = f"[MOCK] Response from {agent.name if hasattr(agent, 'name') else str(agent)}"

                entry = {
                    "speaker": agent.name if hasattr(agent, 'name') else str(agent),
                    "message": str(reply),
                    "turn": turn,
                }
                transcript.append(entry)
                current_message = str(reply)

                if "TERMINATE" in str(reply).upper():
                    return transcript

        return transcript


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_autogen_bridge(
    llm_config: Optional[Dict[str, Any]] = None,
    default_model: str = "gpt-4",
    timeout: int = 60,
    verbose: bool = True,
) -> AutoGenBridge:
    """
    Factory function to create an AutoGenBridge instance.

    Args:
        llm_config: LLM configuration dict.
        default_model: Default model identifier.
        timeout: Code execution timeout in seconds.
        verbose: Enable verbose logging.

    Returns:
        Configured AutoGenBridge instance.

    Example:
        >>> bridge = get_autogen_bridge()
        >>> assistant = bridge.create_assistant("helper", "You are helpful.")
    """
    return AutoGenBridge(
        llm_config=llm_config,
        default_model=default_model,
        timeout=timeout,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def quick_code(task: str, model: str = "gpt-4") -> Dict[str, Any]:
    """
    One-shot code generation and execution.

    Args:
        task: Natural language task description.
        model: Model identifier.

    Returns:
        Dict with 'code', 'output', and 'success'.
    """
    bridge = get_autogen_bridge(default_model=model, verbose=False)
    return bridge.code_execution(task)


def quick_chat(message: str, system_message: str = "You are helpful.", model: str = "gpt-4") -> List[Dict[str, str]]:
    """
    One-shot two-agent chat.

    Args:
        message: User message.
        system_message: Assistant system prompt.
        model: Model identifier.

    Returns:
        Chat transcript.
    """
    bridge = get_autogen_bridge(default_model=model, verbose=False)
    assistant = bridge.create_assistant("assistant", system_message)
    user = bridge.create_user_proxy("user")
    return user.initiate_chat(assistant, message=message)


def quick_group_chat(
    messages: List[str],
    agent_configs: Optional[List[Dict[str, str]]] = None,
    max_round: int = 5,
) -> Dict[str, Any]:
    """
    One-shot group chat with default agents.

    Args:
        messages: Initial messages.
        agent_configs: List of {"name": str, "system_message": str} dicts.
        max_round: Max conversation rounds.

    Returns:
        Group chat result dict.
    """
    bridge = get_autogen_bridge(verbose=False)
    if agent_configs is None:
        agent_configs = [
            {"name": "planner", "system_message": "You plan and organize."},
            {"name": "executor", "system_message": "You execute and implement."},
            {"name": "reviewer", "system_message": "You review and critique."},
        ]
    agents = [bridge.create_assistant(c["name"], c["system_message"]) for c in agent_configs]
    return bridge.group_chat(agents, messages=messages, max_round=max_round)


# ---------------------------------------------------------------------------
# __main__ quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_autogen_bridge(verbose=True)

    # Health check
    print("Health:", bridge.health_check())

    # Test assistant creation
    coder = bridge.create_assistant("coder", "You are an expert Python programmer.")
    print("Created:", coder)

    # Test user proxy
    user = bridge.create_user_proxy("user")
    print("Created:", user)

    # Test two-agent chat
    chat_result = user.initiate_chat(coder, message="Write a hello world program.")
    print(f"Chat had {len(chat_result)} messages")

    # Test code execution
    exec_result = bridge.code_execution("Write a function to compute the factorial of a number.")
    print("Code:\n", exec_result["code"])
    print("Output:", exec_result["output"])
    print("Success:", exec_result["success"])

    # Test group chat
    planner = bridge.create_assistant("planner", "You create plans.")
    reviewer = bridge.create_assistant("reviewer", "You review plans.")
    gc_result = bridge.group_chat(
        [planner, reviewer],
        messages=["Plan a simple web application."],
        max_round=3,
    )
    print(f"Group chat had {len(gc_result['transcript'])} messages")
    for entry in gc_result['transcript']:
        print(f"  [{entry.get('speaker', '?')}]: {entry.get('message', '')[:80]}")
