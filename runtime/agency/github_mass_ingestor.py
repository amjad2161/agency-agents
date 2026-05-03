#!/usr/bin/env python3
"""
================================================================================
JARVIS BRAINIAC — GitHub Mass Ingestor
================================================================================
A mass ingestion system that LEARNS from open-source projects — it does NOT steal.

Purpose:
--------
Discovers, analyzes, and extracts capability patterns from open-source GitHub
repositories. Filters for quality, checks licenses for compatibility, detects
malware, and integrates useful code patterns into JARVIS's skill system.

Philosophy:
-----------
- Learn patterns and architecture, not implementations
- Respect open-source licenses (MIT, Apache-2.0, GPL-compatible)
- Filter for quality (stars, tests, recent activity, documentation)
- Sanitize all extracted code — no malware, no harmful patterns
- Give credit — track provenance of all learned skills

Entry Points:
-------------
- discover_repos(topics, max_results)        → Mass discovery by topic
- clone_and_analyze(repo_url)                → Deep single-repo analysis
- ingest_batch(repos)                        → Batch ingestion
- ingest_from_topics(topics, max_per_topic)  → Topic-driven mass learning
- get_github_mass_ingestor()                 → Factory function

================================================================================
"""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("jarvis.github_mass_ingestor")

# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------

# GitHub API
GITHUB_API_BASE = "https://api.github.com"
GITHUB_SEARCH_API = f"{GITHUB_API_BASE}/search/repositories"
GITHUB_REPO_API = f"{GITHUB_API_BASE}/repos"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"

# Rate limiting
DEFAULT_RATE_LIMIT_CALLS = 30  # requests per minute (authenticated)
DEFAULT_RATE_LIMIT_PERIOD = 60  # seconds

# Quality thresholds
MIN_STARS_DEFAULT = 50
MIN_FORKS_DEFAULT = 5
MAX_AGE_DAYS_DEFAULT = 730  # 2 years of inactivity max
MIN_TEST_FILES_DEFAULT = 1

# License compatibility matrix
COMPATIBLE_LICENSES: Dict[str, Dict[str, bool]] = {
    "mit": {
        "mit": True,
        "apache-2.0": True,
        "bsd-3-clause": True,
        "bsd-2-clause": True,
        "gpl-3.0": False,
        "gpl-2.0": False,
        "lgpl-3.0": True,
        "lgpl-2.1": True,
        "mpl-2.0": True,
        "isc": True,
        "unlicense": True,
    },
    "apache-2.0": {
        "mit": True,
        "apache-2.0": True,
        "bsd-3-clause": True,
        "bsd-2-clause": True,
        "gpl-3.0": True,
        "gpl-2.0": False,
        "lgpl-3.0": True,
        "lgpl-2.1": True,
        "mpl-2.0": True,
        "isc": True,
        "unlicense": True,
    },
}

ALLOWED_LICENSES_DEFAULT = [
    "mit",
    "apache-2.0",
    "bsd-3-clause",
    "bsd-2-clause",
    "isc",
    "unlicense",
    "gpl-3.0",
    "lgpl-3.0",
    "mpl-2.0",
]

# Malicious pattern signatures
MALWARE_PATTERNS = [
    rb"eval\s*\(\s*base64",
    rb"exec\s*\(\s*__import__\s*\(\s*['\"]base64['\"]",
    rb"os\.system\s*\(\s*['\"]rm\s+-rf\s+/['\"]",
    rb"subprocess\.call\s*\(.*['\"]/bin/sh['\"]",
    rb"__import__\s*\(\s*['\"]ctypes['\"].*VirtualAlloc",
    rb"socket\..*connect\s*\(\s*\(\s*['\"]\d+\.\d+\.\d+\.\d+['\"]",
    rb"import\s+pynput",
    rb"keylog",
    rb"password.*steal",
    rb"credential.*harvest",
    rb"reverse.*shell",
    rb"backdoor",
    rb"\.pyc.*marshal\.loads",
    rb"compile\s*\(\s*['\"].*['\"]\s*,\s*['\"]<string>['\"]",
    rb"__builtins__\s*\[\s*['\"]__import__['\"]\s*\]",
    rb"getattr\s*\(\s*__builtins__",
    rb"__import__\s*\(\s*['\"]os['\"]\s*\)\..*fork",
    rb" multiprocessing\.Process.*target=.*os\.system",
    rb"ctypes\.windll\.kernel32\.VirtualAllocEx",
    rb"ctypes\.CDLL\s*\(\s*['\"]libc",
    rb"shellcode",
    rb"cryptography\.fernet.*decrypt.*exec",
    rb"pickle\.loads\s*\(\s*base64",
    rb"yaml\.load\s*\(.*Loader=yaml\.Loader",
    rb"input\s*\(.*eval\s*\(",
    rb"subprocess\.Popen\s*\(\s*['\"]curl['\"].*\|.*sh",
    rb"wget.*\|.*bash",
    rb"nc\s+-e\s+/bin/sh",
    rb"bash\s+-i\s+>&\s+/dev/tcp",
]

# Architecture pattern signatures
ARCHITECTURE_PATTERNS = {
    "microservices": [
        r"docker-compose\.ya?ml",
        r"kubernetes/.*\.ya?ml",
        r"k8s/",
        r"service\.ya?ml",
        r"deployment\.ya?ml",
    ],
    "event_driven": [
        r"kafka",
        r"rabbitmq",
        r"celery",
        r"event.*bus",
        r"pub.*sub",
        r"message.*queue",
    ],
    "plugin_system": [
        r"plugins?/",
        r"extensions?/",
        r"hooks?\.py",
        r"entry_points",
        r"pluggy",
    ],
    "cli_tool": [
        r"click",
        r"argparse",
        r"typer",
        r"fire",
        r"console_scripts",
    ],
    "web_framework": [
        r"fastapi",
        r"flask",
        r"django",
        r"tornado",
        r"starlette",
    ],
    "ml_pipeline": [
        r"pipeline",
        r"sklearn",
        r"transformers",
        r"torch",
        r"tensorflow",
        r"onnx",
    ],
    "agent_framework": [
        r"agent",
        r"autogpt",
        r"langchain",
        r"crewai",
        r"autogen",
        r"tool.*call",
    ],
}

# File language mapping
LANGUAGE_MAP: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JSX",
    ".tsx": "TSX",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".hpp": "C++",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".scala": "Scala",
    ".r": "R",
    ".m": "MATLAB/Objective-C",
    ".cs": "C#",
    ".fs": "F#",
    ".ex": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".lua": "Lua",
    ".jl": "Julia",
    ".dart": "Dart",
    ".sh": "Shell",
    ".bash": "Bash",
    ".zsh": "Zsh",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".ipynb": "Jupyter Notebook",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "Config",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".dockerfile": "Dockerfile",
    "Dockerfile": "Dockerfile",
    ".tf": "Terraform",
    ".nix": "Nix",
}

# Skill taxonomy — topics we care about for JARVIS
JARVIS_SKILL_TOPICS = [
    "ai-agents",
    "computer-vision",
    "nlp",
    "voice-synthesis",
    "robotics",
    "trading",
    "machine-learning",
    "deep-learning",
    "automation",
    "web-scraping",
    "api-design",
    "data-pipeline",
    "stream-processing",
    "llm",
    "rag",
    "embeddings",
    "vector-database",
    "mcp",
    "tool-use",
    "planning",
    "reasoning",
]


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class RepoInfo:
    """Structured representation of a discovered repository."""

    full_name: str
    url: str
    stars: int
    forks: int
    language: str
    license: str
    topics: List[str] = field(default_factory=list)
    description: str = ""
    last_updated: str = ""
    open_issues: int = 0
    size_kb: int = 0
    has_wiki: bool = False
    has_tests: bool = False
    quality_score: float = 0.0
    readme_length: int = 0
    file_count: int = 0
    test_file_count: int = 0
    dependency_count: int = 0
    architecture_patterns: List[str] = field(default_factory=list)
    extracted_skills: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillExtraction:
    """A single extracted skill from a repository."""

    name: str
    description: str
    source_repo: str
    source_license: str
    skill_type: str  # "algorithm", "pattern", "integration", "tool", "architecture"
    code_snippet: str
    sanitized: bool
    confidence: float  # 0.0 - 1.0
    dependencies: List[str] = field(default_factory=list)
    integration_code: str = ""


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Token-bucket rate limiter for GitHub API calls."""

    def __init__(self, max_calls: int = 30, period: int = 60):
        self.max_calls = max_calls
        self.period = period
        self.calls: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        async with self._lock:
            now = time.time()
            # Remove calls outside the period
            self.calls = [c for c in self.calls if now - c < self.period]
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0]) + 0.5
                logger.debug("Rate limit hit, sleeping %.1fs", sleep_time)
                await asyncio.sleep(sleep_time)
                now = time.time()
                self.calls = [c for c in self.calls if now - c < self.period]
            self.calls.append(time.time())

    def sync_acquire(self) -> None:
        """Synchronous version of acquire."""
        now = time.time()
        self.calls = [c for c in self.calls if now - c < self.period]
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0]) + 0.5
            logger.debug("Rate limit hit, sleeping %.1fs", sleep_time)
            time.sleep(sleep_time)
            now = time.time()
            self.calls = [c for c in self.calls if now - c < self.period]
        self.calls.append(time.time())


# ---------------------------------------------------------------------------
# Local LLM Client (ollama-compatible)
# ---------------------------------------------------------------------------

class LocalLLMClient:
    """Lightweight client for local LLM inference via Ollama/compatible API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "codellama"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._session: Optional[Any] = None

    async def generate(self, prompt: str, system: str = "", temperature: float = 0.3) -> str:
        """Generate text using the local LLM. Falls back to heuristic if LLM unavailable."""
        try:
            import aiohttp
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": 512},
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate", json=payload, timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "")
        except Exception as exc:
            logger.debug("LLM generate failed: %s — using heuristic fallback", exc)
        return ""

    async def summarize_repo(self, repo_info: Dict[str, Any], file_tree: str) -> str:
        """Generate a capability summary of a repository."""
        prompt = (
            f"Repository: {repo_info.get('full_name', 'unknown')}\n"
            f"Description: {repo_info.get('description', 'N/A')}\n"
            f"Language: {repo_info.get('language', 'N/A')}\n"
            f"Topics: {', '.join(repo_info.get('topics', []))}\n"
            f"Stars: {repo_info.get('stars', 0)}\n"
            f"File tree:\n{file_tree}\n\n"
            "Summarize the main capabilities and architecture of this project "
            "in 3-5 sentences. Focus on what it DOES and how it works."
        )
        system = (
            "You are a technical analyst. Summarize code repositories concisely. "
            "Focus on capabilities, architecture, and key features. Be specific."
        )
        result = await self.generate(prompt, system=system, temperature=0.3)
        if not result:
            return self._heuristic_summarize(repo_info, file_tree)
        return result

    async def extract_skill_from_code(self, code: str, context: str) -> Dict[str, Any]:
        """Extract a skill description from a code snippet."""
        prompt = (
            f"Context: {context}\n\n"
            f"Code:\n```python\n{code[:2000]}\n```\n\n"
            "Extract: (1) What skill this code demonstrates, "
            "(2) What the inputs/outputs are, "
            "(3) What dependencies it needs. "
            "Respond in JSON: {\"skill_name\": str, \"description\": str, \"dependencies\": [str]}"
        )
        system = "You extract reusable skills from code. Respond only with valid JSON."
        result = await self.generate(prompt, system=system, temperature=0.2)
        if result:
            try:
                # Try to extract JSON from response
                match = re.search(r'\{.*\}', result, re.DOTALL)
                if match:
                    return json.loads(match.group())
            except (json.JSONDecodeError, AttributeError):
                pass
        return self._heuristic_skill_extract(code, context)

    def _heuristic_summarize(self, repo_info: Dict[str, Any], file_tree: str) -> str:
        """Fallback summarization without LLM."""
        parts = [
            f"{repo_info.get('full_name', 'Unknown')} is a "
            f"{repo_info.get('language', 'unknown language')} project",
        ]
        if repo_info.get("description"):
            parts.append(f"for {repo_info['description']}")
        topics = repo_info.get("topics", [])
        if topics:
            parts.append(f"covering topics: {', '.join(topics[:5])}")
        return " ".join(parts) + "."

    def _heuristic_skill_extract(self, code: str, context: str) -> Dict[str, Any]:
        """Fallback skill extraction without LLM."""
        # Detect class/function definitions
        class_match = re.search(r'class\s+(\w+)', code)
        func_match = re.search(r'def\s+(\w+)', code)
        name = class_match.group(1) if class_match else (func_match.group(1) if func_match else "unknown")
        return {
            "skill_name": name,
            "description": f"Extracted {name} from {context}",
            "dependencies": self._detect_imports(code),
        }

    @staticmethod
    def _detect_imports(code: str) -> List[str]:
        """Detect Python imports in code."""
        imports = []
        for line in code.splitlines():
            match = re.match(r'^(?:import|from)\s+([\w.]+)', line)
            if match:
                imports.append(match.group(1).split(".")[0])
        return imports


# ---------------------------------------------------------------------------
# Main Ingestor Class
# ---------------------------------------------------------------------------

class GitHubMassIngestor:
    """
    Mass ingestion engine for learning from open-source GitHub repositories.

    Design principles:
    - LEARN from patterns, don't copy implementations
    - Filter aggressively for quality
    - Check every license, sanitize every snippet
    - Cache results to avoid duplicate work
    - Track provenance for every extracted skill

    Usage:
        ingestor = GitHubMassIngestor(github_token="ghp_...")
        repos = ingestor.discover_repos(["ai-agents"], max_results=500)
        filtered = ingestor.filter_by_license(repos, ["mit", "apache-2.0"])
        ranked = ingestor.rank_by_quality(filtered)
        results = ingestor.ingest_batch(ranked[:20])
    """

    def __init__(
        self,
        github_token: Optional[str] = None,
        cache_dir: Optional[str] = None,
        clone_dir: Optional[str] = None,
        min_stars: int = MIN_STARS_DEFAULT,
        min_forks: int = MIN_FORKS_DEFAULT,
        max_age_days: int = MAX_AGE_DAYS_DEFAULT,
        allowed_licenses: Optional[List[str]] = None,
        llm_base_url: str = "http://localhost:11434",
        llm_model: str = "codellama",
        rate_limit_calls: int = DEFAULT_RATE_LIMIT_CALLS,
        rate_limit_period: int = DEFAULT_RATE_LIMIT_PERIOD,
    ):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.cache_dir = Path(cache_dir or "/tmp/jarvis/github_cache")
        self.clone_dir = Path(clone_dir or "/tmp/jarvis/github_clones")
        self.min_stars = min_stars
        self.min_forks = min_forks
        self.max_age_days = max_age_days
        self.allowed_licenses = allowed_licenses or ALLOWED_LICENSES_DEFAULT
        self.llm = LocalLLMClient(base_url=llm_base_url, model=llm_model)
        self.rate_limiter = RateLimiter(rate_limit_calls, rate_limit_period)

        # Ensure directories exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.clone_dir.mkdir(parents=True, exist_ok=True)

        # Statistics
        self.stats = {
            "api_calls": 0,
            "repos_discovered": 0,
            "repos_analyzed": 0,
            "repos_failed": 0,
            "skills_extracted": 0,
            "malware_detected": 0,
            "start_time": datetime.now().isoformat(),
        }

        # In-memory cache
        self._cache: Dict[str, Any] = {}

    # ── internal helpers ──────────────────────────────────────────────────

    def _api_headers(self) -> Dict[str, str]:
        """Build request headers for GitHub API."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "JARVIS-BRAINIAC-GitHub-Ingestor/1.0",
        }
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        return headers

    def _cache_key(self, *parts: str) -> str:
        """Generate a cache key from parts."""
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _cache_path(self, key: str) -> Path:
        """Get filesystem path for a cache key."""
        return self.cache_dir / f"{key}.json"

    def _load_cache(self, key: str) -> Optional[Any]:
        """Load cached data if available and not expired."""
        if key in self._cache:
            return self._cache[key]
        path = self._cache_path(key)
        if path.exists():
            # Cache valid for 24 hours
            if time.time() - path.stat().st_mtime < 86400:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._cache[key] = data
                        return data
                except (json.JSONDecodeError, IOError):
                    pass
        return None

    def _save_cache(self, key: str, data: Any) -> None:
        """Save data to cache."""
        self._cache[key] = data
        path = self._cache_path(key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except IOError as exc:
            logger.warning("Cache write failed: %s", exc)

    def _github_api_get(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a synchronous GET request to the GitHub API with rate limiting."""
        import urllib.request
        import urllib.error
        import urllib.parse

        self.rate_limiter.sync_acquire()
        self.stats["api_calls"] += 1

        query = urllib.parse.urlencode(params or {})
        full_url = f"{url}?{query}" if query else url

        req = urllib.request.Request(full_url, headers=self._api_headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.error("GitHub API error %s: %s", exc.code, exc.reason)
            if exc.code == 403:
                # Rate limited — wait and retry once
                logger.warning("Rate limited. Waiting 60s...")
                time.sleep(60)
                return self._github_api_get(url, params)
            return {}
        except Exception as exc:
            logger.error("GitHub API request failed: %s", exc)
            return {}

    def _clone_repo(self, repo_url: str, dest: Path) -> bool:
        """Clone a git repository to a destination path."""
        try:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--single-branch", repo_url, str(dest)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error("Clone timeout for %s", repo_url)
            return False
        except FileNotFoundError:
            logger.error("git command not found. Is git installed?")
            return False
        except Exception as exc:
            logger.error("Clone failed for %s: %s", repo_url, exc)
            return False

    def _count_files_by_language(self, repo_path: Path) -> Dict[str, int]:
        """Count source files grouped by programming language."""
        counts: Dict[str, int] = Counter()
        for root, _dirs, files in os.walk(repo_path):
            # Skip hidden dirs and common non-source dirs
            root_path = Path(root)
            if any(part.startswith(".") or part in {"node_modules", "vendor", "__pycache__", "venv", ".git"}
                   for part in root_path.parts):
                continue
            for fname in files:
                ext = Path(fname).suffix.lower()
                if not ext:
                    ext = fname
                lang = LANGUAGE_MAP.get(ext, "Unknown")
                counts[lang] += 1
        return dict(counts)

    def _detect_architecture_patterns(self, repo_path: Path) -> List[str]:
        """Scan repository for known architecture patterns."""
        found: Set[str] = set()
        all_text = ""
        for root, _dirs, files in os.walk(repo_path):
            root_path = Path(root)
            if any(part.startswith(".") or part in {"node_modules", "vendor", "__pycache__", ".git"}
                   for part in root_path.parts):
                continue
            for fname in files:
                if fname.lower().endswith((".py", ".js", ".ts", ".go", ".rs", ".java",
                                            ".md", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".json")):
                    fpath = root_path / fname
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="ignore")[:5000]
                        all_text += content + "\n"
                    except IOError:
                        pass
        # Check for config files / directory structures
        for pattern_name, signatures in ARCHITECTURE_PATTERNS.items():
            for sig in signatures:
                if re.search(sig, all_text, re.IGNORECASE):
                    found.add(pattern_name)
                    break
        return sorted(found)

    def _find_main_modules(self, repo_path: Path, language: str) -> List[Dict[str, str]]:
        """Find main modules, classes, and entry points in the repository."""
        modules: List[Dict[str, str]] = []
        primary_ext = {
            "Python": ".py", "JavaScript": ".js", "TypeScript": ".ts",
            "Go": ".go", "Rust": ".rs", "Java": ".java",
        }.get(language, ".py")

        for root, _dirs, files in os.walk(repo_path):
            root_path = Path(root)
            if any(part.startswith(".") or part in {"node_modules", "vendor", "__pycache__", ".git"}
                   for part in root_path.parts):
                continue
            for fname in files:
                if not fname.endswith(primary_ext):
                    continue
                fpath = root_path / fname
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    # Find class definitions
                    for match in re.finditer(r'class\s+(\w+)\s*(?:\(([^)]*)\))?', content):
                        class_name = match.group(1)
                        bases = match.group(2) or ""
                        modules.append({
                            "type": "class",
                            "name": class_name,
                            "file": str(fpath.relative_to(repo_path)),
                            "bases": bases,
                        })
                    # Find function definitions
                    for match in re.finditer(r'def\s+(\w+)\s*\(', content):
                        func_name = match.group(1)
                        if not func_name.startswith("_"):
                            modules.append({
                                "type": "function",
                                "name": func_name,
                                "file": str(fpath.relative_to(repo_path)),
                                "bases": "",
                            })
                except IOError:
                    pass
        # Return top 30 most interesting (deduplicated)
        seen = set()
        unique: List[Dict[str, str]] = []
        for m in modules:
            key = (m["type"], m["name"])
            if key not in seen:
                seen.add(key)
                unique.append(m)
                if len(unique) >= 30:
                    break
        return unique

    def _check_for_tests(self, repo_path: Path) -> Tuple[bool, int]:
        """Check if repository has test files and count them."""
        test_indicators = [
            "test_*.py", "*_test.py", "tests/**/*.py",
            "*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts",
            "*_test.go", "*_test.rs",
            "test/", "tests/", "spec/", "__tests__/",
            "pytest.ini", "tox.ini", ".pytest_cache",
            "jest.config.*", "vitest.config.*",
        ]
        test_count = 0
        for root, dirs, files in os.walk(repo_path):
            root_path = Path(root)
            if any(part.startswith(".") or part in {"node_modules", "vendor", "__pycache__", ".git"}
                   for part in root_path.parts):
                continue
            rel_root = str(root_path.relative_to(repo_path))
            # Check directory names
            if any(ind.rstrip("/") in rel_root for ind in test_indicators if ind.endswith("/")):
                test_count += len([f for f in files if f.endswith((".py", ".js", ".ts", ".go", ".rs"))])
            # Check file patterns
            for pattern in test_indicators:
                if not pattern.endswith("/"):
                    for fname in files:
                        if fnmatch.fnmatch(fname, pattern):
                            test_count += 1
        return test_count > 0, test_count

    def _extract_dependencies(self, repo_path: Path) -> List[str]:
        """Extract dependency names from package files."""
        deps: Set[str] = set()
        dep_files = {
            "requirements.txt": lambda p: [line.strip().split("=")[0].split("[")[0].lower()
                                            for line in p.read_text(errors="ignore").splitlines()
                                            if line.strip() and not line.startswith("#")],
            "setup.py": lambda p: re.findall(r'[\"\']([\w-]+)[\"\']\s*[>,=!~]', p.read_text(errors="ignore")),
            "pyproject.toml": lambda p: re.findall(r'([\w-]+)\s*[=<>!~]', p.read_text(errors="ignore")),
            "Pipfile": lambda p: re.findall(r'([\w-]+)\s*=', p.read_text(errors="ignore")),
            "package.json": lambda p: list(json.loads(p.read_text(errors="ignore") or "{}").get("dependencies", {}).keys()),
            "go.mod": lambda p: re.findall(r'require\s+([\w./-]+)', p.read_text(errors="ignore")),
            "Cargo.toml": lambda p: re.findall(r'([\w-]+)\s*=', p.read_text(errors="ignore")),
            "Gemfile": lambda p: re.findall(r"gem\s+['\"]([\w-]+)['\"]", p.read_text(errors="ignore")),
        }
        for fname, extractor in dep_files.items():
            fpath = repo_path / fname
            if fpath.exists():
                try:
                    extracted = extractor(fpath)
                    deps.update(extracted)
                except Exception:
                    pass
        return sorted(deps)

    def _get_file_tree(self, repo_path: Path, max_depth: int = 4) -> str:
        """Generate a textual file tree of the repository."""
        lines: List[str] = []
        for root, dirs, files in os.walk(repo_path):
            root_path = Path(root)
            depth = len(root_path.relative_to(repo_path).parts)
            if depth > max_depth:
                del dirs[:]
                continue
            if any(part.startswith(".") or part in {"node_modules", "vendor", "__pycache__", ".git"}
                   for part in root_path.parts):
                del dirs[:]
                continue
            indent = "  " * depth
            rel = root_path.name if depth == 0 else root_path.relative_to(repo_path).name
            if depth > 0:
                lines.append(f"{indent}{rel}/")
            for fname in sorted(files)[:20]:  # cap files per dir
                lines.append(f"{indent}  {fname}")
            if len(files) > 20:
                lines.append(f"{indent}  ... ({len(files) - 20} more files)")
        return "\n".join(lines)

    def _get_readme_length(self, repo_path: Path) -> int:
        """Get the character count of the README file."""
        for readme_name in ["README.md", "README.rst", "README.txt", "README"]:
            readme_path = repo_path / readme_name
            if readme_path.exists():
                try:
                    return len(readme_path.read_text(encoding="utf-8", errors="ignore"))
                except IOError:
                    pass
        return 0

    def _compute_quality_score(self, repo_info: Dict[str, Any]) -> float:
        """Compute a composite quality score (0.0 - 1.0) for a repository."""
        score = 0.0
        # Stars (max contribution 0.3)
        stars = repo_info.get("stars", 0)
        score += min(stars / 10000, 0.3)
        # Forks (max contribution 0.15)
        forks = repo_info.get("forks", 0)
        score += min(forks / 2000, 0.15)
        # Has tests (0.2)
        if repo_info.get("has_tests", False):
            score += 0.2
        # README length (max 0.1)
        readme_len = repo_info.get("readme_length", 0)
        score += min(readme_len / 10000, 0.1)
        # Recent activity (0.15)
        updated = repo_info.get("last_updated", "")
        if updated:
            try:
                from datetime import timezone
                last = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc) if last.tzinfo else datetime.now()
                days_ago = (now - last).days
                if days_ago < 30:
                    score += 0.15
                elif days_ago < 90:
                    score += 0.1
                elif days_ago < 365:
                    score += 0.05
            except ValueError:
                pass
        # Architecture patterns (max 0.1)
        arch_patterns = repo_info.get("architecture_patterns", [])
        score += min(len(arch_patterns) * 0.02, 0.1)
        return round(min(score, 1.0), 3)

    # ═══════════════════════════════════════════════════════════════════════
    # Mass Discovery
    # ═══════════════════════════════════════════════════════════════════════

    def discover_repos(self, topics: List[str], max_results: int = 2000) -> List[Dict[str, Any]]:
        """
        Discover repositories by topic using GitHub Search API.

        Applies quality filters:
        - Minimum stars threshold
        - Has README
        - Recent activity (within max_age_days)
        - Not a fork

        Args:
            topics: List of GitHub topics to search
            max_results: Maximum total results across all topics

        Returns:
            List of repo dicts with keys:
            full_name, url, stars, forks, language, license, topics, description,
            last_updated, open_issues, size_kb, has_wiki
        """
        all_repos: List[Dict[str, Any]] = []
        per_topic = max(1, max_results // len(topics)) if topics else max_results

        for topic in topics:
            logger.info("Discovering repos for topic: %s", topic)
            page = 1
            per_page = min(100, per_topic)
            topic_repos: List[Dict[str, Any]] = []

            while len(topic_repos) < per_topic and page <= 10:
                # Build search query with quality filters
                query_parts = [
                    f"topic:{topic}",
                    f"stars:>={self.min_stars}",
                    "fork:false",
                    "archived:false",
                ]
                if self.max_age_days:
                    cutoff = (datetime.now() - timedelta(days=self.max_age_days)).strftime("%Y-%m-%d")
                    query_parts.append(f"pushed:>={cutoff}")

                query = " ".join(query_parts)
                params = {"q": query, "sort": "stars", "order": "desc", "per_page": per_page, "page": page}

                cache_key = self._cache_key("discover", topic, str(page), str(per_page), str(self.min_stars))
                cached = self._load_cache(cache_key)
                if cached is not None:
                    data = cached
                else:
                    data = self._github_api_get(GITHUB_SEARCH_API, params)
                    self._save_cache(cache_key, data)

                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    license_info = item.get("license") or {}
                    license_key = (license_info.get("key") or "unknown").lower()
                    repo = {
                        "full_name": item.get("full_name", ""),
                        "url": item.get("html_url", ""),
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "language": item.get("language") or "Unknown",
                        "license": license_key,
                        "topics": item.get("topics", []),
                        "description": item.get("description") or "",
                        "last_updated": item.get("pushed_at") or item.get("updated_at", ""),
                        "open_issues": item.get("open_issues_count", 0),
                        "size_kb": item.get("size", 0),
                        "has_wiki": item.get("has_wiki", False),
                        "has_tests": False,  # Will be determined during analysis
                        "readme_length": 0,
                        "file_count": 0,
                        "test_file_count": 0,
                        "dependency_count": 0,
                        "architecture_patterns": [],
                        "quality_score": 0.0,
                        "raw_metadata": item,
                    }
                    topic_repos.append(repo)
                    if len(topic_repos) >= per_topic:
                        break

                page += 1

            logger.info("Topic '%s': found %d repos", topic, len(topic_repos))
            all_repos.extend(topic_repos)

        self.stats["repos_discovered"] += len(all_repos)
        return all_repos

    def filter_by_license(self, repos: List[Dict[str, Any]], allowed_licenses: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Filter repositories by open-source license compatibility.

        Args:
            repos: List of repo dicts from discover_repos()
            allowed_licenses: List of allowed license keys (e.g., ["mit", "apache-2.0"])
                             Defaults to self.allowed_licenses

        Returns:
            Filtered list of repos with compatible licenses
        """
        allowed = [l.lower() for l in (allowed_licenses or self.allowed_licenses)]
        filtered = []
        for repo in repos:
            license_key = (repo.get("license") or "unknown").lower()
            if license_key in allowed:
                filtered.append(repo)
            else:
                logger.debug("Excluded %s: license '%s' not in allowed list", repo.get("full_name"), license_key)
        logger.info("License filter: %d → %d repos", len(repos), len(filtered))
        return filtered

    def rank_by_quality(self, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rank repositories by composite quality score.

        Quality factors:
        - Stars (30%)
        - Forks (15%)
        - Has tests (20%)
        - README completeness (10%)
        - Recent activity (15%)
        - Architecture patterns detected (10%)

        Args:
            repos: List of repo dicts

        Returns:
            Repos sorted by quality_score descending
        """
        for repo in repos:
            repo["quality_score"] = self._compute_quality_score(repo)

        ranked = sorted(repos, key=lambda r: r["quality_score"], reverse=True)
        logger.info("Ranked %d repos by quality", len(ranked))
        return ranked

    # ═══════════════════════════════════════════════════════════════════════
    # Deep Analysis
    # ═══════════════════════════════════════════════════════════════════════

    def clone_and_analyze(self, repo_url: str) -> Dict[str, Any]:
        """
        Perform deep analysis of a single repository.

        Steps:
        1. Clone repository to temp directory
        2. Count files by language
        3. Extract architecture patterns
        4. Find main modules/classes
        5. Check for tests
        6. Extract dependencies
        7. Generate capability summary
        8. Check for malware patterns

        Args:
            repo_url: Git clone URL (https or ssh)

        Returns:
            Analysis dict with all extracted information
        """
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        clone_dest = self.clone_dir / f"{repo_name}_{int(time.time())}"
        logger.info("Analyzing repo: %s", repo_url)

        analysis: Dict[str, Any] = {
            "repo_url": repo_url,
            "repo_name": repo_name,
            "clone_success": False,
            "clone_path": str(clone_dest),
            "file_counts": {},
            "architecture_patterns": [],
            "main_modules": [],
            "has_tests": False,
            "test_file_count": 0,
            "dependencies": [],
            "capability_summary": "",
            "malware_detected": False,
            "malware_details": [],
            "readme_length": 0,
            "total_files": 0,
            "license": "unknown",
            "skills": [],
            "errors": [],
            "provenance": {
                "source_url": repo_url,
                "analyzed_at": datetime.now().isoformat(),
                "analyzer_version": "1.0.0",
            },
        }

        # Step 1: Clone
        if not self._clone_repo(repo_url, clone_dest):
            analysis["errors"].append("Failed to clone repository")
            self.stats["repos_failed"] += 1
            return analysis
        analysis["clone_success"] = True

        try:
            # Step 8: Malware check (do this first for safety)
            is_clean, malware_details = self._scan_for_malware_patterns(clone_dest)
            analysis["malware_detected"] = not is_clean
            analysis["malware_details"] = malware_details
            if not is_clean:
                logger.warning("MALWARE DETECTED in %s — analysis aborted", repo_url)
                self.stats["malware_detected"] += 1
                analysis["errors"].append(f"Malware patterns detected: {malware_details}")
                shutil.rmtree(clone_dest, ignore_errors=True)
                return analysis

            # Step 2: File counts
            analysis["file_counts"] = self._count_files_by_language(clone_dest)
            analysis["total_files"] = sum(analysis["file_counts"].values())

            # Step 3: Architecture patterns
            analysis["architecture_patterns"] = self._detect_architecture_patterns(clone_dest)

            # Step 4: Main modules
            primary_lang = max(analysis["file_counts"], key=analysis["file_counts"].get) if analysis["file_counts"] else "Python"
            analysis["main_modules"] = self._find_main_modules(clone_dest, primary_lang)

            # Step 5: Tests
            has_tests, test_count = self._check_for_tests(clone_dest)
            analysis["has_tests"] = has_tests
            analysis["test_file_count"] = test_count

            # Step 6: Dependencies
            analysis["dependencies"] = self._extract_dependencies(clone_dest)

            # README length
            analysis["readme_length"] = self._get_readme_length(clone_dest)

            # Detect license
            analysis["license"] = self._detect_license(clone_dest)

            # Step 7: Capability summary
            file_tree = self._get_file_tree(clone_dest)
            loop = asyncio.new_event_loop()
            try:
                summary = loop.run_until_complete(
                    self.llm.summarize_repo(
                        {"full_name": repo_name, "description": "", "language": primary_lang,
                         "topics": [], "stars": 0}, file_tree
                    )
                )
                analysis["capability_summary"] = summary
            except Exception as exc:
                logger.warning("LLM summary failed: %s", exc)
                analysis["capability_summary"] = f"{repo_name}: {primary_lang} project with {analysis['total_files']} files."
            finally:
                loop.close()

            # Extract skills
            analysis["skills"] = self.extract_skills(analysis)

            self.stats["repos_analyzed"] += 1
            self.stats["skills_extracted"] += len(analysis["skills"])

        except Exception as exc:
            logger.error("Analysis failed for %s: %s", repo_url, exc)
            analysis["errors"].append(str(exc))
            self.stats["repos_failed"] += 1
        finally:
            # Cleanup clone
            shutil.rmtree(clone_dest, ignore_errors=True)

        return analysis

    def _detect_license(self, repo_path: Path) -> str:
        """Detect the license of a cloned repository."""
        # Check LICENSE file
        for license_name in ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"]:
            license_path = repo_path / license_name
            if license_path.exists():
                content = license_path.read_text(encoding="utf-8", errors="ignore").lower()
                if "mit license" in content:
                    return "mit"
                elif "apache license" in content or "apache-2" in content:
                    return "apache-2.0"
                elif "gnu general public license" in content:
                    if "version 3" in content:
                        return "gpl-3.0"
                    return "gpl-2.0"
                elif "bsd 3" in content or "3-clause" in content:
                    return "bsd-3-clause"
                elif "bsd 2" in content or "2-clause" in content:
                    return "bsd-2-clause"
                elif "isc license" in content:
                    return "isc"
                elif "unlicense" in content:
                    return "unlicense"
                elif "mozilla public license" in content:
                    return "mpl-2.0"
        # Check package metadata
        for pkg_file, license_key in [("setup.py", "mit"), ("pyproject.toml", "mit"),
                                       ("package.json", "mit"), ("Cargo.toml", "mit")]:
            pkg_path = repo_path / pkg_file
            if pkg_path.exists():
                content = pkg_path.read_text(encoding="utf-8", errors="ignore").lower()
                match = re.search(r'license\s*[=:]\s*["\']?([\w\-.]+)', content)
                if match:
                    return match.group(1).lower()
        return "unknown"

    def _scan_for_malware_patterns(self, repo_path: Path) -> Tuple[bool, List[str]]:
        """
        Scan repository for known malware patterns.

        Returns:
            (is_clean, list_of_detected_patterns)
        """
        detected: List[str] = []
        for root, _dirs, files in os.walk(repo_path):
            root_path = Path(root)
            if ".git" in root_path.parts:
                continue
            for fname in files:
                if not fname.lower().endswith((".py", ".js", ".sh", ".bash", ".ps1", ".go", ".rs", ".java")):
                    continue
                fpath = root_path / fname
                try:
                    content = fpath.read_bytes()
                    for pattern in MALWARE_PATTERNS:
                        if pattern.search(content):
                            pattern_str = pattern.pattern.decode("utf-8", errors="ignore")[:80]
                            detected.append(f"{fpath.name}: {pattern_str}")
                            logger.warning("Malware pattern in %s: %s", fpath, pattern_str)
                except IOError:
                    pass
        return len(detected) == 0, detected

    def extract_skills(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract implementable skills from a repository analysis.

        Looks at:
        - Main modules and their purposes
        - Architecture patterns (microservices, event-driven, etc.)
        - Dependency graph insights
        - Test structure patterns

        Args:
            analysis: Output from clone_and_analyze()

        Returns:
            List of skill dicts with keys:
            name, description, source_repo, source_license, skill_type,
            code_pattern, confidence, dependencies
        """
        skills: List[Dict[str, Any]] = []
        repo_name = analysis.get("repo_name", "unknown")
        license_key = analysis.get("license", "unknown")

        if not analysis.get("clone_success"):
            return skills

        # Extract from architecture patterns
        for arch_pattern in analysis.get("architecture_patterns", []):
            skills.append({
                "name": f"{arch_pattern.replace('_', '-').title()} Architecture",
                "description": f"Implements a {arch_pattern.replace('_', ' ')} architecture pattern",
                "source_repo": repo_name,
                "source_license": license_key,
                "skill_type": "architecture",
                "code_pattern": f"#{arch_pattern}_pattern",
                "confidence": 0.85,
                "dependencies": [],
            })

        # Extract from main modules
        for module in analysis.get("main_modules", [])[:10]:
            mod_type = module.get("type", "unknown")
            mod_name = module.get("name", "unknown")
            mod_file = module.get("file", "")
            skills.append({
                "name": f"{mod_name} ({mod_type})",
                "description": f"{mod_type.title()} {mod_name} from {mod_file}",
                "source_repo": repo_name,
                "source_license": license_key,
                "skill_type": "pattern" if mod_type == "class" else "algorithm",
                "code_pattern": f"{mod_type}:{mod_name}",
                "confidence": 0.7,
                "dependencies": analysis.get("dependencies", [])[:5],
            })

        # Extract from test patterns
        if analysis.get("has_tests"):
            test_frameworks = []
            for dep in analysis.get("dependencies", []):
                if dep.lower() in {"pytest", "unittest", "jest", "mocha", "vitest", "gtest"}:
                    test_frameworks.append(dep)
            skills.append({
                "name": f"Testing with {', '.join(test_frameworks) or 'built-in'}",
                "description": f"Uses {test_frameworks or 'testing framework'} for quality assurance",
                "source_repo": repo_name,
                "source_license": license_key,
                "skill_type": "pattern",
                "code_pattern": "#testing_pattern",
                "confidence": 0.8,
                "dependencies": test_frameworks,
            })

        # Extract from dependency insights
        if analysis.get("dependencies"):
            # Group by domain
            ml_deps = [d for d in analysis["dependencies"] if d.lower() in {
                "torch", "tensorflow", "jax", "numpy", "pandas", "scikit-learn",
                "transformers", "onnx", "mlflow", "wandb", "optuna",
            }]
            web_deps = [d for d in analysis["dependencies"] if d.lower() in {
                "fastapi", "flask", "django", "starlette", "uvicorn", "requests",
            }]
            if ml_deps:
                skills.append({
                    "name": f"ML Stack: {', '.join(ml_deps[:3])}",
                    "description": f"Machine learning pipeline using {', '.join(ml_deps)}",
                    "source_repo": repo_name,
                    "source_license": license_key,
                    "skill_type": "integration",
                    "code_pattern": "#ml_pipeline",
                    "confidence": 0.75,
                    "dependencies": ml_deps,
                })
            if web_deps:
                skills.append({
                    "name": f"Web API with {', '.join(web_deps[:3])}",
                    "description": f"Web service using {', '.join(web_deps)}",
                    "source_repo": repo_name,
                    "source_license": license_key,
                    "skill_type": "integration",
                    "code_pattern": "#web_api",
                    "confidence": 0.75,
                    "dependencies": web_deps,
                })

        logger.info("Extracted %d skills from %s", len(skills), repo_name)
        return skills

    def generate_integration_code(self, skill: Dict[str, Any]) -> str:
        """
        Generate bridge/integration code for a learned skill.

        Creates a JARVIS-compatible skill module that wraps the learned pattern
        with proper attribution and safety checks.

        Args:
            skill: Skill dict from extract_skills()

        Returns:
            Python source code string for the integration module
        """
        name = skill.get("name", "UnknownSkill").replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")
        description = skill.get("description", "")
        source_repo = skill.get("source_repo", "unknown")
        source_license = skill.get("source_license", "unknown")
        skill_type = skill.get("skill_type", "pattern")
        dependencies = skill.get("dependencies", [])

        code = f'''#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
JARVIS Learned Skill: {name}
═══════════════════════════════════════════════════════════════════════════════
Learned from: {source_repo}
License: {source_license}
Skill type: {skill_type}
Description: {description}

PROVENANCE:
  - Source repository: {source_repo}
  - Source license: {source_license}
  - Learned at: {datetime.now().isoformat()}
  - Auto-generated by: JARVIS GitHub Mass Ingestor v1.0

This module was auto-generated by analyzing open-source code patterns.
It implements the learned pattern with clean-room methodology.
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger("jarvis.skills.{name.lower()}")

# ---------------------------------------------------------------------------
# Dependencies (install as needed):
#   pip install {" ".join(dependencies) if dependencies else "# none required"}
# ---------------------------------------------------------------------------

# Attempt to import optional dependencies
try:
'''
        for dep in dependencies[:5]:
            safe_dep = dep.replace("-", "_")
            code += f'''    import {safe_dep}
'''
        if not dependencies:
            code += '''    pass  # No external dependencies
'''
        code += f'''except ImportError as _imp_err:
    logger.debug("Optional dependency not available: %s", _imp_err)


class {name}Skill:
    """
    JARVIS skill implementation learned from {source_repo}.
    
    {description}
    """
    
    SKILL_NAME = "{name}"
    SOURCE_REPO = "{source_repo}"
    SOURCE_LICENSE = "{source_license}"
    SKILL_TYPE = "{skill_type}"
    CONFIDENCE = {skill.get("confidence", 0.5)}
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {{}}
        self._initialized = False
        self._state: Dict[str, Any] = {{}}
        
    def initialize(self) -> bool:
        """Initialize the skill. Returns True on success."""
        logger.info("Initializing %s skill", self.SKILL_NAME)
        self._initialized = True
        return True
        
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the learned skill.
        
        Args:
            inputs: Task inputs as a dictionary
            
        Returns:
            Results dictionary
        """
        if not self._initialized:
            self.initialize()
            
        logger.info("Executing %s skill", self.SKILL_NAME)
        
        # TODO: Implement the learned pattern here
        # This is a template — the actual implementation should be
        # derived from the source pattern with clean-room methodology
        
        return {{
            "skill": self.SKILL_NAME,
            "source": self.SOURCE_REPO,
            "license": self.SOURCE_LICENSE,
            "status": "executed",
            "outputs": {{}},
        }}
        
    def get_metadata(self) -> Dict[str, Any]:
        """Return skill metadata for JARVIS skill registry."""
        return {{
            "name": self.SKILL_NAME,
            "description": """{description}""",
            "source_repo": self.SOURCE_REPO,
            "source_license": self.SOURCE_LICENSE,
            "skill_type": self.SKILL_TYPE,
            "confidence": self.CONFIDENCE,
            "dependencies": {dependencies},
            "version": "1.0.0",
        }}
        
    def health_check(self) -> Dict[str, Any]:
        """Verify skill health and dependencies."""
        status = {{"name": self.SKILL_NAME, "healthy": True, "checks": {{}}}}
'''
        for dep in dependencies[:5]:
            safe_dep = dep.replace("-", "_")
            code += f'''        try:
            import {safe_dep}
            status["checks"]["{safe_dep}"] = "available"
        except ImportError:
            status["checks"]["{safe_dep}"] = "missing"
            status["healthy"] = False
'''
        if not dependencies:
            code += '''        status["checks"]["dependencies"] = "none required"
'''
        code += f'''        return status


# ---------------------------------------------------------------------------
# JARVIS Integration Hook
# ---------------------------------------------------------------------------

def register_skill(registry: Any) -> None:
    """Register this skill with the JARVIS skill registry."""
    skill = {name}Skill()
    registry.register(
        name=skill.SKILL_NAME,
        factory=lambda cfg: {name}Skill(cfg),
        metadata=skill.get_metadata(),
    )
    logger.info("Registered skill: %s", skill.SKILL_NAME)


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    skill = {name}Skill()
    print(f"Skill: {{skill.SKILL_NAME}}")
    print(f"Source: {{skill.SOURCE_REPO}} ({{skill.SOURCE_LICENSE}})")
    print(f"Health: {{skill.health_check()}}")
    print(f"Metadata: {{skill.get_metadata()}}")
'''

        # Sanitize the generated code
        return self.sanitize_code(code)

    # ═══════════════════════════════════════════════════════════════════════
    # Batch Processing
    # ═══════════════════════════════════════════════════════════════════════

    def ingest_batch(self, repos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process multiple repositories in batch.

        Args:
            repos: List of repo dicts (from discover_repos + filtering)

        Returns:
            Summary dict with:
            processed, skills_learned, failed, details (per-repo results)
        """
        results = {
            "processed": 0,
            "skills_learned": 0,
            "failed": 0,
            "details": [],
            "start_time": datetime.now().isoformat(),
            "end_time": "",
            "malware_detected": 0,
        }

        for i, repo in enumerate(repos):
            repo_url = repo.get("url", "")
            if not repo_url:
                continue

            logger.info("[%d/%d] Ingesting %s", i + 1, len(repos), repo.get("full_name", repo_url))

            try:
                analysis = self.clone_and_analyze(repo_url)

                if analysis.get("malware_detected"):
                    results["malware_detected"] += 1
                    results["failed"] += 1
                    results["details"].append({
                        "repo": repo.get("full_name", repo_url),
                        "status": "rejected_malware",
                        "malware_details": analysis.get("malware_details", []),
                    })
                    continue

                if analysis.get("errors"):
                    results["failed"] += 1
                    results["details"].append({
                        "repo": repo.get("full_name", repo_url),
                        "status": "failed",
                        "errors": analysis["errors"],
                    })
                    continue

                skills = analysis.get("skills", [])
                integration_codes = []
                for skill in skills:
                    integration_code = self.generate_integration_code(skill)
                    integration_codes.append({
                        "skill": skill,
                        "integration_code": integration_code,
                    })

                results["processed"] += 1
                results["skills_learned"] += len(skills)
                results["details"].append({
                    "repo": repo.get("full_name", repo_url),
                    "status": "success",
                    "skills_count": len(skills),
                    "architecture_patterns": analysis.get("architecture_patterns", []),
                    "file_counts": analysis.get("file_counts", {}),
                    "dependencies": analysis.get("dependencies", []),
                    "capability_summary": analysis.get("capability_summary", ""),
                    "integration_codes": integration_codes,
                    "provenance": analysis.get("provenance", {}),
                })

            except Exception as exc:
                logger.error("Batch ingestion failed for %s: %s", repo_url, exc)
                results["failed"] += 1
                results["details"].append({
                    "repo": repo.get("full_name", repo_url),
                    "status": "error",
                    "error": str(exc),
                })

        results["end_time"] = datetime.now().isoformat()
        logger.info(
            "Batch complete: %d processed, %d skills learned, %d failed, %d malware",
            results["processed"],
            results["skills_learned"],
            results["failed"],
            results["malware_detected"],
        )
        return results

    def ingest_from_topics(self, topics: List[str], max_per_topic: int = 100) -> Dict[str, Any]:
        """
        End-to-end topic-driven mass ingestion pipeline.

        Combines discovery, filtering, ranking, and batch ingestion into
        a single workflow.

        Args:
            topics: List of GitHub topics to search
            max_per_topic: Maximum repos to analyze per topic

        Returns:
            Full pipeline result with discovery and ingestion stats
        """
        logger.info("═" * 60)
        logger.info("JARVIS MASS INGESTION PIPELINE")
        logger.info("Topics: %s", topics)
        logger.info("Max per topic: %d", max_per_topic)
        logger.info("═" * 60)

        pipeline_result = {
            "topics": topics,
            "discovery": {},
            "filtered": {},
            "ranked": {},
            "ingestion": {},
            "total_stats": dict(self.stats),
        }

        # Step 1: Discover
        total_max = max_per_topic * len(topics)
        repos = self.discover_repos(topics, max_results=total_max)
        pipeline_result["discovery"] = {
            "total_found": len(repos),
            "per_topic": dict(Counter(r.get("language", "Unknown") for r in repos)),
        }

        # Step 2: Filter by license
        licensed = self.filter_by_license(repos)
        pipeline_result["filtered"] = {
            "after_license_filter": len(licensed),
            "removed": len(repos) - len(licensed),
        }

        # Step 3: Rank by quality
        ranked = self.rank_by_quality(licensed)
        # Take top N per topic
        topic_counts: Dict[str, int] = defaultdict(int)
        final_selection: List[Dict[str, Any]] = []
        for repo in ranked:
            repo_topics = repo.get("topics", [])
            matching = [t for t in topics if t in repo_topics or t.replace("-", "") in [rt.replace("-", "") for rt in repo_topics]]
            topic_key = matching[0] if matching else "other"
            if topic_counts[topic_key] < max_per_topic:
                final_selection.append(repo)
                topic_counts[topic_key] += 1

        pipeline_result["ranked"] = {
            "selected_for_ingestion": len(final_selection),
            "per_topic": dict(topic_counts),
            "avg_quality_score": round(
                sum(r.get("quality_score", 0) for r in final_selection) / len(final_selection), 3
            ) if final_selection else 0,
        }

        # Step 4: Ingest batch
        ingestion = self.ingest_batch(final_selection)
        pipeline_result["ingestion"] = ingestion

        pipeline_result["total_stats"] = dict(self.stats)
        pipeline_result["completed_at"] = datetime.now().isoformat()

        logger.info("═" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("  Repos discovered:  %d", pipeline_result["discovery"]["total_found"])
        logger.info("  After filtering:   %d", pipeline_result["filtered"]["after_license_filter"])
        logger.info("  Selected:          %d", pipeline_result["ranked"]["selected_for_ingestion"])
        logger.info("  Successfully processed: %d", ingestion["processed"])
        logger.info("  Skills learned:    %d", ingestion["skills_learned"])
        logger.info("  Failed:            %d", ingestion["failed"])
        logger.info("  Malware detected:  %d", ingestion["malware_detected"])
        logger.info("═" * 60)

        return pipeline_result

    # ═══════════════════════════════════════════════════════════════════════
    # Quality & Safety
    # ═══════════════════════════════════════════════════════════════════════

    def check_for_malware(self, repo_path: str) -> bool:
        """
        Check a repository path for known malware patterns.

        Args:
            repo_path: Local filesystem path to the cloned repository

        Returns:
            True if malware was detected, False if clean
        """
        path = Path(repo_path)
        if not path.exists():
            logger.error("Path does not exist: %s", repo_path)
            return False

        is_clean, detected = self._scan_for_malware_patterns(path)
        if not is_clean:
            logger.warning("Malware detected in %s: %d patterns", repo_path, len(detected))
            for d in detected:
                logger.warning("  - %s", d)
        return not is_clean

    def check_license_compatibility(self, license_key: str) -> bool:
        """
        Check if a license is compatible with JARVIS integration.

        JARVIS prefers permissive licenses (MIT, Apache-2.0, BSD)
        but also allows GPL-family for non-proprietary use.

        Args:
            license_key: SPDX license identifier (e.g., "mit", "apache-2.0")

        Returns:
            True if the license allows learning/integration
        """
        license_lower = license_key.lower().strip()

        # Direct match in allowed list
        if license_lower in [l.lower() for l in self.allowed_licenses]:
            return True

        # Handle common variations
        license_aliases = {
            "apache license 2.0": "apache-2.0",
            "apache 2.0": "apache-2.0",
            "apache software license": "apache-2.0",
            "mit license": "mit",
            "bsd license": "bsd-3-clause",
            "bsd 3-clause": "bsd-3-clause",
            "gnu gpl v3": "gpl-3.0",
            "gnu gpl v2": "gpl-2.0",
            "gplv3": "gpl-3.0",
            "gplv2": "gpl-2.0",
            "mozilla public license 2.0": "mpl-2.0",
            "unlicense": "unlicense",
        }
        normalized = license_aliases.get(license_lower, license_lower)

        if normalized in [l.lower() for l in self.allowed_licenses]:
            return True

        logger.info("License '%s' not in compatibility list", license_key)
        return False

    def sanitize_code(self, code: str) -> str:
        """
        Remove potentially harmful patterns from extracted code.

        Sanitization rules:
        - Remove eval()/exec() calls with dynamic content
        - Remove os.system() / subprocess.call() with shell=True
        - Remove hardcoded credentials patterns
        - Remove network callbacks to external IPs
        - Flag pickle.loads() with untrusted data
        - Remove __import__ obfuscation patterns

        Args:
            code: Source code string to sanitize

        Returns:
            Sanitized code string with harmful patterns removed/flagged
        """
        original = code
        lines = code.splitlines()
        sanitized_lines: List[str] = []
        removed_patterns: List[str] = []

        for line in lines:
            original_line = line
            line_lower = line.lower().strip()
            should_remove = False

            # Rule 1: eval() with dynamic content
            if re.search(r'eval\s*\([^)]*(?:input|request|socket|recv)', line, re.IGNORECASE):
                should_remove = True
                removed_patterns.append("eval() with dynamic input")

            # Rule 2: exec() with dynamic content
            if re.search(r'exec\s*\([^)]*(?:input|request|socket|recv|base64|decode)', line, re.IGNORECASE):
                should_remove = True
                removed_patterns.append("exec() with dynamic/obfuscated input")

            # Rule 3: os.system() / subprocess with shell=True and dynamic input
            if re.search(r'os\.system\s*\(|subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True', line, re.IGNORECASE):
                # Only flag if dynamic input is involved
                if re.search(r'(?:input|request|socket|recv|\{.*\}|%s|\+)', line):
                    should_remove = True
                    removed_patterns.append("shell execution with dynamic input")

            # Rule 4: Hardcoded credentials
            if re.search(r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']', line, re.IGNORECASE):
                # Replace with placeholder
                line = re.sub(
                    r'((?:password|secret|api_key|token)\s*=\s*)["\'][^"\']{8,}["\']',
                    r'\1"<REDACTED>"',
                    line,
                    flags=re.IGNORECASE,
                )
                removed_patterns.append("hardcoded credential redacted")

            # Rule 5: Network callbacks to raw IPs
            if re.search(r'socket\..*connect\s*\(\s*\(\s*["\']\d+\.\d+\.\d+\.\d+["\']', line):
                should_remove = True
                removed_patterns.append("raw IP network connection")

            # Rule 6: pickle with untrusted data
            if re.search(r'pickle\.loads?\s*\([^)]*(?:socket|request|recv|network)', line, re.IGNORECASE):
                should_remove = True
                removed_patterns.append("pickle with network data")

            # Rule 7: __import__ obfuscation
            if re.search(r'__import__\s*\(\s*["\']\w+["\']\s*\)\..*(?:system|eval|exec|Popen)', line):
                should_remove = True
                removed_patterns.append("__import__ obfuscation")

            # Rule 8: ctypes dynamic execution
            if re.search(r'ctypes\.(?:CDLL|windll|dllload)', line_lower):
                if "libc" in line_lower or "kernel32" in line_lower:
                    should_remove = True
                    removed_patterns.append("ctypes foreign function call")

            if should_remove:
                sanitized_lines.append(f"# [SANITIZED: harmful pattern removed]")
                sanitized_lines.append(f"# Original: {original_line.strip()}")
            else:
                sanitized_lines.append(line)

        result = "\n".join(sanitized_lines)

        if removed_patterns:
            header = (
                f"# {'='*60}\n"
                f"# SANITIZED CODE — {len(removed_patterns)} pattern(s) removed:\n"
            )
            for p in set(removed_patterns):
                header += f"#   - {p}\n"
            header += f"# {'='*60}\n"
            result = header + result

        return result

    # ═══════════════════════════════════════════════════════════════════════
    # Stats & Utilities
    # ═══════════════════════════════════════════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        """Return current ingestion statistics."""
        return {
            **self.stats,
            "cache_entries": len(list(self.cache_dir.glob("*.json"))),
            "clone_dir_size_mb": self._get_dir_size_mb(self.clone_dir),
            "uptime_seconds": (
                datetime.now() - datetime.fromisoformat(self.stats["start_time"])
            ).total_seconds(),
        }

    @staticmethod
    def _get_dir_size_mb(path: Path) -> float:
        """Calculate directory size in MB."""
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except OSError:
            pass
        return round(total / (1024 * 1024), 2)

    def reset_stats(self) -> None:
        """Reset all statistics counters."""
        self.stats = {
            "api_calls": 0,
            "repos_discovered": 0,
            "repos_analyzed": 0,
            "repos_failed": 0,
            "skills_extracted": 0,
            "malware_detected": 0,
            "start_time": datetime.now().isoformat(),
        }
        logger.info("Statistics reset")

    def clear_cache(self) -> int:
        """Clear all cached data. Returns number of files removed."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
        self._cache.clear()
        logger.info("Cleared %d cache entries", count)
        return count


# ═══════════════════════════════════════════════════════════════════════════
# Mock Ingestor — for testing and development without API access
# ═══════════════════════════════════════════════════════════════════════════

class MockGitHubMassIngestor(GitHubMassIngestor):
    """
    Mock implementation of GitHubMassIngestor for testing.

    Returns pre-defined sample repositories and simulates analysis
    without making any network calls.
    """

    SAMPLE_REPOS: List[Dict[str, Any]] = [
        {
            "full_name": "joaomdmoura/crewAI",
            "url": "https://github.com/joaomdmoura/crewAI",
            "stars": 25600,
            "forks": 3500,
            "language": "Python",
            "license": "mit",
            "topics": ["ai-agents", "automation", "llm", "multi-agent"],
            "description": "Framework for orchestrating role-playing, autonomous AI agents",
            "last_updated": (datetime.now() - timedelta(days=5)).isoformat(),
            "open_issues": 180,
            "size_kb": 25600,
            "has_wiki": True,
        },
        {
            "full_name": "microsoft/autogen",
            "url": "https://github.com/microsoft/autogen",
            "stars": 36800,
            "forks": 5400,
            "language": "Python",
            "license": "mit",
            "topics": ["ai-agents", "llm", "multi-agent", "automation"],
            "description": "A programming framework for agentic AI",
            "last_updated": (datetime.now() - timedelta(days=2)).isoformat(),
            "open_issues": 420,
            "size_kb": 89200,
            "has_wiki": True,
        },
        {
            "full_name": "Significant-Gravitas/AutoGPT",
            "url": "https://github.com/Significant-Gravitas/AutoGPT",
            "stars": 168000,
            "forks": 44200,
            "language": "Python",
            "license": "mit",
            "topics": ["ai-agents", "automation", "llm", "agi"],
            "description": "An experimental open-source attempt at making GPT-4 fully autonomous",
            "last_updated": (datetime.now() - timedelta(days=1)).isoformat(),
            "open_issues": 250,
            "size_kb": 345600,
            "has_wiki": True,
        },
        {
            "full_name": "langchain-ai/langchain",
            "url": "https://github.com/langchain-ai/langchain",
            "stars": 102000,
            "forks": 15800,
            "language": "Python",
            "license": "mit",
            "topics": ["llm", "nlp", "ai-agents", "rag"],
            "description": "Building applications with LLMs through composability",
            "last_updated": (datetime.now() - timedelta(days=1)).isoformat(),
            "open_issues": 1800,
            "size_kb": 512000,
            "has_wiki": False,
        },
        {
            "full_name": "commaai/openpilot",
            "url": "https://github.com/commaai/openpilot",
            "stars": 51200,
            "forks": 9200,
            "language": "Python",
            "license": "mit",
            "topics": ["robotics", "automation", "computer-vision", "self-driving"],
            "description": "openpilot is an open source driver assistance system",
            "last_updated": (datetime.now() - timedelta(days=3)).isoformat(),
            "open_issues": 310,
            "size_kb": 1024000,
            "has_wiki": True,
        },
        {
            "full_name": "OpenBB-finance/OpenBBTerminal",
            "url": "https://github.com/OpenBB-finance/OpenBBTerminal",
            "stars": 36800,
            "forks": 3400,
            "language": "Python",
            "license": "mit",
            "topics": ["trading", "finance", "data-analysis", "automation"],
            "description": "Investment Research for Everyone, Everywhere",
            "last_updated": (datetime.now() - timedelta(days=4)).isoformat(),
            "open_issues": 150,
            "size_kb": 678000,
            "has_wiki": True,
        },
        {
            "full_name": "coqui-ai/TTS",
            "url": "https://github.com/coqui-ai/TTS",
            "stars": 34800,
            "forks": 4200,
            "language": "Python",
            "license": "mpl-2.0",
            "topics": ["voice-synthesis", "nlp", "deep-learning", "tts"],
            "description": "Deep learning for Text to Speech",
            "last_updated": (datetime.now() - timedelta(days=60)).isoformat(),
            "open_issues": 520,
            "size_kb": 456000,
            "has_wiki": False,
        },
        {
            "full_name": "ultralytics/ultralytics",
            "url": "https://github.com/ultralytics/ultralytics",
            "stars": 35600,
            "forks": 6900,
            "language": "Python",
            "license": "agpl-3.0",
            "topics": ["computer-vision", "deep-learning", "object-detection", "yolo"],
            "description": "Ultralytics YOLO11 🚀",
            "last_updated": (datetime.now() - timedelta(days=1)).isoformat(),
            "open_issues": 890,
            "size_kb": 234000,
            "has_wiki": True,
        },
        {
            "full_name": "huggingface/transformers",
            "url": "https://github.com/huggingface/transformers",
            "stars": 138000,
            "forks": 27600,
            "language": "Python",
            "license": "apache-2.0",
            "topics": ["nlp", "deep-learning", "llm", "transformers"],
            "description": "State-of-the-art Machine Learning for Pytorch, TensorFlow, and JAX",
            "last_updated": (datetime.now() - timedelta(days=1)).isoformat(),
            "open_issues": 1200,
            "size_kb": 2048000,
            "has_wiki": False,
        },
        {
            "full_name": "psf/requests",
            "url": "https://github.com/psf/requests",
            "stars": 52000,
            "forks": 9400,
            "language": "Python",
            "license": "apache-2.0",
            "topics": ["http", "api-design", "python"],
            "description": "A simple, yet elegant, HTTP library",
            "last_updated": (datetime.now() - timedelta(days=30)).isoformat(),
            "open_issues": 280,
            "size_kb": 56000,
            "has_wiki": True,
        },
    ]

    def __init__(self, **kwargs):
        # Accept same kwargs but override to disable network
        super().__init__(**kwargs)
        self._mock_analyses: Dict[str, Dict[str, Any]] = {}
        self._build_mock_analyses()

    def _build_mock_analyses(self) -> None:
        """Pre-build mock analysis results for sample repos."""
        for repo in self.SAMPLE_REPOS:
            name = repo["full_name"]
            self._mock_analyses[name] = {
                "repo_url": repo["url"],
                "repo_name": name.split("/")[-1],
                "clone_success": True,
                "clone_path": f"/tmp/mock/{name}",
                "file_counts": {repo["language"]: 150, "Markdown": 20, "YAML": 10},
                "architecture_patterns": ["plugin_system", "cli_tool"] if "cli" in repo.get("description", "").lower() else ["web_framework"],
                "main_modules": [
                    {"type": "class", "name": "Agent", "file": f"{name.split('/')[-1]}/core.py", "bases": "BaseModel"},
                    {"type": "class", "name": "Pipeline", "file": f"{name.split('/')[-1]}/pipeline.py", "bases": ""},
                    {"type": "function", "name": "run", "file": f"{name.split('/')[-1]}/main.py", "bases": ""},
                    {"type": "function", "name": "configure", "file": f"{name.split('/')[-1]}/config.py", "bases": ""},
                ],
                "has_tests": True,
                "test_file_count": 45,
                "dependencies": ["numpy", "pydantic", "pytest", "httpx"] if repo["language"] == "Python" else ["jest", "typescript"],
                "capability_summary": f"{name}: {repo['description']}. Implements core patterns for {', '.join(repo['topics'][:2])}.",
                "malware_detected": False,
                "malware_details": [],
                "readme_length": 5000,
                "total_files": 180,
                "license": repo["license"],
                "skills": [],
                "errors": [],
                "provenance": {
                    "source_url": repo["url"],
                    "analyzed_at": datetime.now().isoformat(),
                    "analyzer_version": "1.0.0-mock",
                },
            }
            # Pre-extract skills
            self._mock_analyses[name]["skills"] = self.extract_skills(self._mock_analyses[name])

    def discover_repos(self, topics: List[str], max_results: int = 2000) -> List[Dict[str, Any]]:
        """Return mock repos filtered by topic."""
        logger.info("[MOCK] discover_repos called with topics=%s", topics)
        results = []
        for repo in self.SAMPLE_REPOS:
            repo_topics = set(repo.get("topics", []))
            if any(t in repo_topics or t.replace("-", "") in {rt.replace("-", "") for rt in repo_topics}
                   for t in topics):
                results.append(dict(repo))
            if len(results) >= max_results:
                break
        self.stats["repos_discovered"] += len(results)
        return results

    def clone_and_analyze(self, repo_url: str) -> Dict[str, Any]:
        """Return pre-built mock analysis."""
        logger.info("[MOCK] clone_and_analyze called for %s", repo_url)
        # Find matching mock
        for name, analysis in self._mock_analyses.items():
            if analysis["repo_url"] == repo_url:
                self.stats["repos_analyzed"] += 1
                self.stats["skills_extracted"] += len(analysis.get("skills", []))
                return dict(analysis)
        # Return a generic mock for unknown repos
        return {
            "repo_url": repo_url,
            "repo_name": "unknown",
            "clone_success": True,
            "file_counts": {"Python": 50},
            "architecture_patterns": [],
            "main_modules": [],
            "has_tests": False,
            "test_file_count": 0,
            "dependencies": [],
            "capability_summary": "Mock analysis for unknown repository",
            "malware_detected": False,
            "malware_details": [],
            "readme_length": 1000,
            "total_files": 50,
            "license": "mit",
            "skills": [],
            "errors": [],
            "provenance": {"source_url": repo_url, "analyzed_at": datetime.now().isoformat()},
        }


# ═══════════════════════════════════════════════════════════════════════════
# Factory Function
# ═══════════════════════════════════════════════════════════════════════════

def get_github_mass_ingestor(
    use_mock: bool = False,
    github_token: Optional[str] = None,
    **kwargs,
) -> GitHubMassIngestor:
    """
    Factory function to create a GitHubMassIngestor instance.

    Args:
        use_mock: If True, returns MockGitHubMassIngestor (no network)
        github_token: GitHub personal access token for API access
        **kwargs: Additional configuration passed to the constructor

    Returns:
        GitHubMassIngestor or MockGitHubMassIngestor instance

    Usage:
        # Production usage (requires GITHUB_TOKEN env var or token arg)
        ingestor = get_github_mass_ingestor(github_token="ghp_xxx")

        # Mock usage (for testing/development)
        ingestor = get_github_mass_ingestor(use_mock=True)

        # Full pipeline
        result = ingestor.ingest_from_topics(
            topics=["ai-agents", "computer-vision", "nlp"],
            max_per_topic=10,
        )
    """
    if use_mock:
        logger.info("Creating MockGitHubMassIngestor (no network calls)")
        return MockGitHubMassIngestor(**kwargs)

    token = github_token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        logger.warning(
            "No GitHub token provided. API rate limits will be strict (60 req/hr). "
            "Set GITHUB_TOKEN env var or pass github_token argument."
        )

    logger.info("Creating GitHubMassIngestor")
    return GitHubMassIngestor(github_token=token, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# CLI / Demo
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JARVIS GitHub Mass Ingestor")
    parser.add_argument("--mock", action="store_true", help="Use mock mode (no network)")
    parser.add_argument("--topics", nargs="+", default=["ai-agents", "nlp"],
                        help="Topics to search for")
    parser.add_argument("--max-per-topic", type=int, default=5,
                        help="Max repos per topic")
    parser.add_argument("--token", default="", help="GitHub API token")
    parser.add_argument("--discover-only", action="store_true",
                        help="Only run discovery, skip ingestion")
    parser.add_argument("--output", default="", help="Save results to JSON file")
    args = parser.parse_args()

    # Create ingestor
    ingestor = get_github_mass_ingestor(
        use_mock=args.mock,
        github_token=args.token or None,
    )

    if args.discover_only:
        repos = ingestor.discover_repos(args.topics, max_results=args.max_per_topic * len(args.topics))
        filtered = ingestor.filter_by_license(repos)
        ranked = ingestor.rank_by_quality(filtered)
        print(json.dumps(ranked[:20], indent=2, default=str))
    else:
        result = ingestor.ingest_from_topics(args.topics, max_per_topic=args.max_per_topic)
        print(json.dumps(result, indent=2, default=str))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result if not args.discover_only else ranked, f, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")

    print("\n--- Statistics ---")
    print(json.dumps(ingestor.get_stats(), indent=2, default=str))
