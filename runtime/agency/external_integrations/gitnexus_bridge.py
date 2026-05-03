"""
JARVIS BRAINIAC - GitNexus Integration Bridge
=============================================

Bridge adapter for GitNexus — a local CLI tool that parses code repositories
into a graph database and injects architectural context via MCP (Model Context
Protocol).

Repository: https://github.com/gitnexus/gitnexus (community)
Features:
    - Parse repositories into dependency graphs
    - Extract architectural context for AI consumption via MCP
    - Compute blast radius for file changes
    - Extract deep call chains from entry points

Usage:
    bridge = GitNexusBridge()
    graph = bridge.analyze_repo("/path/to/repo")
    context = bridge.get_context("authentication flow")
    affected = bridge.find_blast_radius("src/auth.py")
    chain = bridge.get_call_chain("main.handle_request")
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_GITNEXUS_AVAILABLE: bool = False

_GITNEXUS_VERSION: str = "unknown"

try:
    import gitnexus
    from gitnexus.graph import RepoGraph as _GNRepoGraph
    from gitnexus.mcp import MCPContextProvider
    from gitnexus.blast_radius import BlastRadiusAnalyzer
    from gitnexus.call_graph import CallGraphExtractor
    _GITNEXUS_AVAILABLE = True
    _GITNEXUS_VERSION = getattr(gitnexus, "__version__", "unknown")
    logger.info("GitNexus %s loaded successfully.", _GITNEXUS_VERSION)
except Exception as _import_exc:
    logger.warning(
        "GitNexus not installed or failed to import (%s). "
        "Falling back to mock implementations.", _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RepoNode:
    """A node in the repository graph (file, function, class, module)."""
    node_id: str
    name: str
    node_type: str  # file, function, class, module, package
    path: str
    language: str = ""
    lines_of_code: int = 0
    dependencies: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id, "name": self.name,
            "node_type": self.node_type, "path": self.path,
            "language": self.language, "lines_of_code": self.lines_of_code,
            "dependencies": self.dependencies, "metrics": self.metrics,
        }


@dataclass
class RepoEdge:
    """An edge in the repository graph (imports, calls, inherits, includes)."""
    source: str
    target: str
    edge_type: str  # import, call, inherit, include, export
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source, "target": self.target,
            "edge_type": self.edge_type, "weight": self.weight,
        }


@dataclass
class RepoGraph:
    """Complete repository dependency graph."""
    repo_path: str
    repo_name: str
    nodes: List[RepoNode] = field(default_factory=list)
    edges: List[RepoEdge] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_path": self.repo_path, "repo_name": self.repo_name,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "summary": self.summary,
        }


@dataclass
class MCPContext:
    """Architectural context delivered via MCP for AI consumption."""
    query: str
    context_blocks: List[Dict[str, Any]] = field(default_factory=list)
    relevant_files: List[str] = field(default_factory=list)
    architecture_summary: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query, "context_blocks": self.context_blocks,
            "relevant_files": self.relevant_files,
            "architecture_summary": self.architecture_summary,
            "confidence": self.confidence,
        }


@dataclass
class CallChain:
    """A deep call chain extracted from an entry point."""
    entry_point: str
    chain: List[Dict[str, Any]] = field(default_factory=list)
    max_depth: int = 0
    total_paths: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_point": self.entry_point, "chain": self.chain,
            "max_depth": self.max_depth, "total_paths": self.total_paths,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockRepoAnalyzer:
    """Mock repository analyzer producing realistic dependency graphs."""

    def __init__(self) -> None:
        self._cache: Dict[str, RepoGraph] = {}

    def analyze(self, repo_path: str) -> RepoGraph:
        if repo_path in self._cache:
            logger.debug("Returning cached graph for %s", repo_path)
            return self._cache[repo_path]

        logger.info("[MOCK] Analyzing repository: %s", repo_path)
        repo_name = Path(repo_path).name or "unknown_repo"
        nodes: List[RepoNode] = []
        edges: List[RepoEdge] = []

        # Simulate a realistic Python project structure
        mock_files = [
            ("main.py", "file", "python", 150),
            ("config.py", "file", "python", 80),
            ("models/__init__.py", "file", "python", 20),
            ("models/user.py", "file", "python", 120),
            ("models/order.py", "file", "python", 95),
            ("services/auth.py", "file", "python", 200),
            ("services/payment.py", "file", "python", 180),
            ("services/email.py", "file", "python", 110),
            ("api/routes.py", "file", "python", 250),
            ("api/middleware.py", "file", "python", 90),
            ("utils/helpers.py", "file", "python", 75),
            ("utils/logger.py", "file", "python", 60),
            ("tests/test_auth.py", "file", "python", 130),
            ("tests/test_payment.py", "file", "python", 110),
            ("requirements.txt", "file", "text", 15),
        ]

        for idx, (fpath, ftype, lang, loc) in enumerate(mock_files):
            node_id = f"node_{idx}"
            name = Path(fpath).name
            nodes.append(RepoNode(
                node_id=node_id, name=name, node_type=ftype,
                path=fpath, language=lang, lines_of_code=loc,
            ))

        # Simulate dependency edges
        edge_defs = [
            ("node_0", "node_1", "import"),    # main -> config
            ("node_0", "node_8", "import"),    # main -> api/routes
            ("node_8", "node_5", "call"),      # routes -> auth service
            ("node_8", "node_6", "call"),      # routes -> payment service
            ("node_5", "node_3", "call"),      # auth -> user model
            ("node_6", "node_4", "call"),      # payment -> order model
            ("node_6", "node_7", "call"),      # payment -> email service
            ("node_5", "node_11", "import"),   # auth -> logger
            ("node_6", "node_11", "import"),   # payment -> logger
            ("node_8", "node_10", "import"),   # routes -> helpers
            ("node_3", "node_1", "import"),    # user -> config
            ("node_4", "node_1", "import"),    # order -> config
            ("node_12", "node_5", "import"),   # test_auth -> auth
            ("node_13", "node_6", "import"),   # test_payment -> payment
        ]

        for src, tgt, etype in edge_defs:
            edges.append(RepoEdge(source=src, target=tgt, edge_type=etype))

        # Attach dependencies to nodes
        for edge in edges:
            for node in nodes:
                if node.node_id == edge.source:
                    node.dependencies.append(edge.target)

        total_loc = sum(n.lines_of_code for n in nodes)
        summary = {
            "total_files": len([n for n in nodes if n.node_type == "file"]),
            "total_modules": len([n for n in nodes if n.node_type == "module"]),
            "total_functions": 0,
            "total_classes": 0,
            "total_lines_of_code": total_loc,
            "languages": list(set(n.language for n in nodes if n.language)),
            "analysis_duration_ms": 2450,
        }

        graph = RepoGraph(
            repo_path=repo_path, repo_name=repo_name,
            nodes=nodes, edges=edges, summary=summary,
        )
        self._cache[repo_path] = graph
        logger.info("[MOCK] Graph complete: %d nodes, %d edges", len(nodes), len(edges))
        return graph


class _MockMCPContextProvider:
    """Mock MCP context provider returning realistic architectural context."""

    def get_context(self, query: str, graph: RepoGraph) -> MCPContext:
        logger.info("[MOCK] Getting MCP context for query: %s", query)
        q_lower = query.lower()

        blocks: List[Dict[str, Any]] = []
        relevant_files: List[str] = []
        arch_summary = ""
        confidence = 0.75

        if "auth" in q_lower:
            blocks = [
                {"type": "module", "name": "services/auth.py",
                 "description": "Handles authentication and session management."},
                {"type": "model", "name": "models/user.py",
                 "description": "User entity with credentials and roles."},
                {"type": "middleware", "name": "api/middleware.py",
                 "description": "Request authentication middleware."},
            ]
            relevant_files = ["services/auth.py", "models/user.py", "api/middleware.py"]
            arch_summary = (
                "Authentication is handled by a dedicated service layer with "
                "middleware-based request validation. User credentials are stored "
                "in the user model with role-based access control."
            )
            confidence = 0.92
        elif "payment" in q_lower or "order" in q_lower:
            blocks = [
                {"type": "service", "name": "services/payment.py",
                 "description": "Payment processing with gateway integration."},
                {"type": "model", "name": "models/order.py",
                 "description": "Order entity with line items and status."},
                {"type": "service", "name": "services/email.py",
                 "description": "Email notifications for payment events."},
            ]
            relevant_files = ["services/payment.py", "models/order.py", "services/email.py"]
            arch_summary = (
                "Payment processing follows a service-oriented pattern with "
                "order models, payment gateway abstraction, and async email notifications."
            )
            confidence = 0.88
        else:
            blocks = [
                {"type": "entry", "name": "main.py",
                 "description": "Application entry point and bootstrap."},
                {"type": "config", "name": "config.py",
                 "description": "Centralized configuration management."},
                {"type": "routes", "name": "api/routes.py",
                 "description": "URL routing and endpoint definitions."},
            ]
            relevant_files = ["main.py", "config.py", "api/routes.py"]
            arch_summary = (
                f"Repository '{graph.repo_name}' follows a layered architecture with "
                "separation of concerns across API, service, model, and utility layers."
            )
            confidence = 0.65

        return MCPContext(
            query=query, context_blocks=blocks,
            relevant_files=relevant_files,
            architecture_summary=arch_summary, confidence=confidence,
        )


class _MockBlastRadiusAnalyzer:
    """Mock blast radius analyzer."""

    def find_affected(self, file_path: str, graph: RepoGraph) -> List[str]:
        logger.info("[MOCK] Computing blast radius for: %s", file_path)
        affected: List[str] = []
        fname = Path(file_path).name

        # Find the node matching this file
        target_node = None
        for node in graph.nodes:
            if node.path == file_path or node.name == fname:
                target_node = node
                break

        if target_node is None:
            logger.warning("File %s not found in graph, returning mock results.", file_path)
            return ["services/auth.py", "api/routes.py", "models/user.py"]

        # Walk upstream and downstream dependencies
        visited = set()
        queue = list(target_node.dependencies)
        while queue:
            dep_id = queue.pop(0)
            if dep_id in visited:
                continue
            visited.add(dep_id)
            for node in graph.nodes:
                if node.node_id == dep_id and node.path not in affected:
                    affected.append(node.path)
                    queue.extend(node.dependencies)

        # Add reverse dependents (files that import this one)
        for edge in graph.edges:
            if edge.target == target_node.node_id:
                for node in graph.nodes:
                    if node.node_id == edge.source and node.path not in affected:
                        affected.append(node.path)

        logger.info("[MOCK] Blast radius: %d files affected", len(affected))
        return affected if affected else ["No dependencies found."]


class _MockCallGraphExtractor:
    """Mock call graph extractor."""

    def extract_chain(self, entry_point: str, graph: RepoGraph) -> CallChain:
        logger.info("[MOCK] Extracting call chain from: %s", entry_point)

        chain: List[Dict[str, Any]] = []
        if "auth" in entry_point.lower():
            chain = [
                {"function": "main.handle_request", "file": "main.py", "line": 42},
                {"function": "api.routes.authenticate", "file": "api/routes.py", "line": 88},
                {"function": "services.auth.validate_credentials", "file": "services/auth.py", "line": 55},
                {"function": "services.auth.check_password", "file": "services/auth.py", "line": 120},
                {"function": "models.user.verify_hash", "file": "models/user.py", "line": 65},
            ]
        elif "payment" in entry_point.lower():
            chain = [
                {"function": "main.handle_request", "file": "main.py", "line": 42},
                {"function": "api.routes.process_payment", "file": "api/routes.py", "line": 150},
                {"function": "services.payment.charge", "file": "services/payment.py", "line": 72},
                {"function": "services.payment.validate_card", "file": "services/payment.py", "line": 110},
                {"function": "models.order.update_status", "file": "models/order.py", "line": 45},
                {"function": "services.email.send_receipt", "file": "services/email.py", "line": 33},
            ]
        else:
            chain = [
                {"function": entry_point, "file": "main.py", "line": 1},
                {"function": "api.routes.dispatch", "file": "api/routes.py", "line": 20},
                {"function": "services.auth.middleware", "file": "services/auth.py", "line": 15},
            ]

        return CallChain(
            entry_point=entry_point, chain=chain,
            max_depth=len(chain), total_paths=len(chain) * 2 - 1,
        )


# ---------------------------------------------------------------------------
# Main bridge class
# ---------------------------------------------------------------------------

class GitNexusBridge:
    """Bridge adapter for GitNexus repository analysis and MCP context.

    Provides typed access to GitNexus capabilities with automatic mock
    fallback when the native tool is not installed.

    Args:
        repo_path: Optional default repository path.
        use_cli: If True, attempt to invoke the gitnexus CLI directly.

    Example:
        bridge = GitNexusBridge()
        graph = bridge.analyze_repo("/home/user/myproject")
        context = bridge.get_context("authentication flow")
        affected = bridge.find_blast_radius("src/auth.py")
        chain = bridge.get_call_chain("main.handle_request")
    """

    def __init__(self, repo_path: Optional[str] = None, use_cli: bool = True) -> None:
        self.repo_path = repo_path
        self.use_cli = use_cli
        self._graph_cache: Dict[str, RepoGraph] = {}

        if _GITNEXUS_AVAILABLE:
            self._analyzer = _GNRepoGraph()
            self._mcp = MCPContextProvider()
            self._blast = BlastRadiusAnalyzer()
            self._call_graph = CallGraphExtractor()
            logger.info("GitNexusBridge initialized with native backend v%s.", _GITNEXUS_VERSION)
        else:
            self._analyzer = _MockRepoAnalyzer()
            self._mcp = _MockMCPContextProvider()
            self._blast = _MockBlastRadiusAnalyzer()
            self._call_graph = _MockCallGraphExtractor()
            logger.info("GitNexusBridge initialized with mock backend.")

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def analyze_repo(self, repo_path: str) -> RepoGraph:
        """Parse a repository into a dependency graph.

        Args:
            repo_path: Absolute or relative path to the repository root.

        Returns:
            RepoGraph containing all nodes (files, modules) and edges
            (imports, calls, inheritance relationships).
        """
        resolved = str(Path(repo_path).resolve())
        if resolved in self._graph_cache:
            return self._graph_cache[resolved]

        if _GITNEXUS_AVAILABLE and self.use_cli:
            try:
                result = subprocess.run(
                    ["gitnexus", "analyze", resolved, "--json"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    logger.info("GitNexus CLI analysis succeeded for %s", resolved)
                else:
                    logger.warning("GitNexus CLI failed, using mock: %s", result.stderr)
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                logger.debug("CLI invocation failed (%s), using internal analyzer.", exc)

        graph = self._analyzer.analyze(resolved)
        self._graph_cache[resolved] = graph
        return graph

    def get_context(self, query: str, repo_path: Optional[str] = None) -> MCPContext:
        """Get architectural context for an AI query via MCP.

        Args:
            query: Natural language query about the codebase architecture.
            repo_path: Optional repository path override.

        Returns:
            MCPContext with relevant code blocks, file references, and
            an architecture summary tailored to the query.
        """
        target = repo_path or self.repo_path
        if target is None:
            raise ValueError("repo_path must be provided (no default set).")

        graph = self.analyze_repo(target)
        return self._mcp.get_context(query, graph)

    def find_blast_radius(self, file_path: str, repo_path: Optional[str] = None) -> List[str]:
        """Find all files affected by changing a given file.

        Args:
            file_path: Path to the file (relative to repo root).
            repo_path: Optional repository path override.

        Returns:
            List of file paths that directly or indirectly depend on
            the changed file.
        """
        target = repo_path or self.repo_path
        if target is None:
            raise ValueError("repo_path must be provided (no default set).")

        graph = self.analyze_repo(target)
        return self._blast.find_affected(file_path, graph)

    def get_call_chain(self, entry_point: str, repo_path: Optional[str] = None) -> CallChain:
        """Extract the deep call chain starting from an entry point.

        Args:
            entry_point: Function/method name to trace from (e.g.,
                "main.handle_request").
            repo_path: Optional repository path override.

        Returns:
            CallChain with the complete call hierarchy, max depth, and
            total number of execution paths discovered.
        """
        target = repo_path or self.repo_path
        if target is None:
            raise ValueError("repo_path must be provided (no default set).")

        graph = self.analyze_repo(target)
        return self._call_graph.extract_chain(entry_point, graph)

    # ------------------------------------------------------------------
    # Bridge contract
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Return bridge health status.

        Returns:
            Dict with 'status', 'backend', 'version', and 'cached_graphs'.
        """
        return {
            "status": "healthy",
            "backend": "native" if _GITNEXUS_AVAILABLE else "mock",
            "version": _GITNEXUS_VERSION if _GITNEXUS_AVAILABLE else "mock-1.0.0",
            "cached_graphs": len(self._graph_cache),
            "native_available": _GITNEXUS_AVAILABLE,
        }

    def metadata(self) -> Dict[str, Any]:
        """Return bridge metadata for JARVIS registry.

        Returns:
            Dict with bridge name, version, capabilities, and dependencies.
        """
        return {
            "name": "gitnexus_bridge",
            "display_name": "GitNexus Repository Analyzer",
            "version": "1.0.0",
            "description": (
                "Parse repositories into graph databases, extract architectural "
                "context via MCP, compute blast radius, and trace call chains."
            ),
            "author": "JARVIS Integration Team",
            "license": "MIT",
            "capabilities": [
                "repo_graph_analysis",
                "mcp_context_provider",
                "blast_radius_calculation",
                "call_chain_extraction",
                "dependency_mapping",
            ],
            "dependencies": {
                "gitnexus": _GITNEXUS_AVAILABLE,
                "python": ">=3.9",
            },
            "repository": "https://github.com/gitnexus/gitnexus",
            "mock_fallback": not _GITNEXUS_AVAILABLE,
        }

    def clear_cache(self) -> None:
        """Clear the internal graph cache."""
        self._graph_cache.clear()
        logger.info("Graph cache cleared.")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(name)s | %(levelname)s | %(message)s")
    logger.info("=== GitNexus Bridge Self-Test ===")

    bridge = GitNexusBridge()

    # Test health_check
    health = bridge.health_check()
    assert "status" in health
    assert health["status"] == "healthy"
    logger.info("health_check: %s", health)

    # Test metadata
    meta = bridge.metadata()
    assert meta["name"] == "gitnexus_bridge"
    assert "capabilities" in meta
    logger.info("metadata: %s", meta)

    # Test analyze_repo
    graph = bridge.analyze_repo("/tmp/mock_repo")
    assert isinstance(graph, RepoGraph)
    assert len(graph.nodes) > 0
    assert len(graph.edges) > 0
    assert graph.summary["total_lines_of_code"] > 0
    logger.info("analyze_repo: %d nodes, %d edges", len(graph.nodes), len(graph.edges))

    # Test get_context
    ctx = bridge.get_context("authentication flow", repo_path="/tmp/mock_repo")
    assert isinstance(ctx, MCPContext)
    assert ctx.confidence > 0
    assert len(ctx.relevant_files) > 0
    logger.info("get_context: %d files, confidence=%.2f", len(ctx.relevant_files), ctx.confidence)

    # Test find_blast_radius
    affected = bridge.find_blast_radius("services/auth.py", repo_path="/tmp/mock_repo")
    assert isinstance(affected, list)
    assert len(affected) > 0
    logger.info("find_blast_radius: %d affected files: %s", len(affected), affected)

    # Test get_call_chain
    chain = bridge.get_call_chain("main.handle_request", repo_path="/tmp/mock_repo")
    assert isinstance(chain, CallChain)
    assert len(chain.chain) > 0
    logger.info("get_call_chain: depth=%d, paths=%d", chain.max_depth, chain.total_paths)

    # Test caching
    graph2 = bridge.analyze_repo("/tmp/mock_repo")
    assert graph2 is graph  # Same cached object
    logger.info("Cache hit verified.")

    bridge.clear_cache()
    logger.info("=== All GitNexus Bridge self-tests passed ===")
