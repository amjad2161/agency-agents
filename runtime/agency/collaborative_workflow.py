"""
collaborative_workflow.py — Multi-Agent Collaborative Workflow System

Enables multiple expert agents to work together on complex tasks through
message passing, shared context, consensus building, and conflict resolution.

Includes:
    - AgentMessage: typed message envelope for agent-to-agent communication
    - CollaborationSession: manages a live multi-agent collaboration
    - CollaborationWorkflow: pre-defined workflow patterns (peer review,
      brainstorm, debate, sequential, parallel)
    - MockCollaborationSession: deterministic, in-memory test double
    - get_collaboration_session(): factory for creating sessions
"""

from __future__ import annotations

import copy
import datetime
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants & Enums
# ---------------------------------------------------------------------------

VALID_MSG_TYPES: Tuple[str, ...] = (
    "question", "answer", "proposal", "feedback", "consensus", "conflict"
)

VALID_ROLES: Tuple[str, ...] = ("lead", "contributor", "reviewer", "decider")


class WorkflowType(str, Enum):
    """Enumeration of built-in workflow patterns."""
    PEER_REVIEW = "peer_review"
    BRAINSTORM = "brainstorm"
    DEBATE = "debate"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class ConflictResolutionStrategy(str, Enum):
    """Strategies for resolving agent conflicts."""
    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_VOTE = "weighted_vote"
    LEAD_DECIDES = "lead_decides"
    COMPROMISE = "compromise"


# ---------------------------------------------------------------------------
# AgentMessage
# ---------------------------------------------------------------------------

@dataclass
class AgentMessage:
    """
    A single message exchanged between agents in a collaboration session.

    Attributes:
        msg_id:       Unique identifier for the message (UUID4).
        from_agent:   ID of the sending agent.
        to_agent:     ID of the target agent, or "all" for broadcast.
        content:      Human-readable message body.
        msg_type:     One of question|answer|proposal|feedback|consensus|conflict.
        timestamp:    ISO-8601 timestamp when the message was created.
        context:      Optional dictionary with extra metadata / structured data.
    """
    msg_id: str
    from_agent: str
    to_agent: str
    content: str
    msg_type: str
    timestamp: str
    context: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Validate fields after construction."""
        if not self.msg_id:
            raise ValueError("msg_id cannot be empty")
        if not self.from_agent:
            raise ValueError("from_agent cannot be empty")
        if not self.to_agent:
            raise ValueError("to_agent cannot be empty")
        if self.msg_type not in VALID_MSG_TYPES:
            raise ValueError(
                f"Invalid msg_type '{self.msg_type}'. "
                f"Must be one of: {VALID_MSG_TYPES}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """Deserialise from a plain dictionary."""
        return cls(
            msg_id=data.get("msg_id", str(uuid.uuid4())),
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            content=data["content"],
            msg_type=data["msg_type"],
            timestamp=data.get("timestamp", _now_iso()),
            context=data.get("context"),
        )

    def is_broadcast(self) -> bool:
        """Return True if the message is addressed to all agents."""
        return self.to_agent.lower() == "all"

    def summary(self) -> str:
        """Return a one-line summary of the message."""
        target = "all" if self.is_broadcast() else self.to_agent
        return (
            f"[{self.msg_type.upper()}] {self.from_agent} -> {target}: "
            f"{self.content[:80]}{'...' if len(self.content) > 80 else ''}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def _new_uuid() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


def _default_transcript_dir() -> str:
    """Return the default directory for saved transcripts."""
    base = os.environ.get("JARVIS_TRANSCRIPT_DIR", "/mnt/agents/output/jarvis/data/transcripts")
    os.makedirs(base, exist_ok=True)
    return base


# ---------------------------------------------------------------------------
# CollaborationSession
# ---------------------------------------------------------------------------

class CollaborationSession:
    """
    Manages a multi-agent collaboration session.

    Agents communicate via typed messages, share a common context dictionary,
    build consensus through voting, and resolve conflicts via configurable
    resolution strategies.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, session_id: str = None, topic: str = "") -> None:
        self.session_id: str = session_id or _new_uuid()
        self.topic: str = topic
        self.created_at: str = _now_iso()
        self.closed_at: Optional[str] = None

        # Agent registry: agent_id -> {"persona_type": str, "role": str, "joined_at": str}
        self.agents: Dict[str, Dict[str, Any]] = {}

        # Chronological message log
        self.messages: List[AgentMessage] = []

        # Shared key-value store visible to every agent
        self.shared_context: Dict[str, Any] = {}

        # Consensus records: topic -> result dict
        self.consensus_history: Dict[str, Dict[str, Any]] = {}

        # Conflict resolution records: topic -> result dict
        self.conflict_history: Dict[str, Dict[str, Any]] = {}

        # Vote registry for consensus topics
        self._votes: Dict[str, Dict[str, str]] = {}

        # Running flag
        self._active: bool = True

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    def add_agent(self, agent_id: str, persona_type: str, role: str) -> None:
        """
        Register a new expert agent in the session.

        Args:
            agent_id:      Unique identifier for the agent.
            persona_type:  The agent's persona / expertise domain.
            role:          One of 'lead', 'contributor', 'reviewer', 'decider'.
        """
        if not self._active:
            raise RuntimeError("Session is closed; cannot add agents.")
        if agent_id in self.agents:
            raise ValueError(f"Agent '{agent_id}' is already in the session.")
        if role not in VALID_ROLES:
            raise ValueError(
                f"Invalid role '{role}'. Must be one of: {VALID_ROLES}"
            )

        self.agents[agent_id] = {
            "persona_type": persona_type,
            "role": role,
            "joined_at": _now_iso(),
        }

        # Auto-announce membership via a system-style message
        self.send_message(
            from_agent="system",
            content=f"Agent '{agent_id}' ({persona_type}) has joined as {role}.",
            to_agent="all",
            msg_type="feedback",
        )

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from the session."""
        if agent_id not in self.agents:
            raise KeyError(f"Agent '{agent_id}' not found in session.")
        del self.agents[agent_id]
        self.send_message(
            from_agent="system",
            content=f"Agent '{agent_id}' has left the session.",
            to_agent="all",
            msg_type="feedback",
        )

    def list_agents(self) -> List[str]:
        """Return a list of all registered agent IDs."""
        return list(self.agents.keys())

    def get_agent_info(self, agent_id: str) -> Dict[str, Any]:
        """Return metadata for a specific agent."""
        if agent_id not in self.agents:
            raise KeyError(f"Agent '{agent_id}' not found.")
        return copy.deepcopy(self.agents[agent_id])

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(
        self,
        from_agent: str,
        content: str,
        to_agent: str = "all",
        msg_type: str = "proposal",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send a message from one agent to another (or broadcast).

        Args:
            from_agent: ID of the sender.
            content:    Message body text.
            to_agent:   Recipient ID, or "all" for broadcast.
            msg_type:   Message classification.
            context:    Optional extra metadata.

        Returns:
            The generated message ID (UUID4).
        """
        if not self._active:
            raise RuntimeError("Session is closed; cannot send messages.")

        # Validate sender (allow "system" pseudo-agent)
        if from_agent != "system" and from_agent not in self.agents:
            raise ValueError(f"Sender '{from_agent}' is not in the session.")

        # Validate recipient unless broadcast
        if to_agent.lower() != "all" and to_agent not in self.agents:
            raise ValueError(f"Recipient '{to_agent}' is not in the session.")

        if msg_type not in VALID_MSG_TYPES:
            raise ValueError(
                f"Invalid msg_type '{msg_type}'. Must be one of: {VALID_MSG_TYPES}"
            )

        msg = AgentMessage(
            msg_id=_new_uuid(),
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            msg_type=msg_type,
            timestamp=_now_iso(),
            context=context,
        )
        self.messages.append(msg)
        return msg.msg_id

    def broadcast(
        self,
        from_agent: str,
        content: str,
        msg_type: str = "proposal",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Convenience method: broadcast a message to every agent.

        Returns the message ID.
        """
        return self.send_message(
            from_agent=from_agent,
            content=content,
            to_agent="all",
            msg_type=msg_type,
            context=context,
        )

    def reply_to(
        self,
        original_msg_id: str,
        from_agent: str,
        content: str,
        msg_type: str = "answer",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send a direct reply referencing an earlier message.

        The original message ID is injected into *context* under the key
        *in_reply_to*.
        """
        enriched_context = dict(context) if context else {}
        enriched_context["in_reply_to"] = original_msg_id
        return self.send_message(
            from_agent=from_agent,
            content=content,
            to_agent="all",
            msg_type=msg_type,
            context=enriched_context,
        )

    # ------------------------------------------------------------------
    # Conversation queries
    # ------------------------------------------------------------------

    def get_conversation(self, agent_filter: Optional[str] = None) -> List[AgentMessage]:
        """
        Retrieve all messages in chronological order.

        Args:
            agent_filter: If provided, only return messages where this agent
                          is either the sender or the explicit recipient.

        Returns:
            A (possibly filtered) list of AgentMessage objects.
        """
        if agent_filter is None:
            return list(self.messages)

        return [
            m for m in self.messages
            if m.from_agent == agent_filter or m.to_agent == agent_filter
        ]

    def get_messages_by_type(self, msg_type: str) -> List[AgentMessage]:
        """Return all messages of a given msg_type."""
        return [m for m in self.messages if m.msg_type == msg_type]

    def get_last_message(self) -> Optional[AgentMessage]:
        """Return the most recent message, or None if the log is empty."""
        return self.messages[-1] if self.messages else None

    def message_count(self) -> int:
        """Return the total number of messages exchanged."""
        return len(self.messages)

    # ------------------------------------------------------------------
    # Shared context
    # ------------------------------------------------------------------

    def share_context(self, key: str, value: Any) -> None:
        """
        Publish a key-value pair into the shared session context.

        Automatically records an audit trail in the message log.
        """
        if not self._active:
            raise RuntimeError("Session is closed; cannot share context.")
        self.shared_context[key] = value
        self.send_message(
            from_agent="system",
            content=f"Shared context updated: '{key}' = {repr(value)[:200]}",
            to_agent="all",
            msg_type="feedback",
            context={"context_key": key, "context_value": value},
        )

    def get_shared_context(self) -> Dict[str, Any]:
        """Return a deep copy of the full shared context dictionary."""
        return copy.deepcopy(self.shared_context)

    def get_context_value(self, key: str, default: Any = None) -> Any:
        """Look up a single key in the shared context."""
        return copy.deepcopy(self.shared_context.get(key, default))

    # ------------------------------------------------------------------
    # Consensus building
    # ------------------------------------------------------------------

    def build_consensus(
        self,
        topic: str,
        proposal: str = "",
        strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.MAJORITY_VOTE,
    ) -> Dict[str, Any]:
        """
        Drive the registered agents toward agreement on *topic*.

        The session inspects existing messages to infer positions, tallies
        votes, and produces a structured consensus result.

        Args:
            topic:    The subject under discussion.
            proposal: Optional explicit proposal text.
            strategy: Voting / aggregation strategy.

        Returns:
            Dictionary with keys:
                - consensus_reached (bool)
                - topic (str)
                - agreed_points (List[str])
                - disagreements (List[str])
                - vote_breakdown (Dict[str, int])
                - strategy (str)
                - timestamp (str)
        """
        if not self._active:
            raise RuntimeError("Session is closed.")

        # Initialise topic-specific vote store
        if topic not in self._votes:
            self._votes[topic] = {}

        # Derive a simple sentiment from messages that mention the topic
        sentiment = self._analyse_sentiment_on_topic(topic)

        # Tally votes from registered agents
        tally: Dict[str, int] = {"agree": 0, "disagree": 0, "abstain": 0}
        for agent_id in self.agents:
            # Use stored vote if present, otherwise infer from sentiment
            vote = self._votes[topic].get(agent_id)
            if vote is None:
                # Simple deterministic inference based on message content
                agent_msgs = [
                    m for m in self.messages
                    if m.from_agent == agent_id and topic.lower() in m.content.lower()
                ]
                if agent_msgs:
                    text = " ".join(m.content.lower() for m in agent_msgs)
                    if any(w in text for w in ("agree", "support", "yes", "good idea", "approve")):
                        vote = "agree"
                    elif any(w in text for w in ("disagree", "oppose", "no", "bad idea", "reject")):
                        vote = "disagree"
                    else:
                        vote = "abstain"
                else:
                    vote = "abstain"
                self._votes[topic][agent_id] = vote
            tally[vote] = tally.get(vote, 0) + 1

        # Evaluate whether consensus is reached
        total = len(self.agents)
        if total == 0:
            result: Dict[str, Any] = {
                "consensus_reached": False,
                "topic": topic,
                "agreed_points": [],
                "disagreements": ["No agents registered"],
                "vote_breakdown": tally,
                "strategy": strategy.value,
                "timestamp": _now_iso(),
            }
            self.consensus_history[topic] = result
            return result

        agree_ratio = tally["agree"] / total
        consensus_reached = agree_ratio > 0.5

        agreed_points: List[str] = []
        disagreements: List[str] = []

        if consensus_reached:
            agreed_points.append(
                f"Majority agrees on '{topic}'"
                + (f" — proposal: {proposal}" if proposal else "")
            )
        else:
            disagreements.append(
                f"No majority agreement on '{topic}' (agree={tally['agree']}, "
                f"disagree={tally['disagree']}, abstain={tally['abstain']})"
            )

        if proposal and consensus_reached:
            agreed_points.append(f"Proposal accepted: {proposal}")
        elif proposal:
            disagreements.append(f"Proposal rejected: {proposal}")

        # Extract any explicit points mentioned in messages
        topic_msgs = [
            m for m in self.messages
            if topic.lower() in m.content.lower() and m.msg_type in ("proposal", "feedback", "consensus")
        ]
        for m in topic_msgs:
            if m.msg_type == "proposal" and consensus_reached:
                agreed_points.append(m.content)
            elif m.msg_type == "conflict":
                disagreements.append(m.content)

        result = {
            "consensus_reached": consensus_reached,
            "topic": topic,
            "agreed_points": agreed_points,
            "disagreements": disagreements,
            "vote_breakdown": tally,
            "strategy": strategy.value,
            "timestamp": _now_iso(),
        }

        self.consensus_history[topic] = result

        # Announce the outcome in the message log
        outcome = "reached" if consensus_reached else "not reached"
        self.send_message(
            from_agent="system",
            content=f"Consensus on '{topic}': {outcome}.",
            to_agent="all",
            msg_type="consensus",
            context={"consensus_result": result},
        )
        return result

    def cast_vote(self, agent_id: str, topic: str, vote: str) -> None:
        """
        Explicitly record an agent's vote on a topic.

        *vote* should be one of: 'agree', 'disagree', 'abstain'.
        """
        if agent_id not in self.agents:
            raise ValueError(f"Agent '{agent_id}' is not in the session.")
        if vote not in ("agree", "disagree", "abstain"):
            raise ValueError("Vote must be 'agree', 'disagree', or 'abstain'.")
        if topic not in self._votes:
            self._votes[topic] = {}
        self._votes[topic][agent_id] = vote
        self.send_message(
            from_agent=agent_id,
            content=f"I vote '{vote}' on '{topic}'.",
            to_agent="all",
            msg_type="feedback",
            context={"topic": topic, "vote": vote},
        )

    def _analyse_sentiment_on_topic(self, topic: str) -> Dict[str, float]:
        """
        Crude sentiment analysis of messages mentioning *topic*.

        Returns a mapping agent_id -> sentiment_score in [-1.0, 1.0].
        """
        scores: Dict[str, List[float]] = {}
        positive_words = {"agree", "support", "yes", "good", "great", "excellent", "approve"}
        negative_words = {"disagree", "oppose", "no", "bad", "poor", "terrible", "reject"}

        for m in self.messages:
            if topic.lower() not in m.content.lower():
                continue
            words = set(m.content.lower().split())
            pos = len(words & positive_words)
            neg = len(words & negative_words)
            score = (pos - neg) / max(pos + neg, 1)
            scores.setdefault(m.from_agent, []).append(score)

        return {
            agent: round(sum(vals) / len(vals), 3)
            for agent, vals in scores.items() if vals
        }

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def resolve_conflict(
        self,
        conflict_topic: str,
        strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.COMPROMISE,
    ) -> Dict[str, Any]:
        """
        Resolve an existing disagreement among agents.

        Examines previous consensus attempts, message sentiment, and
        agent roles to propose a resolution path.

        Args:
            conflict_topic: The subject of the disagreement.
            strategy:       How to resolve the conflict.

        Returns:
            Dictionary with keys:
                - resolved (bool)
                - conflict_topic (str)
                - resolution (str)
                - compromises (List[str])
                - agent_positions (Dict[str, str])
                - strategy (str)
                - timestamp (str)
        """
        if not self._active:
            raise RuntimeError("Session is closed.")

        # Gather each agent's last explicit position on the topic
        agent_positions: Dict[str, str] = {}
        for m in reversed(self.messages):
            if conflict_topic.lower() in m.content.lower():
                if m.from_agent not in agent_positions and m.from_agent != "system":
                    text = m.content.lower()
                    if any(w in text for w in ("agree", "support", "yes", "for")):
                        agent_positions[m.from_agent] = "support"
                    elif any(w in text for w in ("disagree", "oppose", "no", "against")):
                        agent_positions[m.from_agent] = "oppose"
                    else:
                        agent_positions[m.from_agent] = "neutral"

        # Fill in missing agents
        for agent_id in self.agents:
            if agent_id not in agent_positions:
                agent_positions[agent_id] = "neutral"

        # Apply resolution strategy
        compromises: List[str] = []
        resolution_text = ""
        resolved = False

        if strategy == ConflictResolutionStrategy.LEAD_DECIDES:
            leads = [
                aid for aid, info in self.agents.items()
                if info["role"] == "lead"
            ]
            if leads:
                lead = leads[0]
                lead_pos = agent_positions.get(lead, "neutral")
                resolution_text = (
                    f"Lead '{lead}' decides: position = {lead_pos}"
                )
                resolved = True
            else:
                resolution_text = "No lead agent available to decide."

        elif strategy == ConflictResolutionStrategy.MAJORITY_VOTE:
            counts: Dict[str, int] = {}
            for pos in agent_positions.values():
                counts[pos] = counts.get(pos, 0) + 1
            if counts:
                winner = max(counts, key=counts.get)
                resolution_text = f"Majority vote winner: '{winner}'"
                resolved = True
            else:
                resolution_text = "No votes to tally."

        elif strategy == ConflictResolutionStrategy.WEIGHTED_VOTE:
            weights = {"lead": 3.0, "decider": 2.5, "reviewer": 1.5, "contributor": 1.0}
            scores: Dict[str, float] = {"support": 0.0, "oppose": 0.0, "neutral": 0.0}
            for aid, pos in agent_positions.items():
                role = self.agents[aid]["role"]
                w = weights.get(role, 1.0)
                scores[pos] = scores.get(pos, 0.0) + w
            if scores:
                winner = max(scores, key=scores.get)
                resolution_text = f"Weighted vote winner: '{winner}'"
                resolved = True
            else:
                resolution_text = "No weighted votes to tally."

        elif strategy == ConflictResolutionStrategy.COMPROMISE:
            # Attempt to synthesise a middle-ground position
            supporters = [a for a, p in agent_positions.items() if p == "support"]
            opposers = [a for a, p in agent_positions.items() if p == "oppose"]
            if supporters and opposers:
                resolution_text = (
                    f"Compromise sought between {len(supporters)} supporter(s) "
                    f"and {len(opposers)} opposer(s)."
                )
                compromises.append(
                    f"Consider a phased approach to '{conflict_topic}'"
                )
                compromises.append(
                    "Schedule a follow-up review to evaluate the compromise"
                )
                resolved = True
            elif supporters:
                resolution_text = f"Unanimous support for '{conflict_topic}'."
                resolved = True
            elif opposers:
                resolution_text = f"Unanimous opposition to '{conflict_topic}'."
                resolved = True
            else:
                resolution_text = "All agents are neutral; no conflict to resolve."
                resolved = True

        result: Dict[str, Any] = {
            "resolved": resolved,
            "conflict_topic": conflict_topic,
            "resolution": resolution_text,
            "compromises": compromises,
            "agent_positions": agent_positions,
            "strategy": strategy.value,
            "timestamp": _now_iso(),
        }
        self.conflict_history[conflict_topic] = result

        self.send_message(
            from_agent="system",
            content=f"Conflict resolution on '{conflict_topic}': {resolution_text}",
            to_agent="all",
            msg_type="consensus" if resolved else "conflict",
            context={"resolution_result": result},
        )
        return result

    # ------------------------------------------------------------------
    # Summary & export
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """
        Produce a high-level summary of the collaboration session.

        Returns:
            Dictionary containing session metadata, agent roster,
            message statistics, shared context snapshot, and
            consensus / conflict tallies.
        """
        msg_type_counts: Dict[str, int] = {}
        for m in self.messages:
            msg_type_counts[m.msg_type] = msg_type_counts.get(m.msg_type, 0) + 1

        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "status": "active" if self._active else "closed",
            "created_at": self.created_at,
            "closed_at": self.closed_at,
            "agent_count": len(self.agents),
            "agents": {
                aid: {"persona_type": info["persona_type"], "role": info["role"]}
                for aid, info in self.agents.items()
            },
            "message_count": len(self.messages),
            "message_breakdown": msg_type_counts,
            "consensus_topics": list(self.consensus_history.keys()),
            "conflict_topics": list(self.conflict_history.keys()),
            "shared_context_keys": list(self.shared_context.keys()),
        }

    def export_transcript(self, fmt: str = "json") -> str:
        """
        Serialise the full conversation transcript.

        Args:
            fmt: One of 'json', 'markdown', 'txt'.

        Returns:
            The serialised transcript string.
        """
        if fmt == "json":
            payload = {
                "session_id": self.session_id,
                "topic": self.topic,
                "created_at": self.created_at,
                "agents": self.agents,
                "shared_context": self.shared_context,
                "messages": [m.to_dict() for m in self.messages],
                "consensus_history": self.consensus_history,
                "conflict_history": self.conflict_history,
            }
            return json.dumps(payload, indent=2, default=str)

        elif fmt == "markdown":
            lines: List[str] = [
                f"# Collaboration Transcript — {self.topic}",
                "",
                f"**Session ID:** `{self.session_id}`",
                f"**Created:** {self.created_at}",
                f"**Status:** {'active' if self._active else 'closed'}",
                "",
                "## Agents",
                "",
            ]
            for aid, info in self.agents.items():
                lines.append(
                    f"- **{aid}** ({info['persona_type']}) — role: {info['role']}"
                )
            lines.extend(["", "## Messages", ""])
            for m in self.messages:
                ts = m.timestamp
                target = "all" if m.is_broadcast() else m.to_agent
                lines.append(
                    f"### [{m.msg_type.upper()}] {ts}",
                )
                lines.append(f"**From:** {m.from_agent}  ")
                lines.append(f"**To:** {target}  ")
                lines.append(f"**Content:** {m.content}  ")
                if m.context:
                    lines.append(f"**Context:** `{json.dumps(m.context, default=str)}`  ")
                lines.append("")
            return "\n".join(lines)

        elif fmt == "txt":
            lines = [
                f"Collaboration Transcript — {self.topic}",
                f"Session : {self.session_id}",
                f"Created : {self.created_at}",
                f"Status  : {'active' if self._active else 'closed'}",
                "-" * 60,
            ]
            for m in self.messages:
                lines.append(m.summary())
            return "\n".join(lines)

        else:
            raise ValueError(f"Unsupported format '{fmt}'. Use 'json', 'markdown', or 'txt'.")

    def save_transcript(self, filepath: Optional[str] = None, fmt: str = "json") -> str:
        """
        Persist the transcript to disk.

        Args:
            filepath: Destination path. If None, a default path under
                      JARVIS_TRANSCRIPT_DIR is used.
            fmt:      Serialisation format.

        Returns:
            The path of the saved file.
        """
        if filepath is None:
            filename = f"{self.session_id}_{fmt}.{fmt if fmt != 'txt' else 'txt'}"
            filepath = os.path.join(_default_transcript_dir(), filename)
        transcript = self.export_transcript(fmt=fmt)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(transcript)
        return filepath

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """
        End the collaboration session.

        Marks the session as inactive, records the close timestamp,
        and persists the transcript to the default location.
        """
        if not self._active:
            return

        # Announce closure *before* flipping the active flag so that
        # send_message() is still permitted.
        self.send_message(
            from_agent="system",
            content="Session closed.",
            to_agent="all",
            msg_type="feedback",
        )
        self._active = False
        self.closed_at = _now_iso()
        try:
            path = self.save_transcript(fmt="json")
            self.shared_context["_transcript_path"] = path
        except Exception:
            pass

    def is_active(self) -> bool:
        """Return True if the session is still open."""
        return self._active

    def __repr__(self) -> str:
        return (
            f"<CollaborationSession id={self.session_id[:8]} "
            f"agents={len(self.agents)} msgs={len(self.messages)} "
            f"active={self._active}>"
        )


# ---------------------------------------------------------------------------
# CollaborationWorkflow — high-level workflow patterns
# ---------------------------------------------------------------------------

class CollaborationWorkflow:
    """
    Pre-defined collaboration workflow patterns.

    Each method creates a CollaborationSession, orchestrates agents through
    a specific pattern, and returns structured results.
    """

    # ------------------------------------------------------------------
    # 1. Peer Review
    # ------------------------------------------------------------------

    @staticmethod
    def peer_review(
        content: str,
        creator: str,
        reviewers: List[str],
        topic: str = "Peer Review",
    ) -> Dict[str, Any]:
        """
        Workflow: one agent creates content, designated reviewers provide feedback.

        Args:
            content:  The artefact / document under review.
            creator:  ID of the agent that produced the content.
            reviewers: List of reviewer agent IDs.
            topic:    Optional topic label.

        Returns:
            Dictionary with the session summary, review comments, and
            an aggregate verdict.
        """
        session = CollaborationSession(topic=topic)

        # Register creator as lead
        session.add_agent(creator, "creator", "lead")
        # Register reviewers
        for rid in reviewers:
            session.add_agent(rid, "reviewer", "reviewer")

        # Step 1 — creator submits content
        session.broadcast(
            from_agent=creator,
            content=f"Submitted for review:\n\n{content}",
            msg_type="proposal",
        )

        # Step 2 — each reviewer provides feedback
        review_comments: List[Dict[str, str]] = []
        for rid in reviewers:
            comment = f"Review by {rid}: Reviewed the submission. Looks good with minor notes."
            session.send_message(
                from_agent=rid,
                content=comment,
                to_agent=creator,
                msg_type="feedback",
            )
            review_comments.append({"reviewer": rid, "comment": comment})

        # Step 3 — creator acknowledges
        session.broadcast(
            from_agent=creator,
            content="Thank you for the reviews. I will incorporate the feedback.",
            msg_type="feedback",
        )

        # Build consensus on acceptance
        consensus = session.build_consensus(topic="Accept submission")

        return {
            "workflow": "peer_review",
            "session_id": session.session_id,
            "content": content,
            "creator": creator,
            "reviewers": reviewers,
            "review_comments": review_comments,
            "consensus": consensus,
            "transcript": session.export_transcript("json"),
        }

    # ------------------------------------------------------------------
    # 2. Brainstorm
    # ------------------------------------------------------------------

    @staticmethod
    def brainstorm(
        topic: str,
        agents: List[str],
        rounds: int = 1,
    ) -> Dict[str, Any]:
        """
        Workflow: all agents contribute ideas on a topic.

        Args:
            topic:  The brainstorming subject.
            agents: List of contributor agent IDs.
            rounds: Number of ideation rounds.

        Returns:
            Dictionary with contributed ideas and session metadata.
        """
        session = CollaborationSession(topic=f"Brainstorm: {topic}")

        for aid in agents:
            session.add_agent(aid, "brainstormer", "contributor")

        ideas: List[Dict[str, str]] = []
        for rnd in range(1, rounds + 1):
            for aid in agents:
                idea_text = f"Idea from {aid} (round {rnd}): Approach for '{topic}' using my expertise."
                session.broadcast(
                    from_agent=aid,
                    content=idea_text,
                    msg_type="proposal",
                )
                ideas.append({
                    "agent": aid,
                    "round": rnd,
                    "idea": idea_text,
                })

        # Quick consensus on whether to proceed with any idea
        consensus = session.build_consensus(topic=f"Proceed with ideas on {topic}")

        return {
            "workflow": "brainstorm",
            "session_id": session.session_id,
            "topic": topic,
            "rounds": rounds,
            "agent_count": len(agents),
            "ideas": ideas,
            "consensus": consensus,
            "transcript": session.export_transcript("json"),
        }

    # ------------------------------------------------------------------
    # 3. Debate
    # ------------------------------------------------------------------

    @staticmethod
    def debate(
        topic: str,
        pro_agents: List[str],
        con_agents: List[str],
        rounds: int = 2,
    ) -> Dict[str, Any]:
        """
        Workflow: agents argue for (pro) and against (con) a topic.

        Args:
            topic:      The subject of debate.
            pro_agents: Agent IDs arguing in favour.
            con_agents: Agent IDs arguing against.
            rounds:     Number of exchange rounds.

        Returns:
            Dictionary with arguments from both sides and a resolution summary.
        """
        session = CollaborationSession(topic=f"Debate: {topic}")

        for aid in pro_agents:
            session.add_agent(aid, "debater", "contributor")
        for aid in con_agents:
            session.add_agent(aid, "debater", "contributor")

        pro_args: List[Dict[str, str]] = []
        con_args: List[Dict[str, str]] = []

        for rnd in range(1, rounds + 1):
            # Pro side speaks
            for aid in pro_agents:
                arg = f"PRO argument (round {rnd}) from {aid}: Strong reasons to support '{topic}'."
                session.broadcast(from_agent=aid, content=arg, msg_type="proposal")
                pro_args.append({"agent": aid, "round": rnd, "argument": arg})

            # Con side speaks
            for aid in con_agents:
                arg = f"CON argument (round {rnd}) from {aid}: Important concerns about '{topic}'."
                session.broadcast(from_agent=aid, content=arg, msg_type="conflict")
                con_args.append({"agent": aid, "round": rnd, "argument": arg})

        # Attempt resolution via compromise
        resolution = session.resolve_conflict(
            conflict_topic=topic,
            strategy=ConflictResolutionStrategy.COMPROMISE,
        )

        return {
            "workflow": "debate",
            "session_id": session.session_id,
            "topic": topic,
            "rounds": rounds,
            "pro_agents": pro_agents,
            "con_agents": con_agents,
            "pro_arguments": pro_args,
            "con_arguments": con_args,
            "resolution": resolution,
            "transcript": session.export_transcript("json"),
        }

    # ------------------------------------------------------------------
    # 4. Sequential (handoff)
    # ------------------------------------------------------------------

    @staticmethod
    def sequential(
        tasks: List[str],
        agents: List[str],
        topic: str = "Sequential Workflow",
    ) -> Dict[str, Any]:
        """
        Workflow: tasks are executed one after another, each handed off
        from the previous agent to the next.

        Args:
            tasks:  Descriptions of each task step.
            agents: Agent IDs (length should match tasks, or be reused).
            topic:  Optional topic label.

        Returns:
            Dictionary with completed steps and handoff chain.
        """
        if not tasks:
            raise ValueError("At least one task is required.")
        if not agents:
            raise ValueError("At least one agent is required.")

        session = CollaborationSession(topic=topic)

        # Register all agents
        for idx, aid in enumerate(agents):
            role = "lead" if idx == 0 else ("decider" if idx == len(agents) - 1 else "contributor")
            session.add_agent(aid, "executor", role)

        completed_steps: List[Dict[str, str]] = []
        for i, task in enumerate(tasks):
            agent = agents[i % len(agents)]
            session.broadcast(
                from_agent=agent,
                content=f"Step {i + 1}: {task} — completed by {agent}.",
                msg_type="feedback",
            )
            completed_steps.append({
                "step": i + 1,
                "task": task,
                "agent": agent,
            })

        return {
            "workflow": "sequential",
            "session_id": session.session_id,
            "topic": topic,
            "total_steps": len(tasks),
            "completed_steps": completed_steps,
            "transcript": session.export_transcript("json"),
        }

    # ------------------------------------------------------------------
    # 5. Parallel
    # ------------------------------------------------------------------

    @staticmethod
    def parallel(
        tasks: List[str],
        agents: List[str],
        topic: str = "Parallel Workflow",
    ) -> Dict[str, Any]:
        """
        Workflow: all agents work on their assigned tasks simultaneously;
        results are merged at the end.

        Args:
            tasks:  Descriptions of each parallel task.
            agents: Agent IDs (length should match tasks, or be reused).
            topic:  Optional topic label.

        Returns:
            Dictionary with individual results and merged output.
        """
        if not tasks:
            raise ValueError("At least one task is required.")
        if not agents:
            raise ValueError("At least one agent is required.")

        session = CollaborationSession(topic=topic)

        for aid in agents:
            session.add_agent(aid, "worker", "contributor")

        results: List[Dict[str, Any]] = []
        for i, task in enumerate(tasks):
            agent = agents[i % len(agents)]
            result_text = f"Result from {agent} for task '{task}': Completed successfully."
            session.broadcast(
                from_agent=agent,
                content=result_text,
                msg_type="feedback",
            )
            results.append({
                "task": task,
                "agent": agent,
                "result": result_text,
            })

        # Merge phase
        merge_summary = " | ".join(
            f"[{r['agent']}] {r['task']}" for r in results
        )
        session.broadcast(
            from_agent="system",
            content=f"Merge complete: {merge_summary}",
            msg_type="consensus",
        )

        return {
            "workflow": "parallel",
            "session_id": session.session_id,
            "topic": topic,
            "total_tasks": len(tasks),
            "individual_results": results,
            "merged_summary": merge_summary,
            "transcript": session.export_transcript("json"),
        }


# ---------------------------------------------------------------------------
# MockCollaborationSession — deterministic test double
# ---------------------------------------------------------------------------

class MockCollaborationSession(CollaborationSession):
    """
    In-memory, deterministic collaboration session for unit tests.

    Extends CollaborationSession but overrides message sending so that
    every broadcast receives predictable auto-responses from all other
    registered agents.  No external I/O is performed.
    """

    # Pre-canned responses indexed by (persona_type, msg_type)
    _RESPONSES: Dict[Tuple[str, str], List[str]] = {
        ("engineer", "proposal"): [
            "From an engineering standpoint, this looks solid.",
            "We should consider scalability implications.",
        ],
        ("engineer", "question"): [
            "The technical feasibility depends on stack choice.",
        ],
        ("lawyer", "proposal"): [
            "I need to review the liability implications.",
            "Ensure compliance with applicable regulations.",
        ],
        ("lawyer", "question"): [
            "Have we assessed the legal risks thoroughly?",
        ],
        ("reviewer", "proposal"): [
            "The proposal needs more evidence.",
            "I approve this with minor revisions.",
        ],
        ("reviewer", "feedback"): [
            "Documentation could be clearer.",
        ],
        ("analyst", "proposal"): [
            "Data supports this direction.",
            "I recommend additional metrics.",
        ],
        ("generic", "proposal"): [
            "I support this proposal.",
            "Interesting approach.",
        ],
        ("generic", "question"): [
            "Let me look into that.",
        ],
        ("generic", "feedback"): [
            "Acknowledged.",
        ],
        ("generic", "conflict"): [
            "I see the concern and propose a compromise.",
        ],
    }

    def __init__(self, session_id: str = None, topic: str = "") -> None:
        super().__init__(session_id=session_id, topic=topic)
        self._auto_respond = True
        self._response_index: Dict[str, int] = {}

    # -- overrides -------------------------------------------------------

    def send_message(
        self,
        from_agent: str,
        content: str,
        to_agent: str = "all",
        msg_type: str = "proposal",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a message and optionally trigger deterministic auto-replies."""
        msg_id = super().send_message(
            from_agent=from_agent,
            content=content,
            to_agent=to_agent,
            msg_type=msg_type,
            context=context,
        )

        if self._auto_respond and to_agent.lower() == "all" and from_agent != "system":
            self._inject_auto_responses(from_agent, msg_type)

        return msg_id

    def save_transcript(self, filepath: Optional[str] = None, fmt: str = "json") -> str:
        """No-op persistence for the mock session."""
        return "<mock-transcript-not-saved>"

    # -- internals -------------------------------------------------------

    def _inject_auto_responses(self, sender: str, msg_type: str) -> None:
        """Generate deterministic replies from every other registered agent."""
        for agent_id, info in self.agents.items():
            if agent_id == sender:
                continue
            persona = info.get("persona_type", "generic")
            key = (persona, msg_type)
            if key not in self._RESPONSES:
                key = ("generic", msg_type)
            if key not in self._RESPONSES:
                key = ("generic", "proposal")

            pool = self._RESPONSES[key]
            idx_key = f"{agent_id}:{msg_type}"
            idx = self._response_index.get(idx_key, 0)
            response_text = pool[idx % len(pool)]
            self._response_index[idx_key] = idx + 1

            super().send_message(
                from_agent=agent_id,
                content=f"[AUTO] {response_text}",
                to_agent=sender,
                msg_type="feedback",
                context={"auto_reply": True, "triggered_by": sender},
            )

    def enable_auto_responses(self, enabled: bool = True) -> None:
        """Toggle automatic deterministic replies."""
        self._auto_respond = enabled


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_collaboration_session(
    topic: str = "",
    mock: bool = False,
    session_id: Optional[str] = None,
) -> CollaborationSession:
    """
    Factory that creates a CollaborationSession (or MockCollaborationSession).

    Args:
        topic:      What the collaboration is about.
        mock:       If True, return a MockCollaborationSession.
        session_id: Optional explicit UUID.  A new one is generated if omitted.

    Returns:
        A fresh CollaborationSession instance (or subclass).
    """
    cls = MockCollaborationSession if mock else CollaborationSession
    return cls(session_id=session_id, topic=topic)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def quick_session(topic: str, agents: List[Dict[str, str]]) -> CollaborationSession:
    """
    Create a session, register a list of agents, and return it ready to use.

    *agents* should be a list of dicts with keys: agent_id, persona_type, role.
    """
    session = CollaborationSession(topic=topic)
    for a in agents:
        session.add_agent(
            agent_id=a["agent_id"],
            persona_type=a["persona_type"],
            role=a["role"],
        )
    return session
