"""GitHub Ingestor for JARVIS — autonomous code ingestion pipeline.

Searches GitHub, clones repositories, analyses code with a local LLM,
and hot-swaps discovered capabilities into the JARVIS runtime.

Public API
----------
* :class:`GitHubIngestor`  — production ingestor.
* :class:`MockGitHubIngestor`  — deterministic mock for testing / offline mode.
* :func:`get_github_ingestor`  — factory that picks the right class.

Example::

    from runtime.agency.github_ingestor import get_github_ingestor
    ingestor = get_github_ingestor(github_token=os.getenv("GITHUB_TOKEN"))
    learned = ingestor.ingest("machine learning data pipeline")
    print(f"Learned {len(learned)} new capabilities")
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM import (graceful fallback)
# ---------------------------------------------------------------------------

try:
    from runtime.agency.llm import get_llm_router

    LLM_AVAILABLE = True
except Exception:  # pragma: no cover
    LLM_AVAILABLE = False
    get_llm_router = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CLONE_DIR = "./github_clones"
DEFAULT_SKILLS_DIR = "./jarvis_skills"
GITHUB_API_BASE = "https://api.github.com"
MAX_FILE_SIZE_BYTES = 500_000  # Skip files > 500 KB
MAX_FILES_TO_ANALYZE = 50

# ---------------------------------------------------------------------------
# Simple in-memory vector store fallback (used when no external vector memory
# is injected).
# ---------------------------------------------------------------------------


class _SimpleVectorMemory:
    """Ultra-light in-memory vector memory for capability embeddings.

    Stores records as plain dicts.  Embedding generation is naive
    (character-ngram histogram) so the module works without heavy
    dependencies such as ``sentence-transformers``.
    """

    def __init__(self) -> None:
        self._store: List[Dict[str, Any]] = []
        self._dim = 128

    # -- public vector-memory API -------------------------------------------

    def add(self, text: str, metadata: Dict[str, Any]) -> None:
        """Add a document with an embedding vector."""
        embedding = self._embed(text)
        self._store.append({"embedding": embedding, "text": text, "metadata": metadata})

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Cosine-similarity search over stored vectors."""
        if not self._store:
            return []
        qvec = self._embed(query)
        scored = []
        for rec in self._store:
            sim = self._cosine(qvec, rec["embedding"])
            scored.append((sim, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "score": s,
                "text": r["text"],
                "metadata": r["metadata"],
            }
            for s, r in scored[:top_k]
        ]

    # -- internals -----------------------------------------------------------

    def _embed(self, text: str) -> List[float]:
        """Naive deterministic embedding (char-ngram histogram)."""
        vec = [0.0] * self._dim
        norm = max(len(text), 1)
        for i in range(len(text) - 1):
            idx = (ord(text[i]) + ord(text[i + 1]) * 31) % self._dim
            vec[idx] += 1.0
        # L2-normalise
        magnitude = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / magnitude for v in vec]

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        return sum(x * y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _run_git(*args: str, cwd: Optional[str] = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a git sub-process and return the result."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _safe_read(path: Path, max_bytes: int = MAX_FILE_SIZE_BYTES) -> str:
    """Read a text file safely, skipping binary or oversized files."""
    try:
        size = path.stat().st_size
        if size > max_bytes:
            return ""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _hash_text(text: str) -> str:
    """Return a short SHA-256 hex digest of *text*."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _repo_name_from_url(url: str) -> str:
    """Derive a directory-friendly repo name from a GitHub URL."""
    # Strip .git suffix and protocol
    clean = url.rstrip("/").removesuffix(".git")
    if "github.com/" in clean:
        clean = clean.split("github.com/", 1)[1]
    return clean.replace("/", "__")


# ---------------------------------------------------------------------------
# GitHubIngestor
# ---------------------------------------------------------------------------


class GitHubIngestor:
    """Autonomous GitHub ingestion: search → clone → analyse → learn → hot-swap.

    Uses the local Anthropic LLM wrapper for code summarisation and stores
    capabilities in a vector memory for semantic retrieval.  Discovered
    skills can be hot-swapped into the running JARVIS process.

    Parameters
    ----------
    local_brain : object, optional
        An optional *LocalCognitiveCore* instance (not yet implemented in
        the runtime — reserved for future integration).
    vector_memory : object, optional
        An optional vector-memory instance.  If ``None`` an internal
        :class:`_SimpleVectorMemory` is used.
    github_token : str, optional
        Personal access token for higher GitHub API rate limits.

    Example::

        ingestor = GitHubIngestor(github_token="ghp_xxx")
        caps = ingestor.ingest("async HTTP client")
        for c in caps:
            ingestor.hot_swap(c["name"])
    """

    def __init__(
        self,
        local_brain: Optional[Any] = None,
        vector_memory: Optional[Any] = None,
        github_token: Optional[str] = None,
    ) -> None:
        self.local_brain = local_brain
        self.vector_memory = vector_memory or _SimpleVectorMemory()
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self._session_headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "jarvis-github-ingestor/1.0",
        }
        if self.github_token:
            self._session_headers["Authorization"] = f"token {self.github_token}"

        self._clone_dir = Path(DEFAULT_CLONE_DIR).expanduser().resolve()
        self._skills_dir = Path(DEFAULT_SKILLS_DIR).expanduser().resolve()
        self._llm = get_llm_router() if LLM_AVAILABLE else None

        # Ensure directories exist
        self._clone_dir.mkdir(parents=True, exist_ok=True)
        self._skills_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Search
    # ------------------------------------------------------------------

    def search_repos(
        self,
        query: str,
        language: str = "python",
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search GitHub repositories via the REST Search API.

        Args:
            query: Free-text search query (e.g. ``"web scraping framework"``).
            language: Filter by primary language (default ``python``).
            max_results: Maximum repositories to return (default 5, max 100).

        Returns:
            List of repository dicts with keys ``full_name``, ``url``,
            ``stars``, ``description``, ``language``.
        """
        max_results = min(max(max_results, 1), 100)
        per_page = min(max_results, 30)
        results: List[Dict[str, Any]] = []

        try:
            import requests
        except ImportError as exc:
            logger.error("requests package required for GitHub search: %s", exc)
            return []

        page = 1
        while len(results) < max_results:
            q = f"{query} language:{language}"
            url = (
                f"{GITHUB_API_BASE}/search/repositories"
                f"?q={requests.utils.quote(q)}"
                f"&sort=stars&order=desc"
                f"&per_page={per_page}&page={page}"
            )
            logger.debug("GitHub search URL: %s", url)
            try:
                resp = requests.get(url, headers=self._session_headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error("GitHub search failed: %s", exc)
                break

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                results.append(
                    {
                        "full_name": item.get("full_name", ""),
                        "url": item.get("html_url", ""),
                        "stars": item.get("stargazers_count", 0),
                        "description": item.get("description") or "",
                        "language": item.get("language") or language,
                        "clone_url": item.get("clone_url", ""),
                    }
                )
                if len(results) >= max_results:
                    break
            page += 1

        logger.info("GitHub search returned %d repos for query '%s'", len(results), query)
        return results

    # ------------------------------------------------------------------
    # 2. Clone
    # ------------------------------------------------------------------

    def clone_repo(
        self,
        repo_url: str,
        target_dir: str = DEFAULT_CLONE_DIR,
    ) -> str:
        """Clone a repository or pull latest if already cloned.

        Args:
            repo_url: HTTPS or SSH clone URL.
            target_dir: Parent directory for the clone.

        Returns:
            Absolute path to the local repository directory.
        """
        target = Path(target_dir).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)

        repo_dir = target / _repo_name_from_url(repo_url)

        if repo_dir.exists() and (repo_dir / ".git").exists():
            logger.info("Repo already cloned at %s — pulling latest", repo_dir)
            result = _run_git("pull", "--ff-only", cwd=str(repo_dir))
            if result.returncode != 0:
                logger.warning("git pull failed: %s", result.stderr)
            return str(repo_dir)

        logger.info("Cloning %s into %s", repo_url, repo_dir)
        result = _run_git("clone", "--depth", "1", repo_url, str(repo_dir))
        if result.returncode != 0:
            raise RuntimeError(
                f"git clone failed for {repo_url}: {result.stderr}"
            )
        return str(repo_dir)

    # ------------------------------------------------------------------
    # 3. Analyse
    # ------------------------------------------------------------------

    def analyze_repo(self, local_path: str) -> Dict[str, Any]:
        """Analyse a cloned repository and return a structured summary.

        Steps:
            1. Count files by language.
            2. Extract main modules / classes via AST.
            3. Find entry points (``__main__`` blocks, CLI args).
            4. Identify dependencies (``requirements.txt``, ``setup.py``, etc.).
            5. (Optional) LLM summarisation of the top files.

        Args:
            local_path: Absolute path to the cloned repository.

        Returns:
            Dictionary with keys ``summary``, ``files``,
            ``capabilities``, ``dependencies``.
        """
        repo_path = Path(local_path).resolve()
        if not repo_path.exists():
            return {"summary": "", "files": [], "capabilities": [], "dependencies": []}

        files_by_lang: Dict[str, int] = {}
        py_files: List[Path] = []
        dependencies: List[str] = []
        capabilities: List[Dict[str, Any]] = []

        # Walk the repo
        for p in repo_path.rglob("*"):
            if p.is_dir():
                if p.name in ("__pycache__", ".git", ".venv", "venv", "node_modules"):
                    continue
                continue
            suffix = p.suffix.lower()
            if suffix == ".py":
                py_files.append(p)
                files_by_lang["python"] = files_by_lang.get("python", 0) + 1
            elif suffix in (".js", ".ts", ".jsx", ".tsx"):
                lang = "javascript" if suffix in (".js", ".jsx") else "typescript"
                files_by_lang[lang] = files_by_lang.get(lang, 0) + 1
            elif suffix == ".go":
                files_by_lang["go"] = files_by_lang.get("go", 0) + 1
            elif suffix == ".rs":
                files_by_lang["rust"] = files_by_lang.get("rust", 0) + 1
            elif suffix in (".c", ".cpp", ".h"):
                files_by_lang["c/c++"] = files_by_lang.get("c/c++", 0) + 1
            else:
                files_by_lang["other"] = files_by_lang.get("other", 0) + 1

            # Dependency files
            if p.name in ("requirements.txt", "setup.py", "pyproject.toml",
                          "Pipfile", "poetry.lock", "package.json",
                          "go.mod", "Cargo.toml"):
                content = _safe_read(p, max_bytes=50_000)
                if content:
                    dependencies.append({"file": str(p.relative_to(repo_path)), "content": content})

        # AST analysis of Python files (limit to avoid explosion)
        for py_file in sorted(py_files)[:MAX_FILES_TO_ANALYZE]:
            content = _safe_read(py_file)
            if not content:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            rel = str(py_file.relative_to(repo_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    doc = ast.get_docstring(node) or ""
                    if doc and not node.name.startswith("_"):
                        capabilities.append(
                            {
                                "name": node.name,
                                "type": "function",
                                "file": rel,
                                "lineno": node.lineno,
                                "description": doc.split("\n")[0],
                                "source": content,
                            }
                        )
                elif isinstance(node, ast.ClassDef):
                    doc = ast.get_docstring(node) or ""
                    if doc:
                        capabilities.append(
                            {
                                "name": node.name,
                                "type": "class",
                                "file": rel,
                                "lineno": node.lineno,
                                "description": doc.split("\n")[0],
                                "source": content,
                            }
                        )
                elif isinstance(node, ast.If):
                    # Detect `if __name__ == "__main__":` entry points
                    test = node.test
                    if (
                        isinstance(test, ast.Compare)
                        and isinstance(test.left, ast.Name)
                        and test.left.id == "__name__"
                    ):
                        for op, comparator in zip(test.ops, test.comparators):
                            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) and comparator.value == "__main__":
                                capabilities.append(
                                    {
                                        "name": f"{rel}:__main__",
                                        "type": "cli",
                                        "file": rel,
                                        "lineno": node.lineno,
                                        "description": f"CLI entry point in {rel}",
                                        "source": content,
                                    }
                                )
                                break

        # LLM summarisation of top-level README + a few key files
        summary = self._llm_summarize(repo_path, py_files[:10])

        analysis = {
            "summary": summary,
            "files": [
                {"path": str(p.relative_to(repo_path)), "language": "python"}
                for p in py_files[:50]
            ],
            "capabilities": capabilities[:50],
            "dependencies": dependencies,
        }
        logger.info(
            "Analysed %s — %d files, %d capabilities",
            repo_path.name,
            len(py_files),
            len(capabilities),
        )
        return analysis

    def _llm_summarize(self, repo_path: Path, py_files: List[Path]) -> str:
        """Ask the local LLM to summarise what this repo does."""
        if self._llm is None:
            return "LLM not available — install anthropic and set ANTHROPIC_API_KEY."

        # Gather README + a few short files for context
        context_parts: List[str] = []
        readme = repo_path / "README.md"
        if readme.exists():
            context_parts.append(f"README:\n{_safe_read(readme, 10_000)}")

        for pf in py_files[:5]:
            content = _safe_read(pf, 5_000)
            if content:
                context_parts.append(f"{pf.name}:\n{content[:2000]}")

        prompt = (
            "Summarise what this open-source repository does in 2-3 sentences. "
            "Mention the main purpose, key modules, and target users.\n\n"
            + "\n---\n".join(context_parts)
        )
        try:
            resp = self._llm.chat(prompt, system="You are a concise code analyst.")
            return resp.get("content", "")
        except Exception as exc:
            logger.warning("LLM summarisation failed: %s", exc)
            return f"LLM error: {exc}"

    # ------------------------------------------------------------------
    # 4. Extract capabilities
    # ------------------------------------------------------------------

    def extract_capabilities(self, repo_path: str) -> List[Dict[str, Any]]:
        """Extract runnable capabilities from a repository.

        Discovers:
            * Public Python functions with docstrings.
            * CLI entry points (``__main__`` blocks, ``console_scripts``).
            * API endpoint patterns (Flask/FastAPI route decorators).

        Args:
            repo_path: Absolute path to the cloned repository.

        Returns:
            List of capability dicts with keys ``name``, ``type``,
            ``code``, ``description``.
        """
        repo = Path(repo_path).resolve()
        caps: List[Dict[str, Any]] = []
        seen: set = set()

        for py_file in repo.rglob("*.py"):
            if py_file.name.startswith(".") or "__pycache__" in str(py_file):
                continue
            content = _safe_read(py_file)
            if not content:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            rel = str(py_file.relative_to(repo))

            for node in ast.walk(tree):
                # Functions
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    doc = ast.get_docstring(node) or ""
                    sig = self._function_signature(node)
                    key = f"{rel}::{node.name}"
                    if key not in seen:
                        seen.add(key)
                        source_segment = ast.get_source_segment(content, node) or ""
                        caps.append(
                            {
                                "name": node.name,
                                "type": "function",
                                "code": source_segment,
                                "description": doc.split("\n")[0] if doc else f"Function {node.name}{sig}",
                                "file": rel,
                                "repo": repo.name,
                            }
                        )

                # Classes
                elif isinstance(node, ast.ClassDef):
                    doc = ast.get_docstring(node) or ""
                    key = f"{rel}::{node.name}"
                    if key not in seen:
                        seen.add(key)
                        source_segment = ast.get_source_segment(content, node) or ""
                        caps.append(
                            {
                                "name": node.name,
                                "type": "class",
                                "code": source_segment,
                                "description": doc.split("\n")[0] if doc else f"Class {node.name}",
                                "file": rel,
                                "repo": repo.name,
                            }
                        )

                # CLI patterns
                elif isinstance(node, ast.If):
                    test = node.test
                    if (
                        isinstance(test, ast.Compare)
                        and isinstance(test.left, ast.Name)
                        and test.left.id == "__name__"
                    ):
                        for op, comparator in zip(test.ops, test.comparators):
                            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) and comparator.value == "__main__":
                                key = f"{rel}::__main__"
                                if key not in seen:
                                    seen.add(key)
                                    caps.append(
                                        {
                                            "name": f"{repo.name}_cli",
                                            "type": "cli",
                                            "code": ast.get_source_segment(content, node) or "",
                                            "description": f"CLI entry point in {rel}",
                                            "file": rel,
                                            "repo": repo.name,
                                        }
                                    )
                                break

            # Heuristic: FastAPI / Flask routes in this file
            route_pattern = re.compile(
                r"(@app\.(route|get|post|put|delete|patch)\s*\([^)]*\))",
                re.MULTILINE,
            )
            for match in route_pattern.finditer(content):
                caps.append(
                    {
                        "name": f"endpoint_{match.start()}",
                        "type": "api_endpoint",
                        "code": match.group(1),
                        "description": f"API endpoint pattern in {rel}",
                        "file": rel,
                        "repo": repo.name,
                    }
                )

        logger.info("Extracted %d capabilities from %s", len(caps), repo.name)
        return caps

    @staticmethod
    def _function_signature(node: ast.FunctionDef) -> str:
        """Build a rough ``(arg1, arg2=default)`` string from an AST node."""
        args = node.args
        parts: List[str] = []
        defaults_offset = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            name = arg.arg
            if i >= defaults_offset:
                default = args.defaults[i - defaults_offset]
                try:
                    dv = ast.unparse(default)
                except Exception:
                    dv = "..."
                parts.append(f"{name}={dv}")
            else:
                parts.append(name)
        return f"({', '.join(parts)})"

    # ------------------------------------------------------------------
    # 5. Learn capability
    # ------------------------------------------------------------------

    def learn_capability(self, capability: Dict[str, Any]) -> bool:
        """Store a capability in vector memory with an embedding.

        Args:
            capability: Dict from :meth:`extract_capabilities`.

        Returns:
            ``True`` on success.
        """
        try:
            text = (
                f"Name: {capability.get('name', '')}\n"
                f"Type: {capability.get('type', '')}\n"
                f"Description: {capability.get('description', '')}\n"
                f"Code:\n{capability.get('code', '')[:2000]}"
            )
            metadata = {
                "name": capability.get("name", ""),
                "type": capability.get("type", ""),
                "file": capability.get("file", ""),
                "repo": capability.get("repo", ""),
                "hash": _hash_text(text),
            }
            self.vector_memory.add(text, metadata)
            logger.debug("Learned capability: %s", metadata["name"])
            return True
        except Exception as exc:
            logger.error("Failed to learn capability: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 6. Hot-swap
    # ------------------------------------------------------------------

    def hot_swap(self, capability_name: str) -> bool:
        """Dynamically load a capability into the JARVIS runtime.

        Writes the capability code to a local skill file under
        ``jarvis_skills/``, then imports the module and registers it
        in an in-process skill registry.

        Args:
            capability_name: Name of the capability to hot-swap.

        Returns:
            ``True`` if the capability was successfully loaded.
        """
        # Search vector memory for the exact capability
        hits = self.vector_memory.search(capability_name, top_k=5)
        target = None
        for hit in hits:
            meta = hit.get("metadata", {})
            if meta.get("name") == capability_name:
                target = hit
                break
        if target is None:
            logger.warning("Capability '%s' not found in memory", capability_name)
            return False

        meta = target["metadata"]
        cap_type = meta.get("type", "function")
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", capability_name).strip("_")
        skill_file = self._skills_dir / f"{safe_name}_skill.py"

        # Reconstruct a standalone skill module
        code = target.get("text", "")
        # Extract just the code block if present
        code_match = re.search(r"Code:\n(.*)", code, re.DOTALL)
        extracted_code = code_match.group(1) if code_match else code

        module_src = f'"""Auto-generated skill from GitHub ingestor.\n\nSource: {meta.get("repo", "unknown")}\n"""\n\n'
        module_src += extracted_code or f"# Placeholder for {capability_name}\n"
        module_src += "\n\n# --- skill registration ---\n"
        module_src += f"SKILL_NAME = {repr(capability_name)}\n"
        module_src += f"SKILL_TYPE = {repr(cap_type)}\n"
        module_src += (
            "def register_skill(registry: dict) -> None:\n"
            f"    registry[{repr(capability_name)}] = globals().get({repr(capability_name)}, None)\n"
        )

        skill_file.write_text(module_src, encoding="utf-8")
        logger.info("Wrote skill file: %s", skill_file)

        # Dynamic import
        try:
            spec = importlib.util.spec_from_file_location(
                f"jarvis_skills.{safe_name}_skill", str(skill_file)
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create spec for {skill_file}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module.__name__] = module
            spec.loader.exec_module(module)

            # Register in global skill registry
            _register_in_skill_registry(capability_name, cap_type, module)
            logger.info("Hot-swapped capability '%s' into runtime", capability_name)
            return True
        except Exception as exc:
            logger.error("Hot-swap failed for '%s': %s", capability_name, exc)
            return False

    # ------------------------------------------------------------------
    # 7. Full pipeline
    # ------------------------------------------------------------------

    def ingest(self, query: str) -> List[Dict[str, Any]]:
        """End-to-end pipeline: search → clone → analyse → learn.

        Args:
            query: Search query for GitHub repositories.

        Returns:
            List of learned capabilities.
        """
        repos = self.search_repos(query)
        learned: List[Dict[str, Any]] = []
        for repo in repos[:3]:  # Limit to top 3 to stay within step budget
            try:
                local_path = self.clone_repo(repo["clone_url"])
                capabilities = self.extract_capabilities(local_path)
                for cap in capabilities:
                    if self.learn_capability(cap):
                        learned.append(cap)
                logger.info(
                    "Ingested repo %s → %d capabilities",
                    repo["full_name"],
                    len(capabilities),
                )
            except Exception as exc:
                logger.error("Ingest failed for %s: %s", repo.get("full_name"), exc)
        return learned

    # ------------------------------------------------------------------
    # 8. Rate limit
    # ------------------------------------------------------------------

    def rate_limit_status(self) -> Dict[str, Any]:
        """Check the current GitHub API rate-limit status.

        Returns:
            Dict with ``limit``, ``remaining``, ``reset``, ``used``.
        """
        try:
            import requests
        except ImportError:
            return {"error": "requests package not installed"}

        try:
            resp = requests.get(
                f"{GITHUB_API_BASE}/rate_limit",
                headers=self._session_headers,
                timeout=10,
            )
            resp.raise_for_status()
            core = resp.json().get("resources", {}).get("core", {})
            reset_ts = core.get("reset", 0)
            return {
                "limit": core.get("limit", 0),
                "remaining": core.get("remaining", 0),
                "reset": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(reset_ts)),
                "used": core.get("used", 0),
            }
        except Exception as exc:
            logger.error("Rate-limit check failed: %s", exc)
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Skill registry helpers
# ---------------------------------------------------------------------------

# Global in-process skill registry
_SKILL_REGISTRY: Dict[str, Any] = {}


def _register_in_skill_registry(name: str, cap_type: str, module: Any) -> None:
    """Register a hot-swapped module in the global skill registry."""
    _SKILL_REGISTRY[name] = {
        "type": cap_type,
        "module": module,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def get_skill_registry() -> Dict[str, Any]:
    """Return the global hot-swap skill registry (read-only copy)."""
    return dict(_SKILL_REGISTRY)


# ---------------------------------------------------------------------------
# MockGitHubIngestor
# ---------------------------------------------------------------------------


class MockGitHubIngestor(GitHubIngestor):
    """Deterministic mock implementation of :class:`GitHubIngestor`.

    Returns canned data for every method so that unit tests and offline
    demos can run without network access or a GitHub token.

    The interface is identical to the real class; only the behaviour is
    mocked.
    """

    _MOCK_REPOS = [
        {
            "full_name": "mockuser/mock-ml-pipeline",
            "url": "https://github.com/mockuser/mock-ml-pipeline",
            "stars": 128,
            "description": "A mock machine learning pipeline for testing.",
            "language": "python",
            "clone_url": "https://github.com/mockuser/mock-ml-pipeline.git",
        },
        {
            "full_name": "mockuser/mock-web-scraper",
            "url": "https://github.com/mockuser/mock-web-scraper",
            "stars": 64,
            "description": "Mock async web scraper with BeautifulSoup.",
            "language": "python",
            "clone_url": "https://github.com/mockuser/mock-web-scraper.git",
        },
        {
            "full_name": "mockuser/mock-data-lib",
            "url": "https://github.com/mockuser/mock-data-lib",
            "stars": 32,
            "description": "Mock data processing utilities.",
            "language": "python",
            "clone_url": "https://github.com/mockuser/mock-data-lib.git",
        },
    ]

    def __init__(
        self,
        local_brain: Optional[Any] = None,
        vector_memory: Optional[Any] = None,
        github_token: Optional[str] = None,
    ) -> None:
        # Bypass the real parent __init__ to avoid side effects
        self.local_brain = local_brain
        self.vector_memory = vector_memory or _SimpleVectorMemory()
        self.github_token = github_token or ""
        self._llm = None
        self._clone_dir = Path(DEFAULT_CLONE_DIR).expanduser().resolve()
        self._skills_dir = Path(DEFAULT_SKILLS_DIR).expanduser().resolve()

    def search_repos(
        self,
        query: str,
        language: str = "python",
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return mock repositories (slice of the canned list)."""
        max_results = min(max(max_results, 1), len(self._MOCK_REPOS))
        return [dict(r) for r in self._MOCK_REPOS[:max_results]]

    def clone_repo(
        self,
        repo_url: str,
        target_dir: str = DEFAULT_CLONE_DIR,
    ) -> str:
        """Create a mock directory with a synthetic ``.git`` marker."""
        target = Path(target_dir).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        repo_dir = target / _repo_name_from_url(repo_url)
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git").mkdir(exist_ok=True)
        # Write a fake README so analyse_repo has something to parse
        (repo_dir / "README.md").write_text(f"# Mock repo\n\nAuto-generated for {repo_url}\n")
        # Write a fake Python module
        (repo_dir / "mock_module.py").write_text(
            '\n"""A mock module."""\n\n'
            "def mock_function():\n"
            '    """A mock function for testing."""\n'
            "    return 42\n\n"
            "class MockClass:\n"
            '    """A mock class."""\n'
            "    def run(self):\n"
            "        pass\n"
        )
        return str(repo_dir)

    def analyze_repo(self, local_path: str) -> Dict[str, Any]:
        """Return a mock analysis structure."""
        return {
            "summary": "Mock repository generated for testing purposes.",
            "files": [
                {"path": "README.md", "language": "markdown"},
                {"path": "mock_module.py", "language": "python"},
            ],
            "capabilities": [
                {
                    "name": "mock_function",
                    "type": "function",
                    "file": "mock_module.py",
                    "lineno": 4,
                    "description": "A mock function for testing.",
                    "source": 'def mock_function():\n    """A mock function for testing."""\n    return 42\n',
                },
                {
                    "name": "MockClass",
                    "type": "class",
                    "file": "mock_module.py",
                    "lineno": 7,
                    "description": "A mock class.",
                    "source": 'class MockClass:\n    """A mock class."""\n    def run(self):\n        pass\n',
                },
            ],
            "dependencies": [
                {"file": "requirements.txt", "content": "requests>=2.28\nnumpy>=1.21\n"}
            ],
        }

    def extract_capabilities(self, repo_path: str) -> List[Dict[str, Any]]:
        """Return mock capabilities from the synthetic repo."""
        return [
            {
                "name": "mock_function",
                "type": "function",
                "code": 'def mock_function():\n    """A mock function for testing."""\n    return 42\n',
                "description": "A mock function for testing.",
                "file": "mock_module.py",
                "repo": Path(repo_path).name,
            },
            {
                "name": "MockClass",
                "type": "class",
                "code": 'class MockClass:\n    """A mock class."""\n    def run(self):\n        pass\n',
                "description": "A mock class.",
                "file": "mock_module.py",
                "repo": Path(repo_path).name,
            },
        ]

    def learn_capability(self, capability: Dict[str, Any]) -> bool:
        """Always succeed — stores in the internal simple memory."""
        return super().learn_capability(capability)

    def hot_swap(self, capability_name: str) -> bool:
        """Mock hot-swap: writes a stub skill file and returns True."""
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", capability_name).strip("_")
        skill_file = self._skills_dir / f"{safe_name}_skill.py"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(
            f'"""Mock skill for {capability_name}."""\n\n'
            f"def {safe_name}():\n"
            f'    """Mock implementation."""\n'
            f"    return 'mock-result'\n\n"
            f"SKILL_NAME = {repr(capability_name)}\n"
            f"SKILL_TYPE = 'mock'\n"
        )
        _register_in_skill_registry(capability_name, "mock", None)
        return True

    def ingest(self, query: str) -> List[Dict[str, Any]]:
        """Mock full pipeline returning canned capabilities."""
        learned: List[Dict[str, Any]] = []
        for repo in self.search_repos(query, max_results=2):
            path = self.clone_repo(repo["clone_url"])
            for cap in self.extract_capabilities(path):
                if self.learn_capability(cap):
                    learned.append(cap)
        return learned

    def rate_limit_status(self) -> Dict[str, Any]:
        """Return a generous mock rate-limit dict."""
        return {
            "limit": 5000,
            "remaining": 4999,
            "reset": "2099-12-31 23:59:59 UTC",
            "used": 1,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_github_ingestor(
    local_brain: Optional[Any] = None,
    vector_memory: Optional[Any] = None,
    github_token: Optional[str] = None,
    use_mock: bool = False,
) -> GitHubIngestor:
    """Factory that returns a :class:`GitHubIngestor` or :class:`MockGitHubIngestor`.

    Parameters
    ----------
    local_brain : object, optional
        Optional cognitive core instance.
    vector_memory : object, optional
        Optional vector memory instance.
    github_token : str, optional
        GitHub personal access token.
    use_mock : bool, optional
        If ``True`` force the mock implementation.

    Returns
    -------
    GitHubIngestor or MockGitHubIngestor
    """
    if use_mock:
        logger.info("Using MockGitHubIngestor (forced)")
        return MockGitHubIngestor(local_brain, vector_memory, github_token)

    # Auto-detect: if requests is missing or no token in env and none provided,
    # fall back to mock so the system never crashes on import.
    try:
        import requests  # noqa: F401
    except ImportError:
        logger.warning("requests not installed — falling back to MockGitHubIngestor")
        return MockGitHubIngestor(local_brain, vector_memory, github_token)

    if not (github_token or os.environ.get("GITHUB_TOKEN", "")):
        logger.warning("No GITHUB_TOKEN provided — GitHubIngestor created but search may be rate-limited")

    return GitHubIngestor(local_brain, vector_memory, github_token)
