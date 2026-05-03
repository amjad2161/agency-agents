"""
JARVIS BRAINIAC - LangChain Integration Bridge
===============================================

Unified LangChain adapter providing:
- LLMChain creation and execution
- Agent construction with tool binding
- RAG (Retrieval-Augmented Generation) pipelines
- Conversational memory chains
- Mock fallback when langchain is not installed

Usage:
    bridge = LangChainBridge()
    chain = bridge.create_chain("Tell me about {topic}")
    result = bridge.run_chain(chain, {"topic": "AI"})

    agent = bridge.create_agent([my_tool])
    result = bridge.run_chain(agent, {"input": "Calculate 2+2"})
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
import os
import sys
import warnings
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_LANGCHAIN_AVAILABLE: bool = False

try:
    import langchain
    from langchain.chains import LLMChain, RetrievalQA, ConversationalRetrievalChain
    from langchain.chains.base import Chain
    from langchain.memory import ConversationBufferMemory, ConversationBufferWindowMemory
    from langchain.prompts import PromptTemplate, ChatPromptTemplate
    from langchain.schema import BaseMessage, HumanMessage, SystemMessage, AIMessage
    from langchain.schema.language_model import BaseLanguageModel
    from langchain.tools import BaseTool, Tool
    from langchain.agents import AgentType, initialize_agent, AgentExecutor
    from langchain.vectorstores import FAISS, Chroma
    from langchain.embeddings.base import Embeddings
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.document_loaders import TextLoader, PyPDFLoader
    from langchain.callbacks.base import BaseCallbackHandler
    _LANGCHAIN_AVAILABLE = True
    logger.info("LangChain %s loaded successfully.", langchain.__version__)
except Exception as _import_exc:
    logger.warning(
        "LangChain not installed or failed to import (%s). "
        "Falling back to mock implementations.",
        _import_exc,
    )

# ---------------------------------------------------------------------------
# Mock implementations (used when langchain is unavailable)
# ---------------------------------------------------------------------------

class _MockPromptTemplate:
    """Mock prompt template for use without LangChain installed."""

    def __init__(self, template: str, input_variables: Optional[List[str]] = None, **kwargs: Any) -> None:
        self.template: str = template
        self.input_variables: List[str] = input_variables or []
        self._extra: Dict[str, Any] = kwargs

    def format(self, **kwargs: Any) -> str:
        """Format the template with provided keyword arguments."""
        try:
            return self.template.format(**kwargs)
        except KeyError as exc:
            missing = [v for v in self.input_variables if v not in kwargs]
            return f"[MOCK] Prompt formatted with missing vars {missing}: {self.template}"

    def invoke(self, inputs: Dict[str, Any]) -> Any:
        """Invoke-style interface for compatibility."""
        return self.format(**inputs)


class _MockLLM:
    """Mock LLM that echoes inputs with a prefix."""

    def __init__(self, prefix: str = "[MOCK LLM] ", **kwargs: Any) -> None:
        self.prefix: str = prefix
        self._config: Dict[str, Any] = kwargs

    def predict(self, text: str, **kwargs: Any) -> str:
        """Predict a response for the given text."""
        return f"{self.prefix}Response to: {text[:200]}"

    def invoke(self, inputs: Any) -> Any:
        """Invoke-style interface for compatibility."""
        if isinstance(inputs, str):
            return self.predict(inputs)
        return f"{self.prefix}Processed input: {str(inputs)[:200]}"

    def __call__(self, inputs: Any) -> Any:
        """Callable interface."""
        return self.invoke(inputs)


class _MockChain:
    """Mock chain for execution when LangChain is unavailable."""

    def __init__(self, prompt_template: str, llm: Optional[Any] = None, memory: Optional[Any] = None) -> None:
        self.prompt_template: str = prompt_template
        self.llm: Any = llm or _MockLLM()
        self.memory: Optional[Any] = memory
        self._call_count: int = 0

    def run(self, **kwargs: Any) -> str:
        """Run the mock chain with inputs."""
        self._call_count += 1
        formatted = self.prompt_template
        for key, value in kwargs.items():
            formatted = formatted.replace(f"{{{key}}}", str(value))
        if self.memory:
            past = getattr(self.memory, 'buffer', '')
            formatted = f"[Memory: {past}] {formatted}"
        response = self.llm.predict(formatted)
        if self.memory:
            if hasattr(self.memory, 'save_context'):
                self.memory.save_context({"input": str(kwargs)}, {"output": response})
            elif hasattr(self.memory, 'add'):
                self.memory.add(formatted, response)
        return response

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke-style run returning a dict."""
        result = self.run(**inputs)
        return {"output": result, "text": result}

    def __call__(self, inputs: Any) -> Any:
        """Callable interface."""
        if isinstance(inputs, dict):
            return self.invoke(inputs)
        return self.run(**{k: v for k, v in inputs.items()} if hasattr(inputs, 'items') else {"input": str(inputs)})


class _MockTool:
    """Mock tool for agent construction without LangChain."""

    def __init__(self, name: str, func: Callable[..., str], description: str) -> None:
        self.name: str = name
        self.func: Callable[..., str] = func
        self.description: str = description

    def run(self, tool_input: str) -> str:
        """Execute the tool with the given input."""
        try:
            return self.func(tool_input)
        except Exception as exc:
            return f"[MOCK TOOL ERROR] {self.name}: {exc}"


class _MockAgent:
    """Mock agent for tool-use without LangChain."""

    def __init__(self, tools: List[Any], llm: Optional[Any] = None) -> None:
        self.tools: Dict[str, Any] = {t.name if hasattr(t, 'name') else str(i): t for i, t in enumerate(tools)}
        self.llm: Any = llm or _MockLLM(prefix="[MOCK AGENT] ")
        self._execution_log: List[Dict[str, Any]] = []

    def run(self, **kwargs: Any) -> str:
        """Run the mock agent on a task."""
        query = str(kwargs.get("input", kwargs))
        log_entry: Dict[str, Any] = {"input": query, "tool_calls": []}

        # Simple keyword-based tool selection
        selected_tool = None
        for name, tool in self.tools.items():
            if name.lower() in query.lower():
                selected_tool = tool
                break

        if selected_tool is None and self.tools:
            selected_tool = list(self.tools.values())[0]

        if selected_tool is not None:
            try:
                tool_result = selected_tool.run(query) if hasattr(selected_tool, 'run') else str(selected_tool)
                log_entry["tool_calls"].append({
                    "tool": getattr(selected_tool, 'name', str(selected_tool)),
                    "result": tool_result,
                })
                response = f"[MOCK AGENT] Used tool to process: {query[:100]}. Result: {tool_result[:200]}"
            except Exception as exc:
                response = f"[MOCK AGENT] Tool error: {exc}"
        else:
            response = f"[MOCK AGENT] No tool available for: {query[:100]}"

        log_entry["output"] = response
        self._execution_log.append(log_entry)
        return response

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke-style run."""
        result = self.run(**inputs) if isinstance(inputs, dict) else self.run(input=str(inputs))
        return {"output": result}

    def __call__(self, inputs: Any) -> Any:
        """Callable interface."""
        return self.invoke(inputs) if isinstance(inputs, dict) else self.run(input=str(inputs))


class _MockVectorStore:
    """Mock vector store for RAG without embeddings."""

    def __init__(self, documents: Optional[List[str]] = None) -> None:
        self.documents: List[str] = documents or []
        self._index: Dict[int, str] = {i: doc for i, doc in enumerate(self.documents)}

    def add_texts(self, texts: List[str]) -> None:
        """Add texts to the mock vector store."""
        offset = len(self.documents)
        for i, text in enumerate(texts):
            self._index[offset + i] = text
            self.documents.append(text)

    def similarity_search(self, query: str, k: int = 4) -> List[str]:
        """Mock similarity search returning top-k documents."""
        import difflib
        matches = difflib.get_close_matches(query, self.documents, n=k, cutoff=0.1)
        if not matches:
            matches = self.documents[:k]
        return matches

    def as_retriever(self, **kwargs: Any) -> Any:
        """Return a mock retriever interface."""
        return _MockRetriever(self, **kwargs)


class _MockRetriever:
    """Mock retriever for document retrieval."""

    def __init__(self, vector_store: _MockVectorStore, **kwargs: Any) -> None:
        self.vector_store = vector_store
        self.search_kwargs = kwargs

    def get_relevant_documents(self, query: str) -> List[str]:
        """Get relevant documents for a query."""
        k = self.search_kwargs.get('search_kwargs', {}).get('k', 4)
        return self.vector_store.similarity_search(query, k=k)

    def invoke(self, query: str) -> List[str]:
        """Invoke-style interface."""
        return self.get_relevant_documents(query)


class _MockMemory:
    """Mock conversation memory."""

    def __init__(self, window_size: int = 5) -> None:
        self.buffer: List[Dict[str, str]] = []
        self.window_size: int = window_size

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        """Save a turn of conversation."""
        inp = str(inputs.get("input", str(inputs)))
        out = str(outputs.get("output", str(outputs)))
        self.buffer.append({"input": inp, "output": out})
        if len(self.buffer) > self.window_size:
            self.buffer.pop(0)

    def load_memory_variables(self, inputs: Any = None) -> Dict[str, Any]:
        """Load conversation history as variables."""
        history = "\n".join([f"Human: {m['input']}\nAI: {m['output']}" for m in self.buffer])
        return {"history": history}

    def add(self, user_msg: str, ai_msg: str) -> None:
        """Add a conversation turn directly."""
        self.save_context({"input": user_msg}, {"output": ai_msg})

    def clear(self) -> None:
        """Clear the conversation buffer."""
        self.buffer.clear()


# ---------------------------------------------------------------------------
# LangChainBridge
# ---------------------------------------------------------------------------

class LangChainBridge:
    """
    Unified LangChain integration bridge for JARVIS BRAINIAC.

    Provides factory methods for creating chains, agents, RAG pipelines,
    and memory-backed conversations. When LangChain is not installed,
    all methods return fully-functional mock implementations.

    Attributes:
        available (bool): Whether the real LangChain library is installed.
        default_llm: Default LLM instance used when none is provided.
    """

    def __init__(
        self,
        default_llm: Optional[Any] = None,
        verbose: bool = True,
    ) -> None:
        """
        Initialize the LangChain bridge.

        Args:
            default_llm: Optional default LLM to use for all operations.
                         If LangChain is unavailable, a mock LLM is used.
            verbose: Whether to log verbose output.
        """
        self.available: bool = _LANGCHAIN_AVAILABLE
        self.verbose: bool = verbose
        self._default_llm: Any = default_llm
        self._chains: Dict[str, Any] = {}
        self._agents: Dict[str, Any] = {}
        self._memories: Dict[str, Any] = {}
        self._vector_stores: Dict[str, Any] = {}
        logger.info("LangChainBridge initialized (available=%s)", self.available)

    # -- internal helpers ----------------------------------------------------

    def _get_llm(self, llm: Optional[Any] = None) -> Any:
        """Resolve the LLM to use, falling back to default or mock."""
        resolved = llm or self._default_llm
        if resolved is None:
            if self.available:
                # Try to create a default LLM from environment
                resolved = self._create_default_llm()
            else:
                resolved = _MockLLM()
        return resolved

    def _create_default_llm(self) -> Any:
        """Attempt to create a default LLM from environment configuration."""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(temperature=0.7, model_name="gpt-4o")
            except Exception:
                pass
            try:
                from langchain.chat_models import ChatOpenAI
                return ChatOpenAI(temperature=0.7, model_name="gpt-4")
            except Exception:
                pass
        # Try Azure
        azure_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        if azure_key:
            try:
                from langchain_openai import AzureChatOpenAI
                return AzureChatOpenAI(temperature=0.7)
            except Exception:
                pass
        # Local models
        try:
            from langchain.llms import Ollama
            return Ollama(model="llama2")
        except Exception:
            pass
        logger.warning("No LLM configured; returning mock LLM.")
        return _MockLLM()

    def _log(self, msg: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            logger.info("[LangChainBridge] %s", msg)

    # -- public API ----------------------------------------------------------

    def create_chain(
        self,
        prompt_template: str,
        llm: Optional[Any] = None,
        input_variables: Optional[List[str]] = None,
        chain_name: str = "default_chain",
    ) -> Any:
        """
        Create a LangChain LLMChain (or mock equivalent).

        Args:
            prompt_template: The prompt template string with {variable} placeholders.
            llm: Optional LLM instance. Falls back to default_llm then auto-detected.
            input_variables: List of input variable names. Auto-detected if None.
            chain_name: Identifier for storing/retrieving the chain.

        Returns:
            An LLMChain instance or mock chain object.

        Example:
            >>> bridge = LangChainBridge()
            >>> chain = bridge.create_chain("Explain {topic} in simple terms")
            >>> result = bridge.run_chain(chain, {"topic": "quantum computing"})
        """
        llm_instance = self._get_llm(llm)

        if input_variables is None:
            import re
            input_variables = re.findall(r"\{(\w+)\}", prompt_template)

        if self.available:
            try:
                prompt = PromptTemplate(
                    input_variables=input_variables,
                    template=prompt_template,
                )
                chain = LLMChain(llm=llm_instance, prompt=prompt, verbose=self.verbose)
                self._chains[chain_name] = chain
                self._log(f"Created LLMChain '{chain_name}' with vars={input_variables}")
                return chain
            except Exception as exc:
                logger.error("Failed to create LLMChain: %s. Using mock.", exc)

        # Mock fallback
        mock_chain = _MockChain(prompt_template, llm=llm_instance)
        self._chains[chain_name] = mock_chain
        self._log(f"Created mock chain '{chain_name}' (LangChain unavailable)")
        return mock_chain

    def create_agent(
        self,
        tools: List[Any],
        llm: Optional[Any] = None,
        agent_type: str = "zero-shot-react-description",
        agent_name: str = "default_agent",
    ) -> Any:
        """
        Create a LangChain agent with tool bindings (or mock equivalent).

        Args:
            tools: List of tool objects or dicts with 'name', 'func', 'description'.
            llm: Optional LLM instance.
            agent_type: Agent type identifier string.
            agent_name: Identifier for storing the agent.

        Returns:
            An AgentExecutor or mock agent object.

        Example:
            >>> tools = [{"name": "calculator", "func": lambda x: str(eval(x)), "description": "Math"}]
            >>> agent = bridge.create_agent(tools)
            >>> result = bridge.run_chain(agent, {"input": "What is 15 * 23?"})
        """
        llm_instance = self._get_llm(llm)

        # Normalize tools
        normalized_tools: List[Any] = []
        for t in tools:
            if isinstance(t, dict):
                normalized_tools.append(
                    Tool(
                        name=t["name"],
                        func=t["func"],
                        description=t.get("description", "No description"),
                    ) if self.available else _MockTool(t["name"], t["func"], t.get("description", ""))
                )
            else:
                normalized_tools.append(t)

        if self.available:
            try:
                agent = initialize_agent(
                    tools=normalized_tools,
                    llm=llm_instance,
                    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                    verbose=self.verbose,
                    handle_parsing_errors=True,
                    max_iterations=10,
                )
                self._agents[agent_name] = agent
                self._log(f"Created agent '{agent_name}' with {len(normalized_tools)} tools")
                return agent
            except Exception as exc:
                logger.error("Failed to create agent: %s. Using mock.", exc)

        # Mock fallback
        mock_agent = _MockAgent(normalized_tools, llm=llm_instance)
        self._agents[agent_name] = mock_agent
        self._log(f"Created mock agent '{agent_name}' with {len(normalized_tools)} tools")
        return mock_agent

    def create_rag_chain(
        self,
        documents: List[Union[str, Dict[str, Any]]],
        llm: Optional[Any] = None,
        embedding_model: Optional[Any] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        top_k: int = 4,
        chain_name: str = "default_rag",
    ) -> Any:
        """
        Create a Retrieval-Augmented Generation (RAG) pipeline.

        Args:
            documents: List of document strings or dicts with 'page_content' and 'metadata'.
            llm: Optional LLM instance.
            embedding_model: Optional embeddings model. Auto-detected if None.
            chunk_size: Size of text chunks for splitting.
            chunk_overlap: Overlap between chunks.
            top_k: Number of documents to retrieve.
            chain_name: Identifier for the RAG chain.

        Returns:
            A RetrievalQA chain or mock RAG handler.

        Example:
            >>> docs = ["AI is transforming industries.", "ML models learn from data."]
            >>> rag = bridge.create_rag_chain(docs)
            >>> result = bridge.run_chain(rag, {"query": "What is AI?"})
        """
        llm_instance = self._get_llm(llm)

        # Normalize documents
        doc_texts: List[str] = []
        for doc in documents:
            if isinstance(doc, str):
                doc_texts.append(doc)
            elif isinstance(doc, dict):
                doc_texts.append(doc.get("page_content", str(doc)))
            else:
                doc_texts.append(str(doc))

        if self.available:
            try:
                # Get embeddings
                embeddings = embedding_model
                if embeddings is None:
                    try:
                        from langchain_openai import OpenAIEmbeddings
                        embeddings = OpenAIEmbeddings()
                    except Exception:
                        try:
                            from langchain.embeddings import HuggingFaceEmbeddings
                            embeddings = HuggingFaceEmbeddings()
                        except Exception:
                            logger.warning("No embedding model found; using mock RAG.")
                            raise RuntimeError("No embeddings available")

                # Split and index
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                from langchain.schema import Document
                docs_list = [Document(page_content=t) for t in doc_texts]
                splits = text_splitter.split_documents(docs_list)
                vectorstore = FAISS.from_documents(splits, embeddings)
                retriever = vectorstore.as_retriever(search_kwargs={"k": top_k})
                rag_chain = RetrievalQA.from_chain_type(
                    llm=llm_instance,
                    chain_type="stuff",
                    retriever=retriever,
                    return_source_documents=True,
                    verbose=self.verbose,
                )
                self._vector_stores[chain_name] = vectorstore
                self._chains[chain_name] = rag_chain
                self._log(f"Created RAG chain '{chain_name}' with {len(splits)} chunks")
                return rag_chain
            except Exception as exc:
                logger.error("Failed to create RAG chain: %s. Using mock.", exc)

        # Mock fallback
        mock_store = _MockVectorStore(doc_texts)
        self._vector_stores[chain_name] = mock_store

        class _MockRAG:
            """Mock RAG chain handler."""

            def __init__(self, store: _MockVectorStore, llm: Any, top_k: int) -> None:
                self.store = store
                self.llm = llm
                self.top_k = top_k

            def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                """Run mock RAG retrieval and generation."""
                query = inputs.get("query", str(inputs))
                retrieved = self.store.similarity_search(query, k=self.top_k)
                context = "\n".join(retrieved)
                prompt = f"Context: {context}\nQuestion: {query}\nAnswer:"
                answer = self.llm.predict(prompt) if hasattr(self.llm, 'predict') else str(self.llm)
                return {
                    "result": answer,
                    "source_documents": retrieved,
                }

            def run(self, query: str) -> str:
                """Simple run interface."""
                result = self.invoke({"query": query})
                return str(result.get("result", ""))

        mock_rag = _MockRAG(mock_store, llm_instance, top_k)
        self._chains[chain_name] = mock_rag
        self._log(f"Created mock RAG chain '{chain_name}' with {len(doc_texts)} documents")
        return mock_rag

    def create_memory_chain(
        self,
        llm: Optional[Any] = None,
        memory_key: str = "history",
        window_size: int = 5,
        chain_name: str = "default_memory",
    ) -> Any:
        """
        Create a conversational chain with memory (or mock equivalent).

        Args:
            llm: Optional LLM instance.
            memory_key: Key used for memory variable in prompts.
            window_size: Number of conversation turns to remember.
            chain_name: Identifier for the memory chain.

        Returns:
            A conversational chain or mock memory-backed chain.

        Example:
            >>> chat = bridge.create_memory_chain()
            >>> r1 = bridge.run_chain(chat, {"input": "My name is Alice"})
            >>> r2 = bridge.run_chain(chat, {"input": "What's my name?"})
        """
        llm_instance = self._get_llm(llm)

        if self.available:
            try:
                memory = ConversationBufferWindowMemory(
                    memory_key=memory_key,
                    k=window_size,
                    return_messages=True,
                )
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="You are a helpful assistant."),
                    *(memory.memory_key,),
                    HumanMessage(content="{input}"),
                ])
                from langchain.chains import ConversationChain
                conv_chain = ConversationChain(
                    llm=llm_instance,
                    memory=memory,
                    verbose=self.verbose,
                )
                self._memories[chain_name] = memory
                self._chains[chain_name] = conv_chain
                self._log(f"Created memory chain '{chain_name}' with window={window_size}")
                return conv_chain
            except Exception as exc:
                logger.error("Failed to create memory chain: %s. Using mock.", exc)

        # Mock fallback
        mock_memory = _MockMemory(window_size=window_size)
        self._memories[chain_name] = mock_memory

        class _MockMemoryChain:
            """Mock conversational chain with memory."""

            def __init__(self, llm: Any, memory: _MockMemory, memory_key: str) -> None:
                self.llm = llm
                self.memory = memory
                self.memory_key = memory_key
                self.system_prompt = "You are a helpful assistant."

            def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                """Run the memory chain."""
                user_input = str(inputs.get("input", str(inputs)))
                mem_vars = self.memory.load_memory_variables()
                history = mem_vars.get("history", "")
                prompt = f"{self.system_prompt}\n{history}\nHuman: {user_input}\nAI:"
                response = (
                    self.llm.predict(prompt)
                    if hasattr(self.llm, 'predict')
                    else str(self.llm)
                )
                self.memory.save_context({"input": user_input}, {"output": response})
                return {"output": response, "text": response}

            def run(self, input_text: str) -> str:
                """Simple run interface."""
                result = self.invoke({"input": input_text})
                return str(result.get("output", ""))

            def predict(self, input_text: str) -> str:
                """Predict interface."""
                return self.run(input_text)

        mock_chain = _MockMemoryChain(llm_instance, mock_memory, memory_key)
        self._chains[chain_name] = mock_chain
        self._log(f"Created mock memory chain '{chain_name}' with window={window_size}")
        return mock_chain

    def run_chain(self, chain: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute any chain with the given inputs.

        Args:
            chain: The chain/agent to execute (created by this bridge).
            inputs: Dictionary of input variables.

        Returns:
            Execution result as a dictionary.

        Example:
            >>> chain = bridge.create_chain("Summarize: {text}")
            >>> result = bridge.run_chain(chain, {"text": "Long article here..."})
            >>> print(result["output"])
        """
        self._log(f"Running chain with inputs: {list(inputs.keys())}")
        try:
            if hasattr(chain, 'invoke'):
                result = chain.invoke(inputs)
            elif hasattr(chain, 'run'):
                raw = chain.run(**inputs)
                result = {"output": raw, "text": raw}
            elif callable(chain):
                raw = chain(inputs)
                result = raw if isinstance(raw, dict) else {"output": raw, "text": raw}
            else:
                result = {"output": str(chain), "text": str(chain)}

            # Ensure dict return
            if not isinstance(result, dict):
                result = {"output": result, "text": str(result)}

            self._log(f"Chain execution complete. Output length: {len(str(result.get('output', '')))}")
            return result

        except Exception as exc:
            logger.error("Chain execution failed: %s", exc)
            error_result = {"output": f"[ERROR] {exc}", "text": str(exc), "error": str(exc)}
            return error_result

    def add_tool(
        self,
        name: str,
        func: Callable[..., str],
        description: str,
    ) -> Any:
        """
        Create a LangChain Tool (or mock equivalent).

        Args:
            name: Tool name identifier.
            func: Callable function for the tool.
            description: Description of what the tool does.

        Returns:
            A Tool or mock tool object.
        """
        if self.available:
            try:
                return Tool(name=name, func=func, description=description)
            except Exception as exc:
                logger.error("Failed to create tool: %s. Using mock.", exc)
        return _MockTool(name, func, description)

    def create_embedding(self, texts: List[str]) -> Any:
        """
        Create embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            Embedding vectors or mock representations.
        """
        if self.available:
            try:
                from langchain_openai import OpenAIEmbeddings
                embeddings = OpenAIEmbeddings()
                return embeddings.embed_documents(texts)
            except Exception as exc:
                logger.error("Failed to create embeddings: %s. Using mock.", exc)

        # Mock: return random vectors
        import random
        return [[random.random() for _ in range(128)] for _ in texts]

    def get_chain(self, name: str) -> Optional[Any]:
        """Retrieve a stored chain by name."""
        return self._chains.get(name)

    def get_agent(self, name: str) -> Optional[Any]:
        """Retrieve a stored agent by name."""
        return self._agents.get(name)

    def get_memory(self, name: str) -> Optional[Any]:
        """Retrieve a stored memory by name."""
        return self._memories.get(name)

    def clear_memory(self, name: str = "default_memory") -> None:
        """Clear the conversation memory for a named memory chain."""
        mem = self._memories.get(name)
        if mem and hasattr(mem, 'clear'):
            mem.clear()
        self._log(f"Cleared memory '{name}'")

    def list_chains(self) -> List[str]:
        """List all registered chain names."""
        return list(self._chains.keys())

    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    def health_check(self) -> Dict[str, Any]:
        """
        Return health status of the LangChain bridge.

        Returns:
            Dict with availability, chain count, agent count, etc.
        """
        return {
            "available": self.available,
            "chains": len(self._chains),
            "agents": len(self._agents),
            "memories": len(self._memories),
            "vector_stores": len(self._vector_stores),
            "chain_names": self.list_chains(),
            "agent_names": self.list_agents(),
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_langchain_bridge(
    default_llm: Optional[Any] = None,
    verbose: bool = True,
) -> LangChainBridge:
    """
    Factory function to create a LangChainBridge instance.

    Args:
        default_llm: Optional default LLM instance.
        verbose: Enable verbose logging.

    Returns:
        Configured LangChainBridge instance.

    Example:
        >>> bridge = get_langchain_bridge()
        >>> chain = bridge.create_chain("Hello {name}")
    """
    return LangChainBridge(default_llm=default_llm, verbose=verbose)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def quick_chain(prompt_template: str, inputs: Dict[str, Any], llm: Optional[Any] = None) -> str:
    """
    One-shot chain creation and execution.

    Args:
        prompt_template: Prompt template string.
        inputs: Input variable dict.
        llm: Optional LLM override.

    Returns:
        Chain output string.
    """
    bridge = get_langchain_bridge(default_llm=llm, verbose=False)
    chain = bridge.create_chain(prompt_template, llm=llm)
    result = bridge.run_chain(chain, inputs)
    return str(result.get("output", result.get("text", "")))


def quick_rag(documents: List[str], query: str, llm: Optional[Any] = None) -> Dict[str, Any]:
    """
    One-shot RAG pipeline: index documents and query.

    Args:
        documents: List of document text strings.
        query: Query string.
        llm: Optional LLM override.

    Returns:
        Dict with 'result' and 'source_documents'.
    """
    bridge = get_langchain_bridge(default_llm=llm, verbose=False)
    rag = bridge.create_rag_chain(documents, llm=llm)
    return bridge.run_chain(rag, {"query": query})


def quick_chat(message: str, memory_name: str = "chat", llm: Optional[Any] = None) -> str:
    """
    One-shot chat with persistent memory.

    Args:
        message: User message.
        memory_name: Memory session identifier.
        llm: Optional LLM override.

    Returns:
        Assistant response string.
    """
    bridge = get_langchain_bridge(default_llm=llm, verbose=False)
    existing = bridge.get_chain(memory_name)
    if existing is None:
        existing = bridge.create_memory_chain(chain_name=memory_name)
    result = bridge.run_chain(existing, {"input": message})
    return str(result.get("output", ""))


# ---------------------------------------------------------------------------
# __main__ quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_langchain_bridge(verbose=True)

    # Health check
    print("Health:", bridge.health_check())

    # Test basic chain
    chain = bridge.create_chain("Explain {topic} simply")
    result = bridge.run_chain(chain, {"topic": "neural networks"})
    print("Chain result:", result)

    # Test agent
    calc_tool = bridge.add_tool("calculator", lambda x: str(eval(x)), "Evaluate math expressions")
    agent = bridge.create_agent([calc_tool])
    result = bridge.run_chain(agent, {"input": "Calculate 15 * 23"})
    print("Agent result:", result)

    # Test RAG
    docs = ["AI is a field of computer science.", "Machine learning is a subset of AI."]
    rag = bridge.create_rag_chain(docs)
    result = bridge.run_chain(rag, {"query": "What is AI?"})
    print("RAG result:", result)

    # Test memory chain
    chat = bridge.create_memory_chain()
    r1 = bridge.run_chain(chat, {"input": "My name is Jarvis"})
    print("Memory turn 1:", r1)
    r2 = bridge.run_chain(chat, {"input": "What is my name?"})
    print("Memory turn 2:", r2)
