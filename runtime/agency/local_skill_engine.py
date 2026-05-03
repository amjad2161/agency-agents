"""
JARVIS BRAINIAC - Local Skill Engine
Dynamic skill loading, management, and hot-swapping for agency capabilities.
Skills can come from local files, GitHub repos, or vector memory.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# In-memory vector store (simple semantic search fallback)
# --------------------------------------------------------------------------- #

class _SimpleVectorStore:
    """Lightweight in-memory vector store with basic text-similarity search."""

    def __init__(self) -> None:
        self._vectors: Dict[str, Dict[str, Any]] = {}  # skill_id -> {embedding, metadata}

    @staticmethod
    def _text_to_vec(text: str, dim: int = 64) -> List[float]:
        """Hash-based deterministic text embedding (no external deps)."""
        vec = [0.0] * dim
        words = text.lower().split()
        for i, word in enumerate(words):
            h = hashlib.md5(word.encode()).hexdigest()
            for j in range(dim):
                idx = (j * 2) % 32
                vec[j] += int(h[idx : idx + 2], 16) / 255.0
        # Normalise
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        return dot  # already normalised

    def store(self, skill_id: str, text: str, metadata: Dict[str, Any]) -> None:
        self._vectors[skill_id] = {
            "embedding": self._text_to_vec(text),
            "metadata": metadata,
        }

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        qvec = self._text_to_vec(query)
        scored = []
        for sid, data in self._vectors.items():
            score = self._cosine(qvec, data["embedding"])
            scored.append((sid, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def delete(self, skill_id: str) -> None:
        self._vectors.pop(skill_id, None)


# --------------------------------------------------------------------------- #
# LocalSkillEngine
# --------------------------------------------------------------------------- #

class LocalSkillEngine:
    """
    Dynamic skill engine: loads, registers, and hot-swaps capabilities.
    Skills can come from local files, GitHub repos, or vector memory.
    """

    def __init__(self, skills_dir: str = "~/.jarvis/skills") -> None:
        self.skills_dir = Path(skills_dir).expanduser().resolve()
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # Registry: skill_id -> metadata dict
        self._registry: Dict[str, Dict[str, Any]] = {}

        # Loaded modules: skill_id -> module object
        self._loaded: Dict[str, ModuleType] = {}

        # Vector memory for semantic search
        self._vector_memory = _SimpleVectorStore()

        # Registry persistence file
        self._registry_file = self.skills_dir / ".registry.json"

        self._load_registry()
        self._load_all_skills_from_disk()

    # -- Internal helpers -----------------------------------------------------

    def _load_registry(self) -> None:
        if self._registry_file.exists():
            try:
                data = json.loads(self._registry_file.read_text(encoding="utf-8"))
                self._registry.update(data)
            except (json.JSONDecodeError, OSError):
                self._registry = {}

    def _save_registry(self) -> None:
        try:
            self._registry_file.write_text(
                json.dumps(self._registry, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _load_all_skills_from_disk(self) -> None:
        """Scan skills_dir and auto-register any .py files not in registry."""
        for py_file in sorted(self.skills_dir.glob("*.py")):
            # Skip hidden / private files
            if py_file.name.startswith("_"):
                continue
            skill_id = py_file.stem
            if skill_id not in self._registry:
                code = py_file.read_text(encoding="utf-8")
                valid, err = self.validate_skill_code(code)
                if valid:
                    self._registry[skill_id] = {
                        "name": skill_id,
                        "description": f"Auto-loaded skill from {py_file.name}",
                        "tags": [],
                        "source": "local",
                        "created": time.time(),
                        "file": str(py_file),
                        "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16],
                    }
                    self._vector_memory.store(
                        skill_id,
                        f"{skill_id} {self._registry[skill_id]['description']}",
                        self._registry[skill_id],
                    )
        self._save_registry()

    def _skill_path(self, skill_id: str) -> Path:
        return self.skills_dir / f"{skill_id}.py"

    def _extract_callable(self, module: ModuleType) -> Optional[Callable]:
        """Find the primary callable in a module (function or class)."""
        candidates = [
            obj
            for name, obj in inspect.getmembers(module, inspect.isfunction)
            if obj.__module__ == module.__name__ and not name.startswith("_")
        ]
        if candidates:
            return candidates[0]
        classes = [
            obj
            for name, obj in inspect.getmembers(module, inspect.isclass)
            if obj.__module__ == module.__name__ and not name.startswith("_")
        ]
        if classes:
            return classes[0]
        return None

    # -- Public API -----------------------------------------------------------

    def validate_skill_code(self, code: str) -> Tuple[bool, str]:
        """Validate Python code using ast.parse()."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

    def register_skill(
        self,
        name: str,
        code: str,
        description: str,
        tags: Optional[List[str]] = None,
        source: str = "local",
    ) -> str:
        """
        Register a new skill:
            1. Validate code syntax
            2. Write to skills_dir/name.py
            3. Add to registry
            4. Store in vector memory
        Returns skill_id.
        """
        # 1. Validate
        valid, error = self.validate_skill_code(code)
        if not valid:
            raise ValueError(f"Skill code validation failed: {error}")

        skill_id = name
        file_path = self._skill_path(skill_id)

        # 2. Write to disk
        file_path.write_text(code, encoding="utf-8")

        # 3. Add to registry
        self._registry[skill_id] = {
            "name": name,
            "description": description,
            "tags": tags or [],
            "source": source,
            "created": time.time(),
            "file": str(file_path),
            "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16],
        }
        self._save_registry()

        # 4. Store in vector memory
        self._vector_memory.store(
            skill_id,
            f"{name} {description} {' '.join(tags or [])}",
            self._registry[skill_id],
        )

        return skill_id

    def load_skill(self, skill_id: str) -> Callable:
        """
        Load skill by ID.
        Returns a callable function or class.
        Handles import errors gracefully.
        """
        if skill_id in self._loaded:
            module = self._loaded[skill_id]
            call = self._extract_callable(module)
            if call:
                return call

        file_path = self._skill_path(skill_id)
        if not file_path.exists():
            # Fallback: maybe stored in registry but file moved
            reg = self._registry.get(skill_id, {})
            alt = Path(reg.get("file", ""))
            if alt.exists():
                file_path = alt
            else:
                raise FileNotFoundError(f"Skill file not found for '{skill_id}'")

        try:
            spec = importlib.util.spec_from_file_location(skill_id, str(file_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create module spec for '{skill_id}'")
            module = importlib.util.module_from_spec(spec)
            # Ensure unique module name in sys.modules to avoid collisions
            sys.modules[skill_id] = module
            spec.loader.exec_module(module)
            self._loaded[skill_id] = module

            call = self._extract_callable(module)
            if call is None:
                raise ImportError(f"No public callable found in skill '{skill_id}'")
            return call
        except Exception as e:
            # Clean up partial load
            self._loaded.pop(skill_id, None)
            sys.modules.pop(skill_id, None)
            raise ImportError(f"Failed to load skill '{skill_id}': {e}")

    def unload_skill(self, skill_id: str) -> bool:
        """
        Unload skill from runtime.
        Does NOT delete from disk.
        """
        if skill_id in self._loaded:
            self._loaded.pop(skill_id, None)
            sys.modules.pop(skill_id, None)
            return True
        return False

    def hot_swap(self, skill_id: str, new_code: str) -> bool:
        """
        Hot-swap skill with new code.
        Validates new code before swapping.
        Updates registry and disk.
        """
        # Validate
        valid, error = self.validate_skill_code(new_code)
        if not valid:
            return False

        file_path = self._skill_path(skill_id)
        if not file_path.exists() and skill_id in self._registry:
            alt = Path(self._registry[skill_id].get("file", ""))
            if alt.exists():
                file_path = alt

        try:
            file_path.write_text(new_code, encoding="utf-8")
        except OSError:
            return False

        # Update registry
        info = self._registry.get(skill_id, {})
        info["code_hash"] = hashlib.sha256(new_code.encode()).hexdigest()[:16]
        info["updated"] = time.time()
        self._registry[skill_id] = info
        self._save_registry()

        # Unload from runtime so next load picks up new code
        self.unload_skill(skill_id)

        # Refresh vector memory
        self._vector_memory.store(
            skill_id,
            f"{info.get('name', skill_id)} {info.get('description', '')} {' '.join(info.get('tags', []))}",
            info,
        )

        return True

    def list_skills(self, tag_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all registered skills.
        Optional filter by tag.
        """
        results = []
        for skill_id, meta in self._registry.items():
            if tag_filter:
                tags = meta.get("tags", [])
                if isinstance(tags, list) and tag_filter.lower() not in [t.lower() for t in tags]:
                    continue
            entry = {"skill_id": skill_id, **meta}
            results.append(entry)
        return results

    def find_skill(self, query: str) -> List[Dict[str, Any]]:
        """
        Find skills matching query.
        Uses semantic search via vector memory if available,
        falls back to simple substring search.
        """
        # Try vector search first
        top = self._vector_memory.search(query, top_k=10)
        if top and top[0][1] > 0.0:
            results = []
            for sid, score in top:
                meta = self._registry.get(sid, {})
                entry = {"skill_id": sid, "score": round(score, 4), **meta}
                results.append(entry)
            return results

        # Fallback: substring search across name / description / tags
        q = query.lower()
        results = []
        for skill_id, meta in self._registry.items():
            haystack = f"{meta.get('name', '')} {meta.get('description', '')} {' '.join(meta.get('tags', []))}".lower()
            if q in haystack:
                results.append({"skill_id": skill_id, **meta})
        return results

    def execute_skill(
        self,
        skill_id: str,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Execute skill with given arguments.
        Returns result.
        Catches exceptions and returns error dict.
        """
        kwargs = kwargs or {}
        try:
            call = self.load_skill(skill_id)
            if call is None:
                return {"error": f"Skill '{skill_id}' has no callable entrypoint."}
            result = call(*args, **kwargs)
            return result
        except Exception as e:
            return {
                "error": str(e),
                "skill_id": skill_id,
                "exception_type": type(e).__name__,
            }

    def import_from_github(self, repo_url: str, file_path: Optional[str] = None) -> str:
        """
        Import skill from GitHub repo.
        Clone, extract, validate, register.
        Returns skill_id.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis_skill_"))
        try:
            # Clone repo
            clone_cmd = ["git", "clone", "--depth", "1", repo_url, str(tmp_dir)]
            proc = subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Git clone failed: {proc.stderr}")

            # Determine file to import
            target: Optional[Path] = None
            if file_path:
                target = tmp_dir / file_path
            else:
                # Auto-find first .py file in repo root (non-hidden)
                py_files = [f for f in tmp_dir.glob("*.py") if not f.name.startswith("_")]
                if py_files:
                    target = py_files[0]

            if target is None or not target.exists():
                raise FileNotFoundError(f"No Python skill file found in cloned repo.")

            code = target.read_text(encoding="utf-8")
            valid, error = self.validate_skill_code(code)
            if not valid:
                raise ValueError(f"Cloned skill code invalid: {error}")

            # Derive skill name from filename
            skill_id = target.stem
            # If collision, append hash
            if skill_id in self._registry:
                h = hashlib.md5(code.encode()).hexdigest()[:6]
                skill_id = f"{skill_id}_{h}"

            description = f"Imported from {repo_url}"
            if file_path:
                description += f" (path: {file_path})"

            return self.register_skill(
                name=skill_id,
                code=code,
                description=description,
                tags=["github"],
                source=repo_url,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def get_skill_info(self, skill_id: str) -> Dict[str, Any]:
        """Return skill metadata."""
        meta = self._registry.get(skill_id, {})
        return {"skill_id": skill_id, **meta}


# --------------------------------------------------------------------------- #
# MockSkillEngine
# --------------------------------------------------------------------------- #

class MockSkillEngine:
    """
    Same interface as LocalSkillEngine, but stores skills in memory.
    execute_skill runs in a restricted environment.
    """

    def __init__(self, skills_dir: str = "~/.jarvis/skills") -> None:
        # skills_dir ignored; purely in-memory
        self._skills: Dict[str, Dict[str, Any]] = {}  # skill_id -> {code, meta}
        self._loaded: Dict[str, Callable] = {}
        self._vector_memory = _SimpleVectorStore()

    def validate_skill_code(self, code: str) -> Tuple[bool, str]:
        """Validate Python code using ast.parse()."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

    def register_skill(
        self,
        name: str,
        code: str,
        description: str,
        tags: Optional[List[str]] = None,
        source: str = "local",
    ) -> str:
        valid, error = self.validate_skill_code(code)
        if not valid:
            raise ValueError(f"Skill code validation failed: {error}")

        skill_id = name
        self._skills[skill_id] = {
            "code": code,
            "meta": {
                "name": name,
                "description": description,
                "tags": tags or [],
                "source": source,
                "created": time.time(),
                "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16],
            },
        }
        self._vector_memory.store(
            skill_id,
            f"{name} {description} {' '.join(tags or [])}",
            self._skills[skill_id]["meta"],
        )
        return skill_id

    def load_skill(self, skill_id: str) -> Callable:
        if skill_id in self._loaded:
            return self._loaded[skill_id]

        skill = self._skills.get(skill_id)
        if skill is None:
            raise FileNotFoundError(f"Skill '{skill_id}' not found.")

        # Create a transient module in restricted namespace
        code = skill["code"]
        namespace: Dict[str, Any] = {
            "__name__": skill_id,
            "__builtins__": {
                "abs": abs,
                "all": all,
                "any": any,
                "bool": bool,
                "dict": dict,
                "enumerate": enumerate,
                "filter": filter,
                "float": float,
                "int": int,
                "len": len,
                "list": list,
                "map": map,
                "max": max,
                "min": min,
                "pow": pow,
                "print": print,
                "range": range,
                "round": round,
                "set": set,
                "sorted": sorted,
                "str": str,
                "sum": sum,
                "tuple": tuple,
                "zip": zip,
                "Exception": Exception,
                "TypeError": TypeError,
                "ValueError": ValueError,
                "RuntimeError": RuntimeError,
                "NameError": NameError,
                "KeyError": KeyError,
                "IndexError": IndexError,
                "AttributeError": AttributeError,
                "StopIteration": StopIteration,
                "OSError": OSError,
                "ZeroDivisionError": ZeroDivisionError,
            },
        }
        exec(compile(code, f"<skill:{skill_id}>", "exec"), namespace)

        # Extract callable
        candidates = [v for k, v in namespace.items() if callable(v) and not k.startswith("_") and k not in ("__builtins__",)]
        if not candidates:
            raise ImportError(f"No public callable found in skill '{skill_id}'")
        self._loaded[skill_id] = candidates[0]
        return candidates[0]

    def unload_skill(self, skill_id: str) -> bool:
        if skill_id in self._loaded:
            self._loaded.pop(skill_id, None)
            return True
        return False

    def hot_swap(self, skill_id: str, new_code: str) -> bool:
        valid, error = self.validate_skill_code(new_code)
        if not valid:
            return False

        skill = self._skills.get(skill_id)
        if skill is None:
            return False

        skill["code"] = new_code
        skill["meta"]["code_hash"] = hashlib.sha256(new_code.encode()).hexdigest()[:16]
        skill["meta"]["updated"] = time.time()
        self.unload_skill(skill_id)
        self._vector_memory.delete(skill_id)
        self._vector_memory.store(
            skill_id,
            f"{skill['meta'].get('name', skill_id)} {skill['meta'].get('description', '')} {' '.join(skill['meta'].get('tags', []))}",
            skill["meta"],
        )
        return True

    def list_skills(self, tag_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        for skill_id, data in self._skills.items():
            meta = data["meta"]
            if tag_filter:
                tags = meta.get("tags", [])
                if isinstance(tags, list) and tag_filter.lower() not in [t.lower() for t in tags]:
                    continue
            results.append({"skill_id": skill_id, **meta})
        return results

    def find_skill(self, query: str) -> List[Dict[str, Any]]:
        top = self._vector_memory.search(query, top_k=10)
        if top and top[0][1] > 0.0:
            results = []
            for sid, score in top:
                meta = self._skills.get(sid, {}).get("meta", {})
                results.append({"skill_id": sid, "score": round(score, 4), **meta})
            return results

        q = query.lower()
        results = []
        for skill_id, data in self._skills.items():
            meta = data["meta"]
            haystack = f"{meta.get('name', '')} {meta.get('description', '')} {' '.join(meta.get('tags', []))}".lower()
            if q in haystack:
                results.append({"skill_id": skill_id, **meta})
        return results

    def execute_skill(
        self,
        skill_id: str,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        kwargs = kwargs or {}
        try:
            call = self.load_skill(skill_id)
            if call is None:
                return {"error": f"Skill '{skill_id}' has no callable entrypoint."}
            return call(*args, **kwargs)
        except Exception as e:
            return {
                "error": str(e),
                "skill_id": skill_id,
                "exception_type": type(e).__name__,
            }

    def import_from_github(self, repo_url: str, file_path: Optional[str] = None) -> str:
        """Mock: does not support real GitHub import (no filesystem). Raises NotImplementedError."""
        raise NotImplementedError("MockSkillEngine does not support GitHub import. Use LocalSkillEngine.")

    def get_skill_info(self, skill_id: str) -> Dict[str, Any]:
        meta = self._skills.get(skill_id, {}).get("meta", {})
        return {"skill_id": skill_id, **meta}


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def get_skill_engine(skills_dir: str = "~/.jarvis/skills") -> LocalSkillEngine:
    """Factory that returns a LocalSkillEngine instance."""
    return LocalSkillEngine(skills_dir=skills_dir)
