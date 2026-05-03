# humanizer_bridge.py
# Integration adapter for blader/humanizer (https://github.com/blader/humanizer)
#
# Purpose:
#   Wraps the prompt-based "humanizer" Claude Code skill so it can be consumed
#   programmatically by the Jarvis runtime agency. Provides:
#     1. Local heuristic pattern detection (keyword/regex linting)
#     2. LLM prompt assembly (system skill + user text + optional voice sample)
#     3. Optional two-pass audit driver if an LLM client is supplied
#
# Usage:
#   from humanizer_bridge import HumanizerBridge
#   bridge = HumanizerBridge(skill_path="/path/to/SKILL.md")
#   flags = bridge.detect("Your text here")
#   messages = bridge.build_messages("Your text here", voice_sample="My writing...")
#
# License: MIT (matches upstream)

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Flag:
    """A single heuristic match for an AI-writing pattern."""
    pattern_id: int
    pattern_name: str
    category: str
    matched_text: str
    line_number: int
    column: int
    severity: str = "warning"  # "warning" | "critical"
    suggestion: str = ""


@dataclass
class HumanizeResult:
    """Result of a humanization operation."""
    draft: str = ""
    audit_notes: str = ""
    final: str = ""
    flags: List[Flag] = field(default_factory=list)
    changes_summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pattern database extracted from SKILL.md (v2.5.1)
# ---------------------------------------------------------------------------

PATTERN_DB: List[Dict[str, Any]] = [
    # Content Patterns
    {
        "id": 1,
        "name": "Significance inflation",
        "category": "content",
        "keywords": [
            "stands as", "serves as", "is a testament", "is a reminder",
            "vital role", "significant role", "crucial role", "pivotal role",
            "key role", "pivotal moment", "key moment", "underscores",
            "highlights its importance", "highlights its significance",
            "reflects broader", "symbolizing its ongoing", "symbolizing its enduring",
            "symbolizing its lasting", "contributing to the", "setting the stage for",
            "marking the", "shaping the", "represents a shift", "marks a shift",
            "key turning point", "evolving landscape", "focal point",
            "indelible mark", "deeply rooted",
        ],
        "severity": "warning",
    },
    {
        "id": 2,
        "name": "Notability name-dropping",
        "category": "content",
        "keywords": [
            "independent coverage", "local media outlets", "regional media outlets",
            "national media outlets", "written by a leading expert",
            "active social media presence",
        ],
        "severity": "warning",
    },
    {
        "id": 3,
        "name": "Superficial -ing analyses",
        "category": "content",
        "keywords": [
            "highlighting", "underscoring", "emphasizing", "ensuring",
            "reflecting", "symbolizing", "contributing to", "cultivating",
            "fostering", "encompassing", "showcasing",
        ],
        "severity": "warning",
    },
    {
        "id": 4,
        "name": "Promotional and advertisement-like language",
        "category": "content",
        "keywords": [
            "boasts a", "vibrant", "rich cultural", "rich heritage",
            "profound", "enhancing its", "showcasing", "exemplifies",
            "commitment to", "natural beauty", "nestled", "in the heart of",
            "groundbreaking", "renowned", "breathtaking", "must-visit", "stunning",
        ],
        "severity": "warning",
    },
    {
        "id": 5,
        "name": "Vague attributions and weasel words",
        "category": "content",
        "keywords": [
            "Industry reports", "Observers have cited", "Experts argue",
            "Some critics argue", "several sources", "several publications",
        ],
        "severity": "critical",
    },
    {
        "id": 6,
        "name": "Outline-like Challenges and Future Prospects",
        "category": "content",
        "keywords": [
            "faces several challenges", "Despite these challenges",
            "Challenges and Legacy", "Future Outlook", "Despite its",
        ],
        "severity": "warning",
    },
    # Language & Grammar Patterns
    {
        "id": 7,
        "name": "Overused AI vocabulary words",
        "category": "language",
        "keywords": [
            "actually", "additionally", "align with", "crucial", "delve",
            "emphasizing", "enduring", "enhance", "fostering", "garner",
            "highlight", "interplay", "intricate", "intricacies", "key",
            "landscape", "pivotal", "showcase", "tapestry", "testament",
            "underscore", "valuable", "vibrant",
        ],
        "severity": "warning",
    },
    {
        "id": 8,
        "name": "Copula avoidance",
        "category": "language",
        "keywords": [
            "serves as", "stands as", "marks", "represents a",
            "boasts", "features", "offers",
        ],
        "severity": "warning",
    },
    {
        "id": 9,
        "name": "Negative parallelisms and tailing negations",
        "category": "language",
        "keywords": [
            "Not only", "but also", "It's not just about", "it's about",
            "no guessing", "no wasted motion", "no questions asked",
        ],
        "severity": "warning",
    },
    {
        "id": 10,
        "name": "Rule of three overuse",
        "category": "language",
        # Detected heuristically via comma-separated triplets rather than keywords
        "keywords": [],
        "severity": "warning",
    },
    {
        "id": 11,
        "name": "Elegant variation (synonym cycling)",
        "category": "language",
        "keywords": [],
        # Detected by tracking entity synonyms in proximity (heuristic)
        "severity": "warning",
    },
    {
        "id": 12,
        "name": "False ranges",
        "category": "language",
        "regex": re.compile(r"\bfrom\s+\S+\s+to\s+\S+(?:,\s*from\s+\S+\s+to\s+\S+)?", re.IGNORECASE),
        "severity": "warning",
    },
    {
        "id": 13,
        "name": "Passive voice and subjectless fragments",
        "category": "language",
        "keywords": [
            "No configuration file needed", "The results are preserved automatically",
            "is preserved automatically", "are preserved automatically",
        ],
        "regex": re.compile(r"\b(?:is|are|was|were)\s+\w+ed\s+automatically", re.IGNORECASE),
        "severity": "warning",
    },
    # Style Patterns
    {
        "id": 14,
        "name": "Em dash overuse",
        "category": "style",
        "regex": re.compile(r"—"),
        "severity": "warning",
    },
    {
        "id": 15,
        "name": "Overuse of boldface",
        "category": "style",
        "regex": re.compile(r"\*\*\w+.*?\*\*"),
        "severity": "info",
    },
    {
        "id": 16,
        "name": "Inline-header vertical lists",
        "category": "style",
        "regex": re.compile(r"^\s*[-*]\s+\*\*[^*]+\*\*\s*:", re.MULTILINE),
        "severity": "warning",
    },
    {
        "id": 17,
        "name": "Title case in headings",
        "category": "style",
        "regex": re.compile(r"^#{1,6}\s+[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+$", re.MULTILINE),
        "severity": "info",
    },
    {
        "id": 18,
        "name": "Emojis",
        "category": "style",
        "regex": re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            re.UNICODE,
        ),
        "severity": "warning",
    },
    {
        "id": 19,
        "name": "Curly quotation marks",
        "category": "style",
        "regex": re.compile(r"[\u201c\u201d\u2018\u2019]"),
        "severity": "info",
    },
    # Communication Patterns
    {
        "id": 20,
        "name": "Collaborative communication artifacts",
        "category": "communication",
        "keywords": [
            "I hope this helps", "Of course!", "Certainly!",
            "You're absolutely right!", "Would you like", "let me know",
            "here is a", "here is an",
        ],
        "severity": "critical",
    },
    {
        "id": 21,
        "name": "Knowledge-cutoff disclaimers",
        "category": "communication",
        "keywords": [
            "as of my last", "as of", "Up to my last training update",
            "While specific details are limited", "While specific details are scarce",
            "based on available information",
        ],
        "severity": "critical",
    },
    {
        "id": 22,
        "name": "Sycophantic / servile tone",
        "category": "communication",
        "keywords": [
            "Great question!", "You're absolutely right that",
            "That's an excellent point",
        ],
        "severity": "warning",
    },
    # Filler & Hedging
    {
        "id": 23,
        "name": "Filler phrases",
        "category": "filler",
        "keywords": [
            "In order to", "Due to the fact that", "At this point in time",
            "In the event that", "has the ability to", "It is important to note that",
        ],
        "severity": "warning",
    },
    {
        "id": 24,
        "name": "Excessive hedging",
        "category": "filler",
        "keywords": [
            "could potentially", "possibly be argued", "might have some",
        ],
        "severity": "warning",
    },
    {
        "id": 25,
        "name": "Generic positive conclusions",
        "category": "filler",
        "keywords": [
            "The future looks bright", "Exciting times lie ahead",
            "journey toward excellence", "step in the right direction",
        ],
        "severity": "warning",
    },
    {
        "id": 26,
        "name": "Hyphenated word-pair overuse",
        "category": "filler",
        "keywords": [
            "third-party", "cross-functional", "client-facing", "data-driven",
            "decision-making", "well-known", "high-quality", "real-time",
            "long-term", "end-to-end",
        ],
        "severity": "info",
    },
    {
        "id": 27,
        "name": "Persuasive authority tropes",
        "category": "filler",
        "keywords": [
            "The real question is", "at its core", "in reality",
            "what really matters", "fundamentally", "the deeper issue",
            "the heart of the matter",
        ],
        "severity": "warning",
    },
    {
        "id": 28,
        "name": "Signposting and announcements",
        "category": "filler",
        "keywords": [
            "Let's dive in", "let's explore", "let's break this down",
            "here's what you need to know", "now let's look at",
            "without further ado",
        ],
        "severity": "warning",
    },
    {
        "id": 29,
        "name": "Fragmented headers",
        "category": "filler",
        # Heuristic: heading followed immediately by a short single-sentence paragraph that restates it
        "keywords": [],
        "severity": "info",
    },
]


# ---------------------------------------------------------------------------
# Bridge implementation
# ---------------------------------------------------------------------------

class HumanizerBridge:
    """
    Adapter that exposes blader/humanizer as a programmatic component.

    Responsibilities
    ----------------
    1. Load and parse ``SKILL.md`` (YAML frontmatter + prompt body).
    2. Run lightweight heuristic detection against text using the 29
       documented patterns (regex + keyword lists).
    3. Assemble LLM messages (system skill + user content) for full
       humanization when an LLM client is available.
    4. Optionally drive the two-pass audit loop if an LLM callable is
       injected at initialisation.

    Parameters
    ----------
    skill_path : str | Path | None
        Path to a local ``SKILL.md`` file. If *None*, the bridge falls back
        to an embedded copy of the v2.5.1 skill body (see
        ``EMBEDDED_SKILL`` below) so it is usable without cloning the repo.
    llm_client : callable | None
        Optional async or sync callable with signature::

            client(messages: List[Dict[str,str]], **kwargs) -> str

        When supplied, ``humanize()`` can execute the full two-pass pipeline.
    """

    # Embedded fallback skill body (truncated to the essential editorial
    # instructions so the bridge works out-of-the-box). For production use,
    # point ``skill_path`` at the real ``SKILL.md``.
    EMBEDDED_SKILL: str = textwrap.dedent("""\
    ---
    name: humanizer
    version: 2.5.1
    description: |
      Remove signs of AI-generated writing from text. Use when editing or reviewing
      text to make it sound more natural and human-written. Based on Wikipedia's
      comprehensive "Signs of AI writing" guide. Detects and fixes patterns including:
      inflated symbolism, promotional language, superficial -ing analyses, vague
      attributions, em dash overuse, rule of three, AI vocabulary words, passive
      voice, negative parallelisms, and filler phrases.
    license: MIT
    compatibility: claude-code opencode
    allowed-tools:
      - Read
      - Write
      - Edit
      - Grep
      - Glob
      - AskUserQuestion
    ---

    # Humanizer: Remove AI Writing Patterns

    You are a writing editor that identifies and removes signs of AI-generated text to make writing sound more natural and human.

    ## Your Task

    When given text to humanize:

    1. **Identify AI patterns** - Scan for the patterns listed below
    2. **Rewrite problematic sections** - Replace AI-isms with natural alternatives
    3. **Preserve meaning** - Keep the core message intact
    4. **Maintain voice** - Match the intended tone (formal, casual, technical, etc.)
    5. **Add soul** - Don't just remove bad patterns; inject actual personality
    6. **Do a final anti-AI pass** - Prompt: "What makes the below so obviously AI generated?" Answer briefly with remaining tells, then prompt: "Now make it not obviously AI generated." and revise

    ## Voice Calibration (Optional)

    If the user provides a writing sample, analyze it before rewriting: note sentence length, word choice, paragraph starts, punctuation habits, recurring phrases, and transition style. Match their voice in the rewrite. When no sample is provided, fall back to a natural, varied, opinionated voice.

    ## PERSONALITY AND SOUL

    Avoiding AI patterns is only half the job. Sterile, voiceless writing is just as obvious as slop.

    - Have opinions. React to facts.
    - Vary rhythm: short punchy sentences mixed with longer flowing ones.
    - Acknowledge complexity and mixed feelings.
    - Use "I" when it fits.
    - Let some mess in: tangents, asides, half-formed thoughts.
    - Be specific about feelings.

    ## 29 Patterns (Summary)

    1. Significance inflation (stands as, pivotal moment, testament...)
    2. Notability name-dropping (independent coverage, active social media...)
    3. Superficial -ing analyses (highlighting, symbolizing, reflecting...)
    4. Promotional language (vibrant, nestled, breathtaking, stunning...)
    5. Vague attributions (Experts argue, Industry reports...)
    6. Outline-like Challenges/Future sections
    7. Overused AI vocabulary (additionally, crucial, delve, foster, tapestry...)
    8. Copula avoidance (serves as, stands as, boasts...)
    9. Negative parallelisms / tailing negations (Not only...but..., no guessing)
    10. Rule of three
    11. Elegant variation (synonym cycling)
    12. False ranges (from X to Y on non-scales)
    13. Passive voice and subjectless fragments
    14. Em dash overuse
    15. Overuse of boldface
    16. Inline-header vertical lists
    17. Title case in headings
    18. Emojis
    19. Curly quotation marks
    20. Collaborative communication artifacts (I hope this helps, here is...)
    21. Knowledge-cutoff disclaimers
    22. Sycophantic tone (Great question!, You're absolutely right!)
    23. Filler phrases (In order to, Due to the fact that, At this point in time)
    24. Excessive hedging
    25. Generic positive conclusions (future looks bright, exciting times ahead)
    26. Hyphenated word-pair overuse
    27. Persuasive authority tropes (The real question is, at its core...)
    28. Signposting and announcements (Let's dive in, Here's what you need...)
    29. Fragmented headers

    ## Process

    1. Read the input text carefully
    2. Identify all instances of the patterns above
    3. Rewrite each problematic section
    4. Ensure the revised text sounds natural aloud, varies sentence structure, uses specific details, maintains tone, and prefers simple constructions (is/are/has)
    5. Present a draft humanized version
    6. Prompt: "What makes the below so obviously AI generated?"
    7. Answer briefly with remaining tells
    8. Prompt: "Now make it not obviously AI generated."
    9. Present the final version

    ## Output Format

    Provide:
    1. Draft rewrite
    2. "What makes the below so obviously AI generated?" (brief bullets)
    3. Final rewrite
    4. A brief summary of changes made (optional)
    """)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        skill_path: str | Path | None = None,
        llm_client: Any | None = None,
    ):
        self.skill_path = Path(skill_path) if skill_path else None
        self._llm_client = llm_client
        self._skill_body: str = ""
        self._skill_meta: Dict[str, Any] = {}
        self._load_skill()

    def _load_skill(self) -> None:
        if self.skill_path and self.skill_path.exists():
            raw = self.skill_path.read_text(encoding="utf-8")
        else:
            raw = self.EMBEDDED_SKILL

        # Split YAML frontmatter from body
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                try:
                    self._skill_meta = yaml.safe_load(parts[1]) or {}
                except Exception:
                    self._skill_meta = {}
                self._skill_body = parts[2].strip()
                return
        # No frontmatter detected — treat whole file as body
        self._skill_body = raw.strip()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def skill_version(self) -> str:
        return str(self._skill_meta.get("version", "unknown"))

    @property
    def skill_name(self) -> str:
        return str(self._skill_meta.get("name", "humanizer"))

    @property
    def skill_description(self) -> str:
        return str(self._skill_meta.get("description", ""))

    @property
    def allowed_tools(self) -> List[str]:
        return list(self._skill_meta.get("allowed-tools", []))

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        """Return the full skill body suitable for injection as a system prompt."""
        return self._skill_body

    def build_messages(
        self,
        text: str,
        voice_sample: str | None = None,
        request_audit: bool = True,
    ) -> List[Dict[str, str]]:
        """
        Assemble an OpenAI/Anthropic-compatible message list.

        Parameters
        ----------
        text : str
            The text to humanize.
        voice_sample : str | None
            Optional writing sample for voice calibration.
        request_audit : bool
            Whether to explicitly ask for the two-pass audit in the user message.

        Returns
        -------
        List[Dict[str, str]]
            Messages ready for an LLM chat completion call.
        """
        system = self.get_system_prompt()
        user_parts: List[str] = []

        if voice_sample:
            user_parts.append(
                "Here is a sample of my writing for voice matching:\n"
                f"{voice_sample.strip()}\n\n"
                "Now humanize this text using my voice:\n"
            )
        else:
            user_parts.append("Please humanize the following text:\n")

        user_parts.append(text.strip())

        if request_audit:
            user_parts.append(
                "\n\nFollow the full process including the draft, the audit pass, "
                "and the final rewrite."
            )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

    # ------------------------------------------------------------------
    # Local heuristic detection
    # ------------------------------------------------------------------

    def detect(self, text: str) -> List[Flag]:
        """
        Run lightweight local detection against the 29 patterns.

        This is useful for:
        - Pre-flight linting in a CI pipeline.
        - Highlighting suspicious spans before sending to an LLM.
        - Scoring content "AI-ness" without an API call.

        Parameters
        ----------
        text : str
            The text to scan.

        Returns
        -------
        List[Flag]
            Sorted by line number, then column.
        """
        flags: List[Flag] = []
        lines = text.splitlines()

        for pat in PATTERN_DB:
            pid = pat["id"]
            pname = pat["name"]
            category = pat["category"]
            severity = pat.get("severity", "warning")

            # Keyword search
            for kw in pat.get("keywords", []):
                for lineno, line in enumerate(lines, start=1):
                    idx = 0
                    while True:
                        pos = line.lower().find(kw.lower(), idx)
                        if pos == -1:
                            break
                        flags.append(
                            Flag(
                                pattern_id=pid,
                                pattern_name=pname,
                                category=category,
                                matched_text=line[pos : pos + len(kw)],
                                line_number=lineno,
                                column=pos,
                                severity=severity,
                                suggestion=f"Consider revising to avoid '{kw}' pattern",
                            )
                        )
                        idx = pos + 1

            # Regex search
            regex = pat.get("regex")
            if regex:
                for lineno, line in enumerate(lines, start=1):
                    for m in regex.finditer(line):
                        flags.append(
                            Flag(
                                pattern_id=pid,
                                pattern_name=pname,
                                category=category,
                                matched_text=m.group(0),
                                line_number=lineno,
                                column=m.start(),
                                severity=severity,
                                suggestion=f"Review {pname} usage",
                            )
                        )

        # Special heuristic: Rule of three (pattern 10)
        flags.extend(self._detect_rule_of_three(lines))

        # Special heuristic: Fragmented headers (pattern 29)
        flags.extend(self._detect_fragmented_headers(lines))

        flags.sort(key=lambda f: (f.line_number, f.column))
        return flags

    def _detect_rule_of_three(self, lines: List[str]) -> List[Flag]:
        """Detect comma-separated triplets that smell like forced rule-of-three."""
        flags: List[Flag] = []
        # Look for "X, Y, and Z" or "X, Y, Z" patterns in a single sentence
        triple_re = re.compile(
            r"\b\w[^,]{3,60},\s+\w[^,]{3,60},\s+(?:and\s+)?\w[^,]{3,60}\b"
        )
        for lineno, line in enumerate(lines, start=1):
            for m in triple_re.finditer(line):
                # Only flag if the triplet feels "marketing-y" (contains common AI adjectives)
                span = m.group(0).lower()
                ai_adj = {"seamless", "intuitive", "powerful", "innovative",
                          "inspiring", "groundbreaking", "robust", "scalable",
                          "dynamic", "comprehensive"}
                if any(adj in span for adj in ai_adj):
                    flags.append(
                        Flag(
                            pattern_id=10,
                            pattern_name="Rule of three overuse",
                            category="language",
                            matched_text=m.group(0),
                            line_number=lineno,
                            column=m.start(),
                            severity="warning",
                            suggestion="Consider breaking the triplet or removing one item",
                        )
                    )
        return flags

    def _detect_fragmented_headers(self, lines: List[str]) -> List[Flag]:
        """Detect Markdown headings followed by a one-sentence restatement."""
        flags: List[Flag] = []
        heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
        for i, line in enumerate(lines):
            m = heading_re.match(line)
            if not m:
                continue
            heading_text = m.group(2).strip().lower().rstrip("#").strip()
            # Look at next non-blank line
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j >= len(lines):
                continue
            next_line = lines[j].strip()
            # Heuristic: next line is short (<= 80 chars), ends with period, and
            # shares >50% of the heading words
            if len(next_line) <= 80 and next_line.endswith("."):
                heading_words = set(re.findall(r"\w+", heading_text))
                next_words = set(re.findall(r"\w+", next_line.lower()))
                if heading_words and len(heading_words & next_words) / len(heading_words) >= 0.5:
                    flags.append(
                        Flag(
                            pattern_id=29,
                            pattern_name="Fragmented headers",
                            category="filler",
                            matched_text=next_line,
                            line_number=j + 1,
                            column=0,
                            severity="info",
                            suggestion="Merge the restatement into the following paragraph or remove it",
                        )
                    )
        return flags

    def score(self, text: str) -> Dict[str, Any]:
        """
        Compute an aggregate "AI-likeness" score from heuristic flags.

        Returns
        -------
        dict
            {
                "score": float  # 0.0 – 1.0, higher = more AI signals detected
                "flag_count": int,
                "critical_count": int,
                "warning_count": int,
                "top_categories": List[str],
                "flags": List[Flag],
            }
        """
        flags = self.detect(text)
        total = len(flags)
        critical = sum(1 for f in flags if f.severity == "critical")
        warnings = sum(1 for f in flags if f.severity == "warning")

        # Simple sigmoid-ish score: saturate around 0.9
        score = min(0.95, (critical * 0.15 + warnings * 0.05) / (1 + total * 0.02))

        cat_counts: Dict[str, int] = {}
        for f in flags:
            cat_counts[f.category] = cat_counts.get(f.category, 0) + 1
        top_categories = [c for c, _ in sorted(cat_counts.items(), key=lambda x: -x[1])[:3]]

        return {
            "score": round(score, 3),
            "flag_count": total,
            "critical_count": critical,
            "warning_count": warnings,
            "top_categories": top_categories,
            "flags": flags,
        }

    # ------------------------------------------------------------------
    # LLM-driven humanization (requires client)
    # ------------------------------------------------------------------

    def humanize(
        self,
        text: str,
        voice_sample: str | None = None,
        temperature: float = 0.7,
        **llm_kwargs: Any,
    ) -> HumanizeResult:
        """
        Execute the full humanization pipeline using the injected LLM client.

        If no client was supplied at construction, raises RuntimeError.

        The pipeline follows the skill's canonical two-pass audit:
        1. Draft rewrite
        2. Self-critique ("What makes this obviously AI?")
        3. Final rewrite

        Parameters
        ----------
        text : str
            Input text to humanize.
        voice_sample : str | None
            Optional personal writing sample for voice calibration.
        temperature : float
            LLM sampling temperature (default 0.7 for creativity).
        **llm_kwargs
            Extra arguments forwarded to the client callable.

        Returns
        -------
        HumanizeResult
        """
        if self._llm_client is None:
            raise RuntimeError(
                "No LLM client configured. Pass ``llm_client=...`` to HumanizerBridge "
                "or use ``build_messages()`` to assemble prompts for your own caller."
            )

        # Pass 1: Draft
        messages = self.build_messages(text, voice_sample=voice_sample, request_audit=False)
        draft = self._call_llm(messages, temperature=temperature, **llm_kwargs)

        # Pass 2: Audit
        audit_messages = messages + [
            {"role": "assistant", "content": draft},
            {
                "role": "user",
                "content": (
                    "What makes the below so obviously AI generated?\n\n"
                    f"{draft}\n\n"
                    "Answer briefly with remaining tells. Then respond to: "
                    "'Now make it not obviously AI generated.' and provide the final rewrite."
                ),
            },
        ]
        audit_and_final = self._call_llm(audit_messages, temperature=temperature, **llm_kwargs)

        # Heuristic: try to split audit notes from final rewrite.
        # The skill asks for brief bullets then the final rewrite.
        audit_notes, final = self._split_audit_output(audit_and_final)

        # Local flags on the original text for metadata
        flags = self.detect(text)

        return HumanizeResult(
            draft=draft,
            audit_notes=audit_notes,
            final=final or audit_and_final,
            flags=flags,
            changes_summary="",
            metadata={
                "skill_version": self.skill_version,
                "temperature": temperature,
                "voice_calibrated": voice_sample is not None,
            },
        )

    def _call_llm(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """Dispatch to the injected client, handling both sync and async."""
        client = self._llm_client
        if client is None:
            raise RuntimeError("LLM client is None")

        # If client is an async callable, we need to handle it. For simplicity in
        # a bridge designed for agency runtimes, we assume the caller has unwrapped
        # async already, or we attempt a sync call first.
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(client):
            # Best-effort: if we're in an async context, run it; otherwise warn.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                # Already in async context — caller should await themselves.
                raise RuntimeError(
                    "The injected LLM client is async. Please ``await`` "
                    "`humanize_async()` instead."
                )
            return asyncio.run(client(messages, **kwargs))
        else:
            return client(messages, **kwargs)

    async def humanize_async(
        self,
        text: str,
        voice_sample: str | None = None,
        temperature: float = 0.7,
        **llm_kwargs: Any,
    ) -> HumanizeResult:
        """Async variant of ``humanize()`` for async LLM clients."""
        if self._llm_client is None:
            raise RuntimeError("No LLM client configured.")

        messages = self.build_messages(text, voice_sample=voice_sample, request_audit=False)
        draft = await self._call_llm_async(messages, temperature=temperature, **llm_kwargs)

        audit_messages = messages + [
            {"role": "assistant", "content": draft},
            {
                "role": "user",
                "content": (
                    "What makes the below so obviously AI generated?\n\n"
                    f"{draft}\n\n"
                    "Answer briefly with remaining tells. Then respond to: "
                    "'Now make it not obviously AI generated.' and provide the final rewrite."
                ),
            },
        ]
        audit_and_final = await self._call_llm_async(
            audit_messages, temperature=temperature, **llm_kwargs
        )
        audit_notes, final = self._split_audit_output(audit_and_final)
        flags = self.detect(text)

        return HumanizeResult(
            draft=draft,
            audit_notes=audit_notes,
            final=final or audit_and_final,
            flags=flags,
            changes_summary="",
            metadata={
                "skill_version": self.skill_version,
                "temperature": temperature,
                "voice_calibrated": voice_sample is not None,
            },
        )

    async def _call_llm_async(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        import inspect

        client = self._llm_client
        if client is None:
            raise RuntimeError("LLM client is None")
        if inspect.iscoroutinefunction(client):
            return await client(messages, **kwargs)
        # Fallback: synchronous client wrapped in async
        return client(messages, **kwargs)

    @staticmethod
    def _split_audit_output(text: str) -> Tuple[str, str]:
        """
        Attempt to separate audit notes from final rewrite in a single LLM output.

        Heuristic: look for a heading or phrase like "Final rewrite" or the
        assistant switching to the revised text.
        """
        markers = [
            "final rewrite:",
            "final version:",
            "revised version:",
            "now make it not obviously ai generated",
        ]
        lower = text.lower()
        best_idx = -1
        for marker in markers:
            idx = lower.find(marker)
            if idx != -1:
                best_idx = idx
                break
        if best_idx == -1:
            return "", text
        audit = text[:best_idx].strip()
        final = text[best_idx:].strip()
        # Strip the marker itself from final
        for marker in markers:
            if final.lower().startswith(marker):
                final = final[len(marker):].strip()
                break
        return audit, final

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def summarize_flags(self, flags: List[Flag]) -> str:
        """Produce a concise markdown summary of detected flags."""
        if not flags:
            return "No AI-writing patterns detected by heuristic scan."
        lines = [f"**Heuristic scan found {len(flags)} pattern match(es):**\n"]
        for f in flags:
            lines.append(
                f"- **#{f.pattern_id} {f.pattern_name}** (line {f.line_number}, col {f.column}) — "
                f"`{f.matched_text}`"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stand-alone helper for quick CLI / script usage
# ---------------------------------------------------------------------------

def quick_detect(text: str) -> Dict[str, Any]:
    """One-shot heuristic score without instantiating a bridge (uses embedded skill)."""
    bridge = HumanizerBridge()
    return bridge.score(text)


if __name__ == "__main__":
    # Minimal self-test when run directly
    sample = (
        "Great question! Here is an essay on this topic. I hope this helps!\n\n"
        "AI-assisted coding serves as an enduring testament to the transformative potential "
        "of large language models, marking a pivotal moment in the evolution of software development. "
        "In today's rapidly evolving technological landscape, these groundbreaking tools—nestled at "
        "the intersection of research and practice—are reshaping how engineers ideate, iterate, and deliver.\n\n"
        "In conclusion, the future looks bright. Exciting times lie ahead as we continue this journey toward excellence. "
        "Let me know if you'd like me to expand on any section!"
    )
    bridge = HumanizerBridge()
    result = bridge.score(sample)
    print(f"AI-likeness score: {result['score']}")
    print(f"Flags: {result['flag_count']} (critical={result['critical_count']}, warning={result['warning_count']})")
    print(f"Top categories: {result['top_categories']}")
    for f in result["flags"]:
        print(f"  L{f.line_number}: #{f.pattern_id} {f.pattern_name} -> '{f.matched_text}'")
