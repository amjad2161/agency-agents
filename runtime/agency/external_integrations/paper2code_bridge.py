#!/usr/bin/env python3
"""
paper2code_bridge.py
Integration adapter for the paper2code external repository.

 paper2code (https://github.com/PrathamLearnsToCode/paper2code) is an
 LLM-agent skill that converts arXiv papers into citation-anchored,
 ambiguity-audited Python implementations.

 This bridge provides a typed Python API over the repo's helper scripts
 and markdown protocols so that an agency runtime can:
   1. Fetch and parse arXiv papers (PDF + HTML fallback)
   2. Extract structure (sections, algorithms, equations, tables, footnotes)
   3. Discover official code repositories
   4. Load pipeline prompts / guardrails / scaffolds for LLM consumption
   5. Read worked examples as few-shot exemplars

 Usage:
     from paper2code_bridge import Paper2CodeBridge

     bridge = Paper2CodeBridge()
     result = bridge.fetch_and_extract("1706.03762")
     print(result.metadata.title)
     print(result.sections[0].title)

 Dependencies (managed externally):
     pip install pymupdf4llm pdfplumber requests pyyaml
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_REPO_PATH = Path("/mnt/agents/output/jarvis/external_repos/paper2code")

SCRIPT_FETCH = "skills/paper2code/scripts/fetch_paper.py"
SCRIPT_EXTRACT = "skills/paper2code/scripts/extract_structure.py"

PIPELINE_DIR = "skills/paper2code/pipeline"
GUARDRAILS_DIR = "skills/paper2code/guardrails"
KNOWLEDGE_DIR = "skills/paper2code/knowledge"
SCAFFOLDS_DIR = "skills/paper2code/scaffolds"
WORKED_DIR = "skills/paper2code/worked"

REQUIRED_DEPS = ["pymupdf4llm", "pdfplumber", "requests", "yaml"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PaperMetadata:
    """Parsed paper_metadata.json from fetch_paper.py."""
    arxiv_id: str
    title: str
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    categories: List[str] = field(default_factory=list)
    official_code: List[Dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PaperMetadata:
        return cls(
            arxiv_id=data.get("arxiv_id", ""),
            title=data.get("title", "Unknown"),
            authors=data.get("authors", []),
            abstract=data.get("abstract", ""),
            categories=data.get("categories", []),
            official_code=data.get("official_code", []),
        )


@dataclass
class Section:
    title: str
    content: str
    source_file: Optional[str] = None


@dataclass
class Algorithm:
    title: str
    content: str
    source_file: Optional[str] = None


@dataclass
class Equation:
    number: int
    content: str
    raw: str
    source_file: Optional[str] = None


@dataclass
class Table:
    caption: str
    content: str
    source_file: Optional[str] = None


@dataclass
class Footnote:
    index: int
    content: str


@dataclass
class ExtractionResult:
    """Output of Stage 1 (Paper Acquisition) + structure extraction."""
    arxiv_id: str
    paper_slug: str
    metadata: PaperMetadata
    full_text_path: Path
    sections: List[Section] = field(default_factory=list)
    algorithms: List[Algorithm] = field(default_factory=list)
    equations: List[Equation] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    footnotes: List[Footnote] = field(default_factory=list)
    work_dir: Path = field(default_factory=Path)
    pdf_path: Optional[Path] = None


@dataclass
class ScaffoldTemplate:
    name: str
    path: Path
    content: str


@dataclass
class WorkedExample:
    paper_slug: str
    path: Path
    review_md: str
    src_files: Dict[str, Path] = field(default_factory=dict)
    config_path: Optional[Path] = None
    notebook_path: Optional[Path] = None
    readme_path: Optional[Path] = None
    reproduction_notes_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class Paper2CodeError(Exception):
    """Base exception for bridge errors."""
    pass

class DependencyError(Paper2CodeError):
    pass

class FetchError(Paper2CodeError):
    pass

class ExtractionError(Paper2CodeError):
    pass

class RepoNotFoundError(Paper2CodeError):
    pass


# ---------------------------------------------------------------------------
# Bridge class
# ---------------------------------------------------------------------------

class Paper2CodeBridge:
    """
    Programmatic interface to the paper2code skill.

    All filesystem paths are resolved relative to ``repo_path``.
    The bridge can run the fetch+extract pipeline via subprocess or
    load markdown protocols as LLM prompts.
    """

    def __init__(self, repo_path: Path | str = DEFAULT_REPO_PATH) -> None:
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise RepoNotFoundError(
                f"paper2code repo not found at {self.repo_path}. "
                "Clone it first: git clone https://github.com/PrathamLearnsToCode/paper2code.git"
            )

        self.scripts_dir = self.repo_path / "skills" / "paper2code" / "scripts"
        self.pipeline_dir = self.repo_path / PIPELINE_DIR
        self.guardrails_dir = self.repo_path / GUARDRAILS_DIR
        self.knowledge_dir = self.repo_path / KNOWLEDGE_DIR
        self.scaffolds_dir = self.repo_path / SCAFFOLDS_DIR
        self.worked_dir = self.repo_path / WORKED_DIR

    # ------------------------------------------------------------------
    # Health / dependency checks
    # ------------------------------------------------------------------

    def check_dependencies(self) -> Tuple[bool, List[str]]:
        """
        Check whether the Python packages required by paper2code scripts
        are importable in the current environment.

        Returns:
            (all_ok, missing_packages)
        """
        missing: List[str] = []
        for dep in REQUIRED_DEPS:
            try:
                __import__(dep)
            except ImportError:
                missing.append(dep)
        return (len(missing) == 0, missing)

    def ensure_dependencies(self) -> None:
        """Raise DependencyError if required packages are missing."""
        ok, missing = self.check_dependencies()
        if not ok:
            raise DependencyError(
                f"Missing dependencies: {missing}. Install with:\n"
                f"  pip install {' '.join(missing)}"
            )

    # ------------------------------------------------------------------
    # Low-level: run scripts
    # ------------------------------------------------------------------

    def _run_script(self, script_relative: str, *args: str, cwd: Optional[Path] = None) -> str:
        """Run a script inside the repo via the current Python interpreter."""
        script_path = self.repo_path / script_relative
        if not script_path.exists():
            raise Paper2CodeError(f"Script not found: {script_path}")

        cmd = [sys.executable, str(script_path), *args]
        working_dir = cwd or self.repo_path
        try:
            result = subprocess.run(
                cmd,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            raise FetchError(f"Script timed out after 180s: {' '.join(cmd)}") from exc

        if result.returncode != 0:
            # Some scripts write warnings to stderr but succeed; treat non-zero as error.
            raise Paper2CodeError(
                f"Script failed (exit {result.returncode}): {' '.join(cmd)}\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result.stdout

    # ------------------------------------------------------------------
    # Stage 1: Paper Acquisition
    # ------------------------------------------------------------------

    def fetch_paper(self, arxiv_id_or_url: str, output_dir: Path) -> PaperMetadata:
        """
        Run ``fetch_paper.py`` to download the paper and extract metadata.

        Args:
            arxiv_id_or_url: Bare ID (e.g. ``1706.03762``) or full arXiv URL.
            output_dir: Directory where ``paper_text.md`` and
                ``paper_metadata.json`` will be written.

        Returns:
            ``PaperMetadata`` loaded from the generated JSON file.
        """
        self.ensure_dependencies()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._run_script(str(self.repo_path / SCRIPT_FETCH), arxiv_id_or_url, str(output_dir))

        meta_path = output_dir / "paper_metadata.json"
        if not meta_path.exists():
            raise FetchError(f"Metadata file not generated: {meta_path}")

        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PaperMetadata.from_dict(data)

    def extract_structure(self, paper_text_md: Path, output_dir: Path) -> None:
        """
        Run ``extract_structure.py`` to split a parsed paper into
        sections, algorithms, equations, tables, and footnotes.

        Args:
            paper_text_md: Path to the markdown file produced by ``fetch_paper``.
            output_dir: Directory where sub-artifacts will be written.
        """
        self.ensure_dependencies()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._run_script(
            str(self.repo_path / SCRIPT_EXTRACT),
            str(paper_text_md),
            str(output_dir),
        )

    def fetch_and_extract(
        self,
        arxiv_id_or_url: str,
        work_dir: Optional[Path] = None,
        cleanup: bool = False,
    ) -> ExtractionResult:
        """
        End-to-end Stage 1: fetch paper + extract structure.

        Args:
            arxiv_id_or_url: arXiv ID or URL.
            work_dir: Working directory for intermediate artifacts.
                Defaults to ``.paper2code_work/{arxiv_id}/`` under CWD.
            cleanup: If True, remove ``work_dir`` after extraction (not recommended
                if you plan to run downstream stages).

        Returns:
            ``ExtractionResult`` with all loaded sub-artifacts.
        """
        self.ensure_dependencies()

        # Normalize ID for directory naming (strip URL, keep ID)
        raw_id = arxiv_id_or_url.strip().rstrip("/")
        for prefix in [
            "https://arxiv.org/abs/",
            "http://arxiv.org/abs/",
            "https://arxiv.org/pdf/",
            "http://arxiv.org/pdf/",
        ]:
            if raw_id.startswith(prefix):
                raw_id = raw_id[len(prefix):]
                break
        if raw_id.endswith(".pdf"):
            raw_id = raw_id[:-4]

        if work_dir is None:
            work_dir = Path(f".paper2code_work/{raw_id}")
        work_dir = Path(work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

        # 1. Fetch
        metadata = self.fetch_paper(arxiv_id_or_url, work_dir)
        paper_slug = self._slugify(metadata.title)

        # 2. Extract structure
        paper_text_md = work_dir / "paper_text.md"
        self.extract_structure(paper_text_md, work_dir)

        # 3. Load sub-artifacts
        sections = self._load_sections(work_dir / "sections")
        algorithms = self._load_algorithms(work_dir / "algorithms")
        equations = self._load_equations(work_dir / "equations")
        tables = self._load_tables(work_dir / "tables")
        footnotes = self._load_footnotes(work_dir / "footnotes.md")

        pdf_path = work_dir / "paper.pdf"
        if not pdf_path.exists():
            pdf_path = None

        result = ExtractionResult(
            arxiv_id=metadata.arxiv_id,
            paper_slug=paper_slug,
            metadata=metadata,
            full_text_path=paper_text_md,
            sections=sections,
            algorithms=algorithms,
            equations=equations,
            tables=tables,
            footnotes=footnotes,
            work_dir=work_dir,
            pdf_path=pdf_path,
        )

        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)

        return result

    # ------------------------------------------------------------------
    # Artifact loaders
    # ------------------------------------------------------------------

    @staticmethod
    def _load_sections(sections_dir: Path) -> List[Section]:
        sections: List[Section] = []
        if not sections_dir.exists():
            return sections
        for fpath in sorted(sections_dir.glob("*.md")):
            content = fpath.read_text(encoding="utf-8")
            # First line is usually a markdown heading
            title = fpath.stem
            first_line = content.splitlines()[0] if content else ""
            if first_line.startswith("# "):
                title = first_line[2:].strip()
            sections.append(Section(title=title, content=content, source_file=str(fpath)))
        return sections

    @staticmethod
    def _load_algorithms(algorithms_dir: Path) -> List[Algorithm]:
        algorithms: List[Algorithm] = []
        if not algorithms_dir.exists():
            return algorithms
        for fpath in sorted(algorithms_dir.glob("*.md")):
            content = fpath.read_text(encoding="utf-8")
            title = fpath.stem
            first_line = content.splitlines()[0] if content else ""
            if first_line.startswith("# "):
                title = first_line[2:].strip()
            algorithms.append(Algorithm(title=title, content=content, source_file=str(fpath)))
        return algorithms

    @staticmethod
    def _load_equations(equations_dir: Path) -> List[Equation]:
        equations: List[Equation] = []
        if not equations_dir.exists():
            return equations
        for fpath in sorted(equations_dir.glob("*.md")):
            content = fpath.read_text(encoding="utf-8")
            # Try to infer number from filename like "05_some_name.md" or content heading
            number = 0
            m = re.match(r"^(\d+)_", fpath.stem)
            if m:
                number = int(m.group(1))
            first_line = content.splitlines()[0] if content else ""
            raw = content
            # Strip heading line for content
            body_lines = content.splitlines()[1:] if first_line.startswith("# ") else content.splitlines()
            body = "\n".join(body_lines).strip()
            equations.append(Equation(number=number, content=body, raw=raw, source_file=str(fpath)))
        return equations

    @staticmethod
    def _load_tables(tables_dir: Path) -> List[Table]:
        tables: List[Table] = []
        if not tables_dir.exists():
            return tables
        for fpath in sorted(tables_dir.glob("*.md")):
            content = fpath.read_text(encoding="utf-8")
            caption = fpath.stem
            first_line = content.splitlines()[0] if content else ""
            if first_line.startswith("# "):
                caption = first_line[2:].strip()
            tables.append(Table(caption=caption, content=content, source_file=str(fpath)))
        return tables

    @staticmethod
    def _load_footnotes(footnotes_path: Path) -> List[Footnote]:
        footnotes: List[Footnote] = []
        if not footnotes_path.exists():
            return footnotes
        content = footnotes_path.read_text(encoding="utf-8")
        # Parse the format written by extract_structure.py:
        # ## Footnote 1
        # ...content...
        # ---
        matches = re.findall(
            r"## Footnote (\d+)\n\n(.*?)(?=\n\n---|\Z)", content, re.DOTALL
        )
        for idx_str, body in matches:
            footnotes.append(Footnote(index=int(idx_str), content=body.strip()))
        return footnotes

    # ------------------------------------------------------------------
    # Prompt / protocol loaders
    # ------------------------------------------------------------------

    def load_pipeline_protocol(self, stage: int | str) -> str:
        """
        Load a pipeline reasoning protocol as a prompt string.

        Args:
            stage: Stage number (1-5) or filename stem (e.g. ``"01_paper_acquisition"``).

        Returns:
            Full markdown content of the protocol.
        """
        if isinstance(stage, int):
            fname = f"{stage:02d}_*.md"
            matches = list(self.pipeline_dir.glob(fname))
            if not matches:
                raise Paper2CodeError(f"Pipeline stage {stage} not found in {self.pipeline_dir}")
            path = matches[0]
        else:
            path = self.pipeline_dir / f"{stage}.md"
        if not path.exists():
            raise Paper2CodeError(f"Pipeline protocol not found: {path}")
        return path.read_text(encoding="utf-8")

    def load_all_pipeline_protocols(self) -> Dict[str, str]:
        """Load all 5 pipeline protocols keyed by filename stem."""
        protocols: Dict[str, str] = {}
        for path in sorted(self.pipeline_dir.glob("*.md")):
            protocols[path.stem] = path.read_text(encoding="utf-8")
        return protocols

    def load_guardrail(self, name: str) -> str:
        """
        Load a guardrail markdown file.

        Args:
            name: Stem, e.g. ``"hallucination_prevention"``, ``"scope_enforcement"``.
        """
        path = self.guardrails_dir / f"{name}.md"
        if not path.exists():
            raise Paper2CodeError(f"Guardrail not found: {path}")
        return path.read_text(encoding="utf-8")

    def load_all_guardrails(self) -> Dict[str, str]:
        """Load all guardrails keyed by stem."""
        guardrails: Dict[str, str] = {}
        for path in sorted(self.guardrails_dir.glob("*.md")):
            guardrails[path.stem] = path.read_text(encoding="utf-8")
        return guardrails

    def load_knowledge(self, name: str) -> str:
        """Load a knowledge file, e.g. ``"loss_functions"``."""
        path = self.knowledge_dir / f"{name}.md"
        if not path.exists():
            raise Paper2CodeError(f"Knowledge file not found: {path}")
        return path.read_text(encoding="utf-8")

    def load_all_knowledge(self) -> Dict[str, str]:
        """Load all knowledge files keyed by stem."""
        knowledge: Dict[str, str] = {}
        for path in sorted(self.knowledge_dir.glob("*.md")):
            knowledge[path.stem] = path.read_text(encoding="utf-8")
        return knowledge

    # ------------------------------------------------------------------
    # Scaffold helpers
    # ------------------------------------------------------------------

    def load_scaffold(self, name: str) -> ScaffoldTemplate:
        """
        Load a scaffold template.

        Args:
            name: e.g. ``"model"``, ``"train"``, ``"config"`` (the ``_template.{py,yaml,md}``
            suffix is added automatically).
        """
        # Try common extensions
        for ext in (".py", ".yaml", ".md"):
            path = self.scaffolds_dir / f"{name}_template{ext}"
            if path.exists():
                return ScaffoldTemplate(
                    name=name,
                    path=path,
                    content=path.read_text(encoding="utf-8"),
                )
        raise Paper2CodeError(
            f"Scaffold template '{name}' not found in {self.scaffolds_dir}"
        )

    def list_scaffolds(self) -> List[str]:
        """Return available scaffold names (stems without ``_template`` suffix)."""
        names: set = set()
        for path in self.scaffolds_dir.glob("*_template.*"):
            stem = path.stem.replace("_template", "")
            names.add(stem)
        return sorted(names)

    def load_all_scaffolds(self) -> Dict[str, ScaffoldTemplate]:
        """Load every scaffold template keyed by name."""
        scaffolds: Dict[str, ScaffoldTemplate] = {}
        for name in self.list_scaffolds():
            scaffolds[name] = self.load_scaffold(name)
        return scaffolds

    # ------------------------------------------------------------------
    # Worked examples
    # ------------------------------------------------------------------

    def list_worked_examples(self) -> List[str]:
        """Return slugs of available worked examples (e.g. ``"attention_is_all_you_need"``)."""
        if not self.worked_dir.exists():
            return []
        return sorted([d.name for d in self.worked_dir.iterdir() if d.is_dir()])

    def load_worked_example(self, slug: str) -> WorkedExample:
        """
        Load a worked example directory.

        Args:
            slug: Directory name under ``worked/``.
        """
        ex_dir = self.worked_dir / slug
        if not ex_dir.exists():
            raise Paper2CodeError(f"Worked example '{slug}' not found at {ex_dir}")

        src_dir = ex_dir / "src"
        src_files = {}
        if src_dir.exists():
            src_files = {p.stem: p for p in src_dir.glob("*.py")}

        review_path = ex_dir / "review.md"
        review_md = review_path.read_text(encoding="utf-8") if review_path.exists() else ""

        return WorkedExample(
            paper_slug=slug,
            path=ex_dir,
            review_md=review_md,
            src_files=src_files,
            config_path=next((ex_dir / "configs").glob("*.yaml"), None) if (ex_dir / "configs").exists() else None,
            notebook_path=ex_dir / "notebooks" / "walkthrough.ipynb" if (ex_dir / "notebooks").exists() else None,
            readme_path=ex_dir / "README.md" if (ex_dir / "README.md").exists() else None,
            reproduction_notes_path=ex_dir / "REPRODUCTION_NOTES.md" if (ex_dir / "REPRODUCTION_NOTES.md").exists() else None,
        )

    def load_all_worked_examples(self) -> Dict[str, WorkedExample]:
        """Load every worked example keyed by slug."""
        examples: Dict[str, WorkedExample] = {}
        for slug in self.list_worked_examples():
            examples[slug] = self.load_worked_example(slug)
        return examples

    # ------------------------------------------------------------------
    # Convenience: prompt assembly
    # ------------------------------------------------------------------

    def build_system_prompt(self, stage: int = 4) -> str:
        """
        Assemble a composite system prompt for an LLM agent executing a given stage.

        Includes:
          - SKILL.md orchestration instructions
          - The requested pipeline protocol
          - All guardrails (hallucination prevention + scope enforcement)
          - All knowledge files

        Args:
            stage: Pipeline stage number (default 4, Code Generation).

        Returns:
            A large markdown string suitable for a system prompt.
        """
        parts: List[str] = []

        skill_path = self.repo_path / "skills" / "paper2code" / "SKILL.md"
        if skill_path.exists():
            parts.append("# SKILL ORCHESTRATION\n\n" + skill_path.read_text(encoding="utf-8"))

        try:
            protocol = self.load_pipeline_protocol(stage)
            parts.append(f"\n# STAGE {stage} PROTOCOL\n\n{protocol}")
        except Paper2CodeError:
            pass

        for name, text in self.load_all_guardrails().items():
            parts.append(f"\n# GUARDRAIL: {name}\n\n{text}")

        for name, text in self.load_all_knowledge().items():
            parts.append(f"\n# KNOWLEDGE: {name}\n\n{text}")

        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(title: str) -> str:
        """Convert paper title to a filesystem-safe slug matching paper2code convention."""
        slug = title.lower()
        # Remove common LaTeX / punctuation noise
        slug = re.sub(r"[{}\\$]", "", slug)
        slug = re.sub(r"[^a-z0-9\s]+", "", slug)
        slug = re.sub(r"\s+", "_", slug).strip("_")
        return slug

    def get_repo_info(self) -> Dict[str, Any]:
        """Return summary metadata about the cloned repo."""
        info: Dict[str, Any] = {
            "repo_path": str(self.repo_path),
            "exists": self.repo_path.exists(),
            "pipeline_stages": sorted(self.pipeline_dir.glob("*.md")) if self.pipeline_dir.exists() else [],
            "guardrails": sorted(self.guardrails_dir.glob("*.md")) if self.guardrails_dir.exists() else [],
            "scaffolds": self.list_scaffolds(),
            "worked_examples": self.list_worked_examples(),
            "dependencies_ok": self.check_dependencies()[0],
        }
        return info


# ---------------------------------------------------------------------------
# CLI smoke-test (optional)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="paper2code bridge smoke test")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_PATH)
    parser.add_argument("--fetch", type=str, default=None, help="arxiv ID to fetch")
    parser.add_argument("--out", type=Path, default=Path(".paper2code_work"))
    args = parser.parse_args()

    bridge = Paper2CodeBridge(repo_path=args.repo)
    print("Repo info:", json.dumps(bridge.get_repo_info(), indent=2))

    ok, missing = bridge.check_dependencies()
    if not ok:
        print(f"Missing deps: {missing}")
        sys.exit(1)

    if args.fetch:
        print(f"\nFetching {args.fetch} ...")
        result = bridge.fetch_and_extract(args.fetch, work_dir=args.out / args.fetch.replace("/", "_"))
        print(f"Title: {result.metadata.title}")
        print(f"Authors: {', '.join(result.metadata.authors[:3])}")
        print(f"Sections: {len(result.sections)}")
        print(f"Algorithms: {len(result.algorithms)}")
        print(f"Equations: {len(result.equations)}")
        print(f"Tables: {len(result.tables)}")
        print(f"Footnotes: {len(result.footnotes)}")
        print(f"Official code links: {len(result.metadata.official_code)}")
        for link in result.metadata.official_code:
            print(f"  - {link['url']} (source: {link['source']})")
