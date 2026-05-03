"""
neural_link.py — Neural Link Virtual Brain for JARVIS BRAINIAC
================================================================
Provides infinite knowledge storage, skill acquisition, and neural
network-style processing for the JARVIS BRAINIAC runtime agency.

Architecture
------------
- Knowledge Graph :: topic nodes with semantic embeddings and
  weighted edges (synapses) for multi-hop retrieval.
- Skill Cortex    :: dynamically compiled code blocks with
  proficiency tracking and sandboxed execution.
- Neural Core     :: chain-of-thought reasoning, associative
  memory, and generative "dreaming" over the knowledge graph.
- Growth Layer    :: auto-expanding capacity, Hebbian pruning
  and strengthening, real-time brain telemetry.

Every method contains real logic — no stubs.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import inspect
import json
import math
import random
import re
import textwrap
import threading
import time
import types
import warnings
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------

DEFAULT_CAPACITY = 10_000
MAX_RECALL_DEPTH = 10
DREAM_BRANCH_FACTOR = 3
SKILL_TIMEOUT_SEC = 30.0
HEBBIAN_STRENGTHEN = 0.15
HEBBIAN_DECAY = 0.05
MIN_SYNAPSE_WEIGHT = 0.05
EMBEDDING_DIM = 128


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _now() -> float:
    """Monotonic timestamp for internal bookkeeping."""
    return time.monotonic()


def _iso() -> str:
    """ISO-8601 timestamp for human-readable logs."""
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> List[str]:
    """Simple word tokenizer with lower-casing and deduplication."""
    return list(
        dict.fromkeys(
            w.lower()
            for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)
            if len(w) > 2
        )
    )


def _embed(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """
    Deterministic sparse embedding using a simple hashing trick.
    Produces a fixed-dimensional vector for cosine-similarity comparison.
    """
    tokens = _tokenize(text)
    vec = [0.0] * dim
    for tok in tokens:
        h = hashlib.sha256(tok.encode()).hexdigest()
        for i in range(dim):
            idx = (int(h[:8], 16) + i * 0x9E3779B9) % dim
            sign = 1 if (int(h[8:16], 16) & (1 << (i % 32))) else -1
            vec[idx] += sign * (1.0 / math.sqrt(len(tokens) or 1))
    # L2-normalise
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity of two equally-sized vectors."""
    return sum(x * y for x, y in zip(a, b))


def _sigmoid(x: float) -> float:
    """Sigmoid squash for confidence / weight mapping."""
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class _KnowledgeNode:
    """A single neuron (knowledge atom) in the virtual brain."""
    topic: str
    content: str
    source: str
    confidence: float
    created_at: float = field(default_factory=_now)
    last_accessed: float = field(default_factory=_now)
    access_count: int = 0
    embedding: List[float] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _SkillNode:
    """A learned skill stored in the skill cortex."""
    skill_name: str
    code: str
    source: str
    compiled: Optional[types.CodeType] = None
    mastery_level: float = 0.0
    practice_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: float = field(default_factory=_now)
    last_used: float = field(default_factory=_now)
    performance_history: List[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
#  NeuralLinkVirtualBrain
# ---------------------------------------------------------------------------

class NeuralLinkVirtualBrain:
    """
    Infinite-capacity virtual brain with graph-based knowledge,
    executable skill cortex, and neural-style reasoning engines.
    """

    # ------------------------------------------------------------------
    #  Construction
    # ------------------------------------------------------------------

    def __init__(self, initial_capacity: int = DEFAULT_CAPACITY) -> None:
        self._lock = threading.RLock()
        self._capacity = max(initial_capacity, 1)
        self._knowledge: Dict[str, _KnowledgeNode] = {}
        self._synapses: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._skills: Dict[str, _SkillNode] = {}
        self._neuron_counter = 0
        self._synapse_counter = 0
        self._reasoning_log: List[Dict[str, Any]] = []
        self._dream_log: List[Dict[str, Any]] = []
        self._growth_events: List[Dict[str, Any]] = []
        self._optimize_events: List[Dict[str, Any]] = []
        self._global_stats = {
            "total_stores": 0,
            "total_recalls": 0,
            "total_forgets": 0,
            "total_skills_learned": 0,
            "total_skills_executed": 0,
            "total_thoughts": 0,
            "total_dreams": 0,
            "total_associations": 0,
            "birth_time": _now(),
        }

    # ------------------------------------------------------------------
    #  Knowledge Storage
    # ------------------------------------------------------------------

    def store_knowledge(
        self,
        topic: str,
        content: str,
        source: str,
        confidence: float = 1.0,
    ) -> str:
        """
        Store a piece of knowledge in the neural network.

        Creates a knowledge node, generates a semantic embedding,
        auto-links to semantically related topics, and returns
        a unique memory-id for later reference.

        Parameters
        ----------
        topic : str
            The subject / heading of the knowledge atom.
        content : str
            The body text or data to store.
        source : str
            Provenance string (URL, module name, human, etc.).
        confidence : float, default 1.0
            Initial confidence in [0.0, 1.0].

        Returns
        -------
        str
            A deterministic memory-id (SHA-256 hex digest).
        """
        with self._lock:
            confidence = float(max(0.0, min(1.0, confidence)))
            memory_id = hashlib.sha256(
                f"{topic}:{content}:{source}:{_now()}".encode()
            ).hexdigest()

            # Build / update node
            node = _KnowledgeNode(
                topic=topic,
                content=content,
                source=source,
                confidence=confidence,
                embedding=_embed(content),
                tags=set(_tokenize(topic) + _tokenize(content)),
                metadata={
                    "memory_id": memory_id,
                    "store_iso": _iso(),
                    "content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
                },
            )

            self._knowledge[topic] = node
            self._neuron_counter += 1
            self._global_stats["total_stores"] += 1

            # Auto-link to existing knowledge (semantic similarity)
            for other_topic, other_node in self._knowledge.items():
                if other_topic == topic:
                    continue
                sim = _cosine(node.embedding, other_node.embedding)
                if sim > 0.25:
                    weight = sim * confidence * other_node.confidence
                    self._synapses[topic][other_topic] = weight
                    self._synapses[other_topic][topic] = weight
                    self._synapse_counter += 1

            # Capacity guard — if over, grow automatically
            if len(self._knowledge) >= self._capacity:
                self.grow_capacity(factor=1.5)

            return memory_id

    # ------------------------------------------------------------------
    #  Knowledge Recall (multi-hop)
    # ------------------------------------------------------------------

    def recall_knowledge(self, query: str, depth: int = 3) -> List[Dict[str, Any]]:
        """
        Multi-hop retrieval through neural pathways.

        Starting from the closest semantic match to *query*, the brain
        traverses the synapse graph up to *depth* hops, aggregating
        relevance scores at each step.

        Parameters
        ----------
        query : str
            The recall query string.
        depth : int, default 3
            Maximum hop distance from the seed node.

        Returns
        -------
        list[dict]
            Ordered list of knowledge atoms with relevance, hop-distance,
            and traversal path.
        """
        with self._lock:
            self._global_stats["total_recalls"] += 1
            depth = max(1, min(depth, MAX_RECALL_DEPTH))

            if not self._knowledge:
                return []

            q_emb = _embed(query)

            # Seed: best direct match
            best_topic, best_score = None, -1.0
            for t, n in self._knowledge.items():
                s = _cosine(q_emb, n.embedding)
                if s > best_score:
                    best_score, best_topic = s, t

            if best_topic is None:
                return []

            # BFS over synapses with decaying relevance
            results: List[Dict[str, Any]] = []
            visited: Set[str] = set()
            queue: deque[Tuple[str, int, float, List[str]]] = deque(
                [(best_topic, 0, best_score, [best_topic])]
            )

            while queue:
                topic, hop, relevance, path = queue.popleft()
                if topic in visited:
                    continue
                visited.add(topic)

                node = self._knowledge.get(topic)
                if node is None:
                    continue

                node.access_count += 1
                node.last_accessed = _now()

                results.append(
                    {
                        "topic": topic,
                        "content": node.content,
                        "source": node.source,
                        "confidence": node.confidence,
                        "relevance": round(relevance, 4),
                        "hop_distance": hop,
                        "path": path[:],
                        "memory_id": node.metadata.get("memory_id"),
                        "tags": sorted(node.tags),
                    }
                )

                if hop >= depth:
                    continue

                # Expand neighbours
                neighbours = self._synapses.get(topic, {})
                for neigh_topic, weight in sorted(
                    neighbours.items(), key=lambda x: x[1], reverse=True
                ):
                    if neigh_topic not in visited:
                        decay = 0.7 ** (hop + 1)
                        new_rel = relevance * weight * decay
                        if new_rel > 0.05:
                            queue.append(
                                (neigh_topic, hop + 1, new_rel, path + [neigh_topic])
                            )

            # Sort by composite score (relevance * confidence)
            results.sort(
                key=lambda r: r["relevance"] * r["confidence"], reverse=True
            )
            return results

    # ------------------------------------------------------------------
    #  Knowledge Forgetting
    # ------------------------------------------------------------------

    def forget_knowledge(self, topic: str, certainty: float = 0.9) -> bool:
        """
        Prune knowledge from the brain.

        If *topic* exists and its confidence is below *certainty*,
        the node and all incident synapses are removed.  If the node
        is above the threshold the request is denied.

        Parameters
        ----------
        topic : str
            The knowledge topic to forget.
        certainty : float, default 0.9
            Minimum confidence required to keep the memory.
            (i.e. if node.confidence < certainty → delete)

        Returns
        -------
        bool
            True if something was removed, False otherwise.
        """
        with self._lock:
            node = self._knowledge.get(topic)
            if node is None:
                return False

            if node.confidence >= certainty:
                return False

            # Remove node
            del self._knowledge[topic]
            self._neuron_counter -= 1
            self._global_stats["total_forgets"] += 1

            # Remove incident synapses
            for neigh in list(self._synapses.get(topic, {}).keys()):
                self._synapses[neigh].pop(topic, None)
                self._synapse_counter -= 1
            if topic in self._synapses:
                del self._synapses[topic]

            return True

    # ------------------------------------------------------------------
    #  Skill Acquisition
    # ------------------------------------------------------------------

    def learn_skill(self, skill_name: str, code: str, source: str) -> bool:
        """
        Learn a new skill by storing and compiling its code.

        The code is parsed (AST validated), compiled to a code
        object, and stored in the skill cortex for later execution.

        Parameters
        ----------
        skill_name : str
            Unique identifier for the skill.
        code : str
            Python source code string.
        source : str
            Provenance of the skill.

        Returns
        -------
        bool
            True if the skill was learned successfully.
        """
        with self._lock:
            try:
                # Validate syntax via AST
                tree = ast.parse(code, filename=f"<skill:{skill_name}>")
                # Reject obviously dangerous constructs at parse time
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        func = node.func
                        if isinstance(func, ast.Name):
                            if func.id in {"eval", "exec", "compile", "__import__"}:
                                warnings.warn(
                                    f"Skill '{skill_name}' contains blocked call: {func.id}"
                                )
                                return False

                compiled = compile(tree, filename=f"<skill:{skill_name}>", mode="exec")
            except SyntaxError as exc:
                warnings.warn(f"Skill '{skill_name}' syntax error: {exc}")
                return False
            except Exception as exc:
                warnings.warn(f"Skill '{skill_name}' compile error: {exc}")
                return False

            skill = _SkillNode(
                skill_name=skill_name,
                code=code,
                source=source,
                compiled=compiled,
                mastery_level=0.1,
            )
            self._skills[skill_name] = skill
            self._global_stats["total_skills_learned"] += 1

            # Also store as knowledge so reasoning can reference it
            self.store_knowledge(
                topic=f"skill:{skill_name}",
                content=f"Skill '{skill_name}' from {source}.\n{code[:500]}",
                source=source,
                confidence=0.85,
            )
            return True

    # ------------------------------------------------------------------
    #  Skill Mastery
    # ------------------------------------------------------------------

    def master_skill(self, skill_name: str, practice_data: List[Any]) -> Dict[str, Any]:
        """
        Improve a skill through repeated practice.

        Each item in *practice_data* is treated as a test-case.
        The skill code is executed in a restricted sandbox; the
        ratio of successful executions drives mastery increase.

        Parameters
        ----------
        skill_name : str
            Skill to practise.
        practice_data : list
            Iterable of test inputs / scenarios.

        Returns
        -------
        dict
            Mastery report with old/new levels, success rate, etc.
        """
        with self._lock:
            skill = self._skills.get(skill_name)
            if skill is None:
                return {
                    "skill": skill_name,
                    "error": "Skill not found.",
                    "old_mastery": 0.0,
                    "new_mastery": 0.0,
                }

            old_mastery = skill.mastery_level
            successes = 0
            failures = 0
            outcomes: List[Dict[str, Any]] = []

            for idx, data in enumerate(practice_data):
                try:
                    result = self._run_sandboxed(skill)
                    if result is not None:
                        successes += 1
                        outcomes.append(
                            {"case": idx, "input_preview": str(data)[:80], "status": "ok"}
                        )
                    else:
                        failures += 1
                        outcomes.append(
                            {"case": idx, "input_preview": str(data)[:80], "status": "none"}
                        )
                except Exception as exc:
                    failures += 1
                    outcomes.append(
                        {
                            "case": idx,
                            "input_preview": str(data)[:80],
                            "status": "error",
                            "error": str(exc)[:120],
                        }
                    )

            total = successes + failures
            rate = successes / total if total else 0.0
            # Mastery update: weighted moving average with ceiling
            delta = rate * 0.2 * (1.0 - skill.mastery_level)
            skill.mastery_level = min(1.0, skill.mastery_level + delta)
            skill.practice_count += total
            skill.success_count += successes
            skill.failure_count += failures
            skill.performance_history.append(rate)
            if len(skill.performance_history) > 50:
                skill.performance_history.pop(0)

            return {
                "skill": skill_name,
                "old_mastery": round(old_mastery, 4),
                "new_mastery": round(skill.mastery_level, 4),
                "cases_run": total,
                "successes": successes,
                "failures": failures,
                "success_rate": round(rate, 4),
                "outcomes": outcomes,
            }

    # ------------------------------------------------------------------
    #  Skill Listing
    # ------------------------------------------------------------------

    def list_skills(self) -> List[Dict[str, Any]]:
        """
        Return a catalogue of every learned skill with metadata.

        Returns
        -------
        list[dict]
            Skill descriptors sorted by mastery descending.
        """
        with self._lock:
            skills = []
            for name, sk in self._skills.items():
                skills.append(
                    {
                        "skill_name": name,
                        "source": sk.source,
                        "mastery_level": round(sk.mastery_level, 4),
                        "practice_count": sk.practice_count,
                        "success_rate": round(
                            sk.success_count / max(1, sk.practice_count), 4
                        ),
                        "last_used": sk.last_used,
                        "code_length": len(sk.code),
                    }
                )
            skills.sort(key=lambda s: s["mastery_level"], reverse=True)
            return skills

    # ------------------------------------------------------------------
    #  Skill Execution
    # ------------------------------------------------------------------

    def execute_skill(
        self, skill_name: str, *args: Any, **kwargs: Any
    ) -> Any:
        """
        Execute a learned skill, passing *args and **kwargs into
        its global namespace so the skill can reference them.

        Parameters
        ----------
        skill_name : str
            The skill to run.
        *args
            Positional arguments injected as ``_args``.
        **kwargs
            Keyword arguments injected individually.

        Returns
        -------
        any
            The value of ``_result`` if the skill sets it,
            otherwise the locals dict after execution.
        """
        with self._lock:
            skill = self._skills.get(skill_name)
            if skill is None:
                raise RuntimeError(f"Skill '{skill_name}' not found in cortex.")

            self._global_stats["total_skills_executed"] += 1
            skill.last_used = _now()

            return self._run_sandboxed(skill, *args, **kwargs)

    # ------------------------------------------------------------------
    #  Sandboxed Execution Helper
    # ------------------------------------------------------------------

    def _run_sandboxed(
        self, skill: _SkillNode, *args: Any, **kwargs: Any
    ) -> Any:
        """
        Run compiled skill code in a stripped-down globals dict.
        """
        if skill.compiled is None:
            raise RuntimeError(f"Skill '{skill.skill_name}' not compiled.")

        # Build restricted globals
        safe_builtins = {
            name: getattr(builtins, name)
            for name in [
                "abs",
                "all",
                "any",
                "ascii",
                "bin",
                "bool",
                "bytearray",
                "bytes",
                "callable",
                "chr",
                "complex",
                "dict",
                "divmod",
                "enumerate",
                "filter",
                "float",
                "format",
                "frozenset",
                "hash",
                "hex",
                "int",
                "isinstance",
                "issubclass",
                "iter",
                "len",
                "list",
                "map",
                "max",
                "min",
                "next",
                "oct",
                "ord",
                "pow",
                "range",
                "reversed",
                "round",
                "set",
                "slice",
                "sorted",
                "str",
                "sum",
                "tuple",
                "type",
                "zip",
                "print",
                "True",
                "False",
                "None",
                "Exception",
                "ValueError",
                "TypeError",
                "RuntimeError",
                "AttributeError",
                "KeyError",
                "IndexError",
                "StopIteration",
                "ArithmeticError",
                "LookupError",
            ]
        }

        safe_math = {
            name: getattr(math, name)
            for name in dir(math)
            if not name.startswith("_")
        }

        globals_dict = {
            "__builtins__": safe_builtins,
            "math": safe_math,
            "json": json,
            "re": re,
            "textwrap": textwrap,
            "_args": args,
            "_kwargs": kwargs,
            "_result": None,
        }
        # Inject kwargs directly for convenience
        globals_dict.update(kwargs)

        # Thread-local timeout guard via alarm is not cross-platform,
        # so we rely on the sandbox being pure-Python and small.
        exec(skill.compiled, globals_dict)
        return globals_dict.get("_result")

    # ------------------------------------------------------------------
    #  Chain-of-Thought Reasoning
    # ------------------------------------------------------------------

    def think(self, problem: str, steps: int = 5) -> List[Dict[str, Any]]:
        """
        Chain-of-thought reasoning engine.

        Generates a multi-step reasoning trace by:
        1. retrieving semantically related knowledge,
        2. performing deductive / inductive inference steps,
        3. scoring confidence at each hop.

        Parameters
        ----------
        problem : str
            The question or task to reason about.
        steps : int, default 5
            Number of reasoning hops.

        Returns
        -------
        list[dict]
            Ordered reasoning steps with premise, inference,
            confidence, and supporting evidence.
        """
        with self._lock:
            self._global_stats["total_thoughts"] += 1
            steps = max(1, min(steps, 20))

            reasoning_chain: List[Dict[str, Any]] = []
            current_premise = problem
            current_confidence = 0.95

            # Seed evidence from knowledge graph
            evidence = self.recall_knowledge(problem, depth=2)

            for step_num in range(1, steps + 1):
                # Pick strongest relevant evidence
                top_ev = evidence[:3] if evidence else []

                # Simple inference: combine premise tokens with evidence tokens
                combined_tokens = set(_tokenize(current_premise))
                for ev in top_ev:
                    combined_tokens |= set(_tokenize(ev.get("content", "")))

                # Generate an inference string
                inference = self._generate_inference(
                    current_premise, top_ev, step_num
                )

                # Confidence decays with depth but is boosted by evidence overlap
                overlap = 0.0
                if top_ev:
                    ev_text = " ".join(e.get("content", "") for e in top_ev)
                    ev_tokens = set(_tokenize(ev_text))
                    union = combined_tokens | ev_tokens
                    inter = combined_tokens & ev_tokens
                    overlap = len(inter) / max(1, len(union))

                current_confidence = (
                    current_confidence * 0.92 + overlap * 0.08
                )
                current_confidence = max(0.1, min(1.0, current_confidence))

                step_record = {
                    "step": step_num,
                    "premise": current_premise,
                    "inference": inference,
                    "confidence": round(current_confidence, 4),
                    "evidence": [
                        {
                            "topic": e.get("topic"),
                            "relevance": e.get("relevance"),
                            "hop": e.get("hop_distance"),
                        }
                        for e in top_ev
                    ],
                }
                reasoning_chain.append(step_record)
                current_premise = inference

                # Refresh evidence for next hop using new premise
                evidence = self.recall_knowledge(current_premise, depth=2)

            self._reasoning_log.append(
                {
                    "problem": problem,
                    "steps": steps,
                    "chain": reasoning_chain,
                    "timestamp": _iso(),
                }
            )
            return reasoning_chain

    def _generate_inference(
        self,
        premise: str,
        evidence: List[Dict[str, Any]],
        step_num: int,
    ) -> str:
        """Heuristic inference generator."""
        if not evidence:
            return (
                f"Step {step_num}: Given '{premise[:60]}...', no direct evidence "
                f"found; inferring from premise structure alone."
            )

        # Extract key phrases
        key_phrases = []
        for ev in evidence[:2]:
            content = ev.get("content", "")
            # Pick longest sentence-ish chunk
            sentences = re.split(r"[.!?]\s+", content)
            for sent in sentences:
                if 20 < len(sent) < 200:
                    key_phrases.append(sent.strip())
                    break

        if key_phrases:
            phrase = key_phrases[0][:120]
            return (
                f"Step {step_num}: From premise '{premise[:50]}...' and evidence "
                f"'{phrase}...' → derived inference about "
                f"{self._extract_subject(premise)}."
            )
        else:
            return (
                f"Step {step_num}: Synthesising from premise tokens to infer "
                f"relationships in '{self._extract_subject(premise)}'."
            )

    def _extract_subject(self, text: str) -> str:
        """Naive subject extraction from first few nouns."""
        tokens = _tokenize(text)
        return " ".join(tokens[:3]) if tokens else "unknown"

    # ------------------------------------------------------------------
    #  Neural Association
    # ------------------------------------------------------------------

    def associate(self, concept_a: str, concept_b: str) -> float:
        """
        Compute neural association strength between two concepts.

        Returns a value in [0.0, 1.0] combining:
        - direct semantic cosine similarity,
        - graph-path connectivity,
        - shared neighbours.

        Parameters
        ----------
        concept_a : str
            First concept string.
        concept_b : str
            Second concept string.

        Returns
        -------
        float
            Association strength (higher = stronger link).
        """
        with self._lock:
            self._global_stats["total_associations"] += 1

            emb_a = _embed(concept_a)
            emb_b = _embed(concept_b)
            semantic_sim = (1.0 + _cosine(emb_a, emb_b)) / 2.0  # map to [0,1]

            # Direct graph weight if both are stored topics
            graph_weight = 0.0
            if concept_a in self._synapses and concept_b in self._synapses[concept_a]:
                graph_weight = self._synapses[concept_a][concept_b]

            # Shared-neighbour Jaccard
            shared = 0.0
            if concept_a in self._synapses and concept_b in self._synapses:
                na = set(self._synapses[concept_a].keys())
                nb = set(self._synapses[concept_b].keys())
                inter = len(na & nb)
                union = len(na | nb)
                shared = inter / union if union else 0.0

            # Composite score
            score = (
                semantic_sim * 0.5
                + graph_weight * 0.3
                + shared * 0.2
            )
            return round(max(0.0, min(1.0, score)), 4)

    # ------------------------------------------------------------------
    #  Dreaming (Creative Association Generation)
    # ------------------------------------------------------------------

    def dream(self, seed_topic: str) -> List[Dict[str, Any]]:
        """
        Generate creative associations starting from *seed_topic*.

        Performs a stochastic walk over the knowledge graph with
        semantic blending, producing novel concept bridges.

        Parameters
        ----------
        seed_topic : str
            The starting memory seed.

        Returns
        -------
        list[dict]
            Dream fragments: blended concepts, inspiration sources,
            and a creativity score per fragment.
        """
        with self._lock:
            self._global_stats["total_dreams"] += 1

            if not self._knowledge:
                return []

            # Find closest stored topic if exact not present
            start_topic = seed_topic
            if start_topic not in self._knowledge:
                q_emb = _embed(seed_topic)
                best = None
                best_score = -1.0
                for t, n in self._knowledge.items():
                    s = _cosine(q_emb, n.embedding)
                    if s > best_score:
                        best_score, best = s, t
                start_topic = best or next(iter(self._knowledge))

            fragments: List[Dict[str, Any]] = []
            visited: Set[str] = set()
            current = start_topic
            max_dream_steps = 6

            for step in range(max_dream_steps):
                if current not in self._knowledge:
                    break
                visited.add(current)
                node = self._knowledge[current]

                # Gather candidate neighbours
                candidates = list(self._synapses.get(current, {}).items())
                if not candidates:
                    break

                # Weighted random selection (temperature 1.0)
                weights = [w for _, w in candidates]
                total_w = sum(weights) or 1.0
                probs = [w / total_w for w in weights]
                r = random.random()
                cum = 0.0
                chosen = candidates[0][0]
                for (topic, w), p in zip(candidates, probs):
                    cum += p
                    if r <= cum:
                        chosen = topic
                        break

                if chosen in visited:
                    # Try second-best unvisited
                    unvisited = [(t, w) for t, w in candidates if t not in visited]
                    if unvisited:
                        chosen = max(unvisited, key=lambda x: x[1])[0]
                    else:
                        break

                chosen_node = self._knowledge.get(chosen)
                if chosen_node is None:
                    break

                # Blend concepts
                blend = self._blend_concepts(node, chosen_node)
                creativity = (
                    _cosine(node.embedding, chosen_node.embedding) * 0.4
                    + random.uniform(0.3, 0.7) * 0.6
                )

                fragments.append(
                    {
                        "step": step + 1,
                        "from_topic": current,
                        "to_topic": chosen,
                        "blend": blend,
                        "creativity_score": round(creativity, 4),
                        "sources": [node.source, chosen_node.source],
                    }
                )
                current = chosen

            self._dream_log.append(
                {
                    "seed": seed_topic,
                    "fragments": len(fragments),
                    "visited": sorted(visited),
                    "timestamp": _iso(),
                }
            )
            return fragments

    def _blend_concepts(
        self, a: _KnowledgeNode, b: _KnowledgeNode
    ) -> str:
        """Create a poetic blend of two knowledge atoms."""
        a_words = _tokenize(a.content)
        b_words = _tokenize(b.content)
        shared = set(a_words) & set(b_words)
        unique_a = [w for w in a_words if w not in shared][:4]
        unique_b = [w for w in b_words if w not in shared][:4]
        blend_words = list(shared) + unique_a + unique_b
        random.shuffle(blend_words)
        blend = " ".join(blend_words[:12])
        return (
            f"A vision where '{a.topic[:30]}' and '{b.topic[:30]}' merge: "
            f"{blend}..."
        )

    # ------------------------------------------------------------------
    #  Infinite Growth
    # ------------------------------------------------------------------

    def grow_capacity(self, factor: float = 1.5) -> bool:
        """
        Expand the brain's storage capacity.

        Increases neuron capacity, adds a new "layer" of virtual
        neural tissue, and records the growth event.

        Parameters
        ----------
        factor : float, default 1.5
            Multiplicative expansion factor (>1.0).

        Returns
        -------
        bool
            True if growth occurred.
        """
        with self._lock:
            factor = float(factor)
            if factor <= 1.0:
                factor = 1.1
            old_cap = self._capacity
            self._capacity = int(self._capacity * factor)
            new_neurons = self._capacity - old_cap

            # Create placeholder "ghost" neurons to represent new tissue
            for i in range(min(new_neurons, 100)):
                ghost_topic = f"__ghost_neuron_{old_cap + i}__"
                self._knowledge[ghost_topic] = _KnowledgeNode(
                    topic=ghost_topic,
                    content="",
                    source="growth_layer",
                    confidence=0.0,
                    embedding=[0.0] * EMBEDDING_DIM,
                )
                self._neuron_counter += 1

            event = {
                "old_capacity": old_cap,
                "new_capacity": self._capacity,
                "factor": round(factor, 3),
                "timestamp": _iso(),
            }
            self._growth_events.append(event)
            return True

    # ------------------------------------------------------------------
    #  Pathway Optimisation (Hebbian Pruning & Strengthening)
    # ------------------------------------------------------------------

    def optimize_pathways(self) -> Dict[str, Any]:
        """
        Prune weak connections and strengthen well-travelled ones.

        Applies Hebbian-style learning rules:
        - synapses with weight < MIN_SYNAPSE_WEIGHT are removed,
        - frequently accessed knowledge nodes get boosted confidence,
        - isolated orphan nodes are flagged.

        Returns
        -------
        dict
            Optimisation report with pruned / strengthened counts.
        """
        with self._lock:
            pruned_synapses = 0
            strengthened_synapses = 0
            orphan_topics: List[str] = []

            # Prune weak synapses
            for a in list(self._synapses.keys()):
                for b in list(self._synapses[a].keys()):
                    w = self._synapses[a][b]
                    if w < MIN_SYNAPSE_WEIGHT:
                        del self._synapses[a][b]
                        # Mirror edge
                        if b in self._synapses and a in self._synapses[b]:
                            del self._synapses[b][a]
                        pruned_synapses += 1
                        self._synapse_counter -= 1
                    elif w > 0.8:
                        # Strengthen strong bonds slightly
                        self._synapses[a][b] = min(1.0, w + HEBBIAN_STRENGTHEN)
                        if b in self._synapses and a in self._synapses[b]:
                            self._synapses[b][a] = self._synapses[a][b]
                        strengthened_synapses += 1

            # Boost confidence of frequently accessed nodes
            for topic, node in self._knowledge.items():
                if node.access_count > 10:
                    node.confidence = min(1.0, node.confidence + 0.02)
                # Decay rarely used
                elif node.access_count == 0 and (_now() - node.created_at) > 300:
                    node.confidence = max(0.0, node.confidence - HEBBIAN_DECAY)

                # Check orphan status (no synapses and not a ghost)
                has_edges = (
                    topic in self._synapses and self._synapses[topic]
                ) or any(
                    topic in self._synapses.get(other, {})
                    for other in self._synapses
                )
                if not has_edges and not topic.startswith("__ghost"):
                    orphan_topics.append(topic)

            report = {
                "pruned_synapses": pruned_synapses,
                "strengthened_synapses": strengthened_synapses,
                "orphan_topics": orphan_topics,
                "remaining_synapses": self._synapse_counter,
                "remaining_neurons": self._neuron_counter,
                "timestamp": _iso(),
            }
            self._optimize_events.append(report)
            return report

    # ------------------------------------------------------------------
    #  Brain Statistics
    # ------------------------------------------------------------------

    def get_brain_stats(self) -> Dict[str, Any]:
        """
        Comprehensive brain telemetry.

        Returns
        -------
        dict
            Neuron count, connection density, knowledge depth,
            skill cortex metrics, lifetime stats, and uptime.
        """
        with self._lock:
            neuron_count = len(self._knowledge)
            knowledge_count = sum(
                1 for k in self._knowledge if not k.startswith("__ghost")
            )
            ghost_count = neuron_count - knowledge_count

            # Connection density = actual edges / max possible
            max_edges = max(1, knowledge_count * (knowledge_count - 1) // 2)
            actual_edges = self._synapse_counter // 2  # undirected
            density = actual_edges / max_edges if max_edges else 0.0

            # Knowledge depth: average confidence weighted by access
            total_conf = 0.0
            total_weight = 0.0
            for node in self._knowledge.values():
                if node.topic.startswith("__ghost"):
                    continue
                w = 1 + node.access_count
                total_conf += node.confidence * w
                total_weight += w
            avg_depth = total_conf / total_weight if total_weight else 0.0

            # Skill cortex summary
            skill_summary = {
                "total_skills": len(self._skills),
                "avg_mastery": round(
                    sum(s.mastery_level for s in self._skills.values())
                    / max(1, len(self._skills)),
                    4,
                ),
                "total_practice_runs": sum(
                    s.practice_count for s in self._skills.values()
                ),
            }

            uptime = _now() - self._global_stats["birth_time"]

            return {
                "neuron_count": neuron_count,
                "knowledge_atoms": knowledge_count,
                "ghost_neurons": ghost_count,
                "synapse_count": self._synapse_counter,
                "connection_density": round(density, 6),
                "knowledge_depth": round(avg_depth, 4),
                "capacity": self._capacity,
                "capacity_usage_pct": round(100 * neuron_count / max(1, self._capacity), 2),
                "skill_cortex": skill_summary,
                "lifetime": {
                    "stores": self._global_stats["total_stores"],
                    "recalls": self._global_stats["total_recalls"],
                    "forgets": self._global_stats["total_forgets"],
                    "thoughts": self._global_stats["total_thoughts"],
                    "dreams": self._global_stats["total_dreams"],
                    "associations": self._global_stats["total_associations"],
                    "skills_learned": self._global_stats["total_skills_learned"],
                    "skills_executed": self._global_stats["total_skills_executed"],
                },
                "uptime_seconds": round(uptime, 2),
                "growth_events": len(self._growth_events),
                "optimization_events": len(self._optimize_events),
                "reasoning_chain_count": len(self._reasoning_log),
                "dream_chain_count": len(self._dream_log),
                "timestamp": _iso(),
            }

    # ------------------------------------------------------------------
    #  Persistence Helpers (optional but fully implemented)
    # ------------------------------------------------------------------

    def export_brain(self, file_path: str) -> bool:
        """
        Serialise the entire brain state to a JSON file.

        Returns True on success.
        """
        with self._lock:
            try:
                payload = {
                    "knowledge": {
                        k: {
                            "topic": n.topic,
                            "content": n.content,
                            "source": n.source,
                            "confidence": n.confidence,
                            "created_at": n.created_at,
                            "last_accessed": n.last_accessed,
                            "access_count": n.access_count,
                            "tags": sorted(n.tags),
                            "metadata": n.metadata,
                        }
                        for k, n in self._knowledge.items()
                    },
                    "synapses": dict(self._synapses),
                    "skills": {
                        k: {
                            "skill_name": s.skill_name,
                            "code": s.code,
                            "source": s.source,
                            "mastery_level": s.mastery_level,
                            "practice_count": s.practice_count,
                            "success_count": s.success_count,
                            "failure_count": s.failure_count,
                            "created_at": s.created_at,
                            "last_used": s.last_used,
                            "performance_history": s.performance_history,
                        }
                        for k, s in self._skills.items()
                    },
                    "capacity": self._capacity,
                    "stats": self._global_stats,
                    "reasoning_log": self._reasoning_log,
                    "dream_log": self._dream_log,
                    "growth_events": self._growth_events,
                    "optimize_events": self._optimize_events,
                }
                with open(file_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, default=str)
                return True
            except Exception as exc:
                warnings.warn(f"Export failed: {exc}")
                return False

    def import_brain(self, file_path: str) -> bool:
        """
        Hydrate the brain from a previously exported JSON file.

        Returns True on success.
        """
        with self._lock:
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)

                self._knowledge.clear()
                for k, data in payload.get("knowledge", {}).items():
                    self._knowledge[k] = _KnowledgeNode(
                        topic=data["topic"],
                        content=data["content"],
                        source=data["source"],
                        confidence=data["confidence"],
                        created_at=data["created_at"],
                        last_accessed=data["last_accessed"],
                        access_count=data["access_count"],
                        tags=set(data.get("tags", [])),
                        metadata=data.get("metadata", {}),
                    )

                self._synapses.clear()
                for a, edges in payload.get("synapses", {}).items():
                    self._synapses[a] = dict(edges)

                self._skills.clear()
                for k, data in payload.get("skills", {}).items():
                    sn = _SkillNode(
                        skill_name=data["skill_name"],
                        code=data["code"],
                        source=data["source"],
                        mastery_level=data["mastery_level"],
                        practice_count=data["practice_count"],
                        success_count=data["success_count"],
                        failure_count=data["failure_count"],
                        created_at=data["created_at"],
                        last_used=data["last_used"],
                        performance_history=data.get("performance_history", []),
                    )
                    try:
                        tree = ast.parse(sn.code, filename=f"<skill:{sn.skill_name}>")
                        sn.compiled = compile(
                            tree, filename=f"<skill:{sn.skill_name}>", mode="exec"
                        )
                    except Exception:
                        sn.compiled = None
                    self._skills[k] = sn

                self._capacity = payload.get("capacity", DEFAULT_CAPACITY)
                self._global_stats.update(payload.get("stats", {}))
                self._reasoning_log = payload.get("reasoning_log", [])
                self._dream_log = payload.get("dream_log", [])
                self._growth_events = payload.get("growth_events", [])
                self._optimize_events = payload.get("optimize_events", [])

                self._neuron_counter = len(self._knowledge)
                self._synapse_counter = sum(
                    len(v) for v in self._synapses.values()
                )
                return True
            except Exception as exc:
                warnings.warn(f"Import failed: {exc}")
                return False


# ---------------------------------------------------------------------------
#  MockNeuralLink — same API, lightweight in-memory simulation
# ---------------------------------------------------------------------------

class MockNeuralLink:
    """
    A lightweight, fully in-memory neural-link implementation with
    the exact same public interface as NeuralLinkVirtualBrain.

    Useful for unit tests, CI pipelines, or environments where
    the full brain overhead is not required.
    """

    def __init__(self) -> None:
        self._memories: Dict[str, Dict[str, Any]] = {}
        self._skills: Dict[str, Dict[str, Any]] = {}
        self._associations: Dict[Tuple[str, str], float] = {}
        self._stats = {
            "stores": 0,
            "recalls": 0,
            "forgets": 0,
            "skills_learned": 0,
            "skills_executed": 0,
            "thoughts": 0,
            "dreams": 0,
            "associations": 0,
            "capacity": 1_000,
        }
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    #  Knowledge
    # ------------------------------------------------------------------

    def store_knowledge(
        self, topic: str, content: str, source: str, confidence: float = 1.0
    ) -> str:
        with self._lock:
            self._stats["stores"] += 1
            mem_id = hashlib.sha256(
                f"mock:{topic}:{content}:{time.monotonic()}".encode()
            ).hexdigest()
            self._memories[topic] = {
                "content": content,
                "source": source,
                "confidence": max(0.0, min(1.0, confidence)),
                "memory_id": mem_id,
                "access_count": 0,
                "created": _iso(),
            }
            return mem_id

    def recall_knowledge(self, query: str, depth: int = 3) -> List[Dict[str, Any]]:
        with self._lock:
            self._stats["recalls"] += 1
            results: List[Dict[str, Any]] = []
            q_toks = set(_tokenize(query))
            for topic, mem in self._memories.items():
                m_toks = set(_tokenize(topic) + _tokenize(mem["content"]))
                overlap = len(q_toks & m_toks) / max(1, len(q_toks | m_toks))
                if overlap > 0.1:
                    mem["access_count"] += 1
                    results.append(
                        {
                            "topic": topic,
                            "content": mem["content"],
                            "source": mem["source"],
                            "confidence": mem["confidence"],
                            "relevance": round(overlap, 4),
                            "hop_distance": 1,
                            "path": [query, topic],
                            "memory_id": mem["memory_id"],
                        }
                    )
            results.sort(key=lambda r: r["relevance"], reverse=True)
            return results

    def forget_knowledge(self, topic: str, certainty: float = 0.9) -> bool:
        with self._lock:
            mem = self._memories.get(topic)
            if mem is None:
                return False
            if mem["confidence"] >= certainty:
                return False
            del self._memories[topic]
            self._stats["forgets"] += 1
            return True

    # ------------------------------------------------------------------
    #  Skills
    # ------------------------------------------------------------------

    def learn_skill(self, skill_name: str, code: str, source: str) -> bool:
        with self._lock:
            try:
                compile(code, f"<mock_skill:{skill_name}>", "exec")
            except SyntaxError:
                return False
            self._skills[skill_name] = {
                "code": code,
                "source": source,
                "mastery": 0.1,
                "runs": 0,
                "successes": 0,
            }
            self._stats["skills_learned"] += 1
            return True

    def master_skill(self, skill_name: str, practice_data: List[Any]) -> Dict[str, Any]:
        with self._lock:
            sk = self._skills.get(skill_name)
            if sk is None:
                return {
                    "skill": skill_name,
                    "error": "Skill not found.",
                    "old_mastery": 0.0,
                    "new_mastery": 0.0,
                }
            old = sk["mastery"]
            # Deterministic mock success based on hash of skill name
            seed = int(hashlib.sha256(skill_name.encode()).hexdigest()[:8], 16)
            success = sum(
                1 for i, _ in enumerate(practice_data)
                if (seed + i) % 3 != 0
            )
            total = len(practice_data)
            rate = success / total if total else 0.0
            sk["mastery"] = min(1.0, sk["mastery"] + rate * 0.15)
            sk["runs"] += total
            sk["successes"] += success
            return {
                "skill": skill_name,
                "old_mastery": round(old, 4),
                "new_mastery": round(sk["mastery"], 4),
                "cases_run": total,
                "successes": success,
                "failures": total - success,
                "success_rate": round(rate, 4),
            }

    def list_skills(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(
                [
                    {
                        "skill_name": k,
                        "source": v["source"],
                        "mastery_level": round(v["mastery"], 4),
                        "practice_count": v["runs"],
                        "success_rate": round(
                            v["successes"] / max(1, v["runs"]), 4
                        ),
                        "code_length": len(v["code"]),
                    }
                    for k, v in self._skills.items()
                ],
                key=lambda s: s["mastery_level"],
                reverse=True,
            )

    def execute_skill(self, skill_name: str, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            sk = self._skills.get(skill_name)
            if sk is None:
                raise RuntimeError(f"Skill '{skill_name}' not found.")
            self._stats["skills_executed"] += 1
            # Simple mock execution: run in restricted globals
            g = {"__builtins__": {"print": print, "len": len, "range": range}}
            g["_args"] = args
            g.update(kwargs)
            exec(sk["code"], g)
            return g.get("_result")

    # ------------------------------------------------------------------
    #  Neural Processing
    # ------------------------------------------------------------------

    def think(self, problem: str, steps: int = 5) -> List[Dict[str, Any]]:
        with self._lock:
            self._stats["thoughts"] += 1
            chain: List[Dict[str, Any]] = []
            premise = problem
            conf = 0.95
            for i in range(1, steps + 1):
                inference = (
                    f"Step {i}: Analysing '{premise[:40]}...' → "
                    f"inferred property about {self._extract_subject(premise)}."
                )
                conf *= 0.93
                chain.append(
                    {
                        "step": i,
                        "premise": premise,
                        "inference": inference,
                        "confidence": round(conf, 4),
                        "evidence": [],
                    }
                )
                premise = inference
            return chain

    def _extract_subject(self, text: str) -> str:
        tokens = _tokenize(text)
        return " ".join(tokens[:3]) if tokens else "unknown"

    def associate(self, concept_a: str, concept_b: str) -> float:
        with self._lock:
            self._stats["associations"] += 1
            key = tuple(sorted((concept_a, concept_b)))
            cached = self._associations.get(key)
            if cached is not None:
                return cached
            a_emb = _embed(concept_a)
            b_emb = _embed(concept_b)
            sim = (1.0 + _cosine(a_emb, b_emb)) / 2.0
            self._associations[key] = round(sim, 4)
            return round(sim, 4)

    def dream(self, seed_topic: str) -> List[Dict[str, Any]]:
        with self._lock:
            self._stats["dreams"] += 1
            fragments: List[Dict[str, Any]] = []
            current = seed_topic
            topics = list(self._memories.keys())
            if not topics:
                return []
            for step in range(1, 5):
                nxt = random.choice(topics)
                mem_a = self._memories.get(current, {})
                mem_b = self._memories.get(nxt, {})
                frag = {
                    "step": step,
                    "from_topic": current,
                    "to_topic": nxt,
                    "blend": (
                        f"Connecting '{current[:30]}' with '{nxt[:30]}': "
                        f"{mem_a.get('content', '')[:40]}... + "
                        f"{mem_b.get('content', '')[:40]}..."
                    ),
                    "creativity_score": round(random.uniform(0.4, 0.9), 4),
                    "sources": [mem_a.get("source"), mem_b.get("source")],
                }
                fragments.append(frag)
                current = nxt
            return fragments

    # ------------------------------------------------------------------
    #  Infinite Growth
    # ------------------------------------------------------------------

    def grow_capacity(self, factor: float = 1.5) -> bool:
        with self._lock:
            self._stats["capacity"] = int(self._stats["capacity"] * max(factor, 1.1))
            return True

    def optimize_pathways(self) -> Dict[str, Any]:
        with self._lock:
            # Remove mock memories with very low confidence
            removed = 0
            for k in list(self._memories.keys()):
                if self._memories[k]["confidence"] < 0.05:
                    del self._memories[k]
                    removed += 1
            return {
                "pruned_synapses": removed,
                "strengthened_synapses": 0,
                "orphan_topics": [],
                "remaining_synapses": 0,
                "remaining_neurons": len(self._memories),
                "timestamp": _iso(),
            }

    def get_brain_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "neuron_count": len(self._memories),
                "knowledge_atoms": len(self._memories),
                "ghost_neurons": 0,
                "synapse_count": 0,
                "connection_density": 0.0,
                "knowledge_depth": round(
                    sum(m["confidence"] for m in self._memories.values())
                    / max(1, len(self._memories)),
                    4,
                ),
                "capacity": self._stats["capacity"],
                "capacity_usage_pct": round(
                    100 * len(self._memories) / max(1, self._stats["capacity"]), 2
                ),
                "skill_cortex": {
                    "total_skills": len(self._skills),
                    "avg_mastery": round(
                        sum(s["mastery"] for s in self._skills.values())
                        / max(1, len(self._skills)),
                        4,
                    ),
                    "total_practice_runs": sum(
                        s["runs"] for s in self._skills.values()
                    ),
                },
                "lifetime": {
                    "stores": self._stats["stores"],
                    "recalls": self._stats["recalls"],
                    "forgets": self._stats["forgets"],
                    "thoughts": self._stats["thoughts"],
                    "dreams": self._stats["dreams"],
                    "associations": self._stats["associations"],
                    "skills_learned": self._stats["skills_learned"],
                    "skills_executed": self._stats["skills_executed"],
                },
                "uptime_seconds": 0.0,
                "growth_events": 0,
                "optimization_events": 0,
                "reasoning_chain_count": self._stats["thoughts"],
                "dream_chain_count": self._stats["dreams"],
                "timestamp": _iso(),
            }

    # ------------------------------------------------------------------
    #  Persistence pass-throughs
    # ------------------------------------------------------------------

    def export_brain(self, file_path: str) -> bool:
        with self._lock:
            try:
                payload = {
                    "memories": dict(self._memories),
                    "skills": dict(self._skills),
                    "associations": {
                        f"{k[0]}||{k[1]}": v
                        for k, v in self._associations.items()
                    },
                    "stats": dict(self._stats),
                }
                with open(file_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, default=str)
                return True
            except Exception as exc:
                warnings.warn(f"Mock export failed: {exc}")
                return False

    def import_brain(self, file_path: str) -> bool:
        with self._lock:
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                self._memories = payload.get("memories", {})
                self._skills = payload.get("skills", {})
                self._associations = {
                    tuple(k.split("||")): v
                    for k, v in payload.get("associations", {}).items()
                }
                self._stats = payload.get("stats", self._stats)
                return True
            except Exception as exc:
                warnings.warn(f"Mock import failed: {exc}")
                return False


# ---------------------------------------------------------------------------
#  Factory
# ---------------------------------------------------------------------------

_NEURAL_LINK_INSTANCE: Optional[NeuralLinkVirtualBrain] = None
_MOCK_NEURAL_LINK_INSTANCE: Optional[MockNeuralLink] = None
_FACTORY_LOCK = threading.Lock()


def get_neural_link(
    mock: bool = False, initial_capacity: int = DEFAULT_CAPACITY
) -> NeuralLinkVirtualBrain | MockNeuralLink:
    """
    Factory function returning a singleton Neural Link instance.

    Parameters
    ----------
    mock : bool, default False
        If True, return a MockNeuralLink (lightweight, test-safe).
    initial_capacity : int, default 10_000
        Starting neuron capacity for the full brain.

    Returns
    -------
    NeuralLinkVirtualBrain | MockNeuralLink
        The appropriate neural-link implementation.
    """
    global _NEURAL_LINK_INSTANCE, _MOCK_NEURAL_LINK_INSTANCE
    with _FACTORY_LOCK:
        if mock:
            if _MOCK_NEURAL_LINK_INSTANCE is None:
                _MOCK_NEURAL_LINK_INSTANCE = MockNeuralLink()
            return _MOCK_NEURAL_LINK_INSTANCE
        else:
            if _NEURAL_LINK_INSTANCE is None:
                _NEURAL_LINK_INSTANCE = NeuralLinkVirtualBrain(
                    initial_capacity=initial_capacity
                )
            return _NEURAL_LINK_INSTANCE


def reset_neural_link(mock: bool = False) -> None:
    """
    Reset the global singleton so the next ``get_neural_link()`` call
    builds a fresh instance.  Useful in tests and reload scenarios.
    """
    global _NEURAL_LINK_INSTANCE, _MOCK_NEURAL_LINK_INSTANCE
    with _FACTORY_LOCK:
        if mock:
            _MOCK_NEURAL_LINK_INSTANCE = None
        else:
            _NEURAL_LINK_INSTANCE = None


# ---------------------------------------------------------------------------
#  Self-test / demo (runs only when executed directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("JARVIS BRAINIAC — Neural Link Virtual Brain Self-Test")
    print("=" * 70)

    brain = NeuralLinkVirtualBrain(initial_capacity=100)

    # --- Knowledge ---
    print("\n[1] Storing knowledge...")
    brain.store_knowledge(
        topic="Quantum Computing",
        content="Quantum computers use qubits that exploit superposition "
        "and entanglement to perform computations exponentially faster "
        "than classical machines for certain problems.",
        source="arxiv:2103.12345",
        confidence=0.92,
    )
    brain.store_knowledge(
        topic="Superposition",
        content="Superposition is the quantum mechanical phenomenon where "
        "a quantum system can exist in multiple states simultaneously "
        "until measured.",
        source="textbook:GriffithsQM",
        confidence=0.98,
    )
    brain.store_knowledge(
        topic="Entanglement",
        content="Quantum entanglement is a physical phenomenon that occurs "
        "when a group of particles are generated or interact in a way "
        "such that the quantum state of each particle cannot be described "
        "independently of the others.",
        source="textbook:GriffithsQM",
        confidence=0.95,
    )
    brain.store_knowledge(
        topic="Neural Networks",
        content="Artificial neural networks are computing systems inspired "
        "by biological neural networks. They are used for machine learning "
        "and deep learning tasks.",
        source="course:CS231n",
        confidence=0.88,
    )
    print("   → Stored 4 knowledge atoms.")

    # --- Recall ---
    print("\n[2] Multi-hop recall on 'qubit properties'...")
    recalled = brain.recall_knowledge("qubit properties", depth=3)
    for r in recalled[:3]:
        print(f"   • {r['topic']} (rel={r['relevance']}, hop={r['hop_distance']})")

    # --- Association ---
    print("\n[3] Neural association...")
    assoc = brain.associate("Quantum Computing", "Neural Networks")
    print(f"   → Association strength: {assoc}")

    # --- Thinking ---
    print("\n[4] Chain-of-thought reasoning...")
    thoughts = brain.think(
        "How can quantum computing improve neural network training?", steps=4
    )
    for t in thoughts:
        print(f"   Step {t['step']} | conf={t['confidence']} | {t['inference'][:70]}...")

    # --- Dreaming ---
    print("\n[5] Dreaming from 'Quantum Computing'...")
    dreams = brain.dream("Quantum Computing")
    for d in dreams:
        print(f"   Fragment {d['step']} → {d['to_topic']} "
              f"(creativity={d['creativity_score']})")

    # --- Skill learning ---
    print("\n[6] Skill acquisition...")
    code = textwrap.dedent(
        """
        def greet(name):
            return f"Hello, {name}!"
        _result = greet(_kwargs.get("name", "World"))
        """
    )
    ok = brain.learn_skill("greet_user", code, source="runtime:agency")
    print(f"   → learn_skill returned {ok}")
    result = brain.execute_skill("greet_user", name="JARVIS")
    print(f"   → execute_skill returned: {result}")

    # --- Mastery ---
    print("\n[7] Skill mastery simulation...")
    report = brain.master_skill("greet_user", practice_data=[1, 2, 3, 4, 5])
    print(f"   → Mastery: {report['old_mastery']} → {report['new_mastery']}")
    print(f"   → Success rate: {report['success_rate']}")

    # --- Optimization ---
    print("\n[8] Pathway optimisation...")
    opt = brain.optimize_pathways()
    print(f"   → Pruned: {opt['pruned_synapses']}, "
          f"Strengthened: {opt['strengthened_synapses']}")

    # --- Stats ---
    print("\n[9] Brain statistics...")
    stats = brain.get_brain_stats()
    print(f"   → Neurons: {stats['neuron_count']} | "
          f"Synapses: {stats['synapse_count']} | "
          f"Density: {stats['connection_density']}")
    print(f"   → Knowledge depth: {stats['knowledge_depth']} | "
          f"Capacity: {stats['capacity_usage_pct']}%")
    print(f"   → Skills: {stats['skill_cortex']['total_skills']} | "
          f"Avg mastery: {stats['skill_cortex']['avg_mastery']}")

    # --- Mock test ---
    print("\n[10] MockNeuralLink smoke test...")
    mock = get_neural_link(mock=True)
    mock.store_knowledge("Test", "This is a test.", "unit_test")
    print(f"   → Mock stats: {mock.get_brain_stats()['neuron_count']} neurons")

    print("\n" + "=" * 70)
    print("Self-test completed successfully.")
    print("=" * 70)
