"""
Input guardrails for the Bookly CX agent.

Layer: rule-based prompt injection detection.
Runs before the message reaches Claude — zero LLM cost.

If triggered:
  - Writes a security flag task to tasks.json for the operator inbox
  - Returns a canned customer-facing response
"""

import json
import os
import re
from datetime import datetime, timezone

TASKS_PATH = os.path.join(os.path.dirname(__file__), "..", "tasks.json")

# Common prompt injection patterns
# Covers the classic attempts: role override, instruction bypass, system prompt extraction
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|your|the)?\s*(instructions?|rules?|guidelines?|system\s+prompt|constraints?)",
    r"disregard\s+(all\s+)?(previous|prior|your|the)?\s*(instructions?|rules?|guidelines?)",
    r"forget\s+(all\s+)?(your|the|previous)?\s*(instructions?|rules?|guidelines?|training)",
    r"override\s+(your|the|all)?\s*(instructions?|rules?|system|constraints?|filters?)",
    r"bypass\s+(your|the|all)?\s*(instructions?|rules?|filters?|guardrails?|restrictions?)",
    r"you\s+are\s+now\s+(a|an|the)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"act\s+as\s+(if\s+you\s+are|a|an)",
    r"new\s+(persona|role|identity|instructions?)",
    r"(reveal|print|show|display|repeat|output)\s+(your|the)\s*(system\s+prompt|instructions?|rules?|guidelines?|prompt)",
    r"what\s+(are|were)\s+your\s+(instructions?|rules?|system\s+prompt)",
    r"(escape|break\s+out\s+of|break\s+free\s+from)\s+(your\s+)?(role|character|constraints?)",
    r"\bjailbreak\b",
    r"\bDAN\b",
    r"do\s+anything\s+now",
    r"developer\s+mode",
    r"training\s+data\b",
    r"(simulate|roleplay|role-play)\s+(being|a|an)\s+\w+\s+(without|that\s+(ignores?|has\s+no))",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def is_prompt_injection(text: str) -> bool:
    """Returns True if the message matches a known injection pattern."""
    for pattern in _compiled:
        if pattern.search(text):
            return True
    return False


def flag_security_event(message: str, history: list) -> None:
    """
    Write a security flag task to tasks.json so it appears in the operator inbox.
    Includes the flagged message and a short conversation excerpt for context.
    """
    # Build a short context snippet from recent history (last 4 turns)
    recent = history[-4:] if len(history) >= 4 else history
    context_lines = []
    for turn in recent:
        role = "Customer" if turn.get("role") == "user" else "Agent"
        content = turn.get("content", "")
        # content may be a list (multimodal) — flatten to text
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        context_lines.append(f"{role}: {content}")
    context_lines.append(f"Customer: {message}  ← FLAGGED")
    conversation_excerpt = "\n".join(context_lines)

    if not os.path.exists(TASKS_PATH):
        tasks = []
    else:
        with open(TASKS_PATH, "r") as f:
            tasks = json.load(f)

    tasks.append({
        "ticket_id": f"SEC-{datetime.now(timezone.utc).strftime('%H%M%S')}",
        "order_id": "—",
        "reason": "Prompt injection attempt detected",
        "summary": f"Flagged message:\n\"{message}\"\n\nConversation context:\n{conversation_excerpt}",
        "image_filename": None,
        "status": "pending",
        "type": "security",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "procedure": None
    })

    with open(TASKS_PATH, "w") as f:
        json.dump(tasks, f, indent=2)


# Customer-facing response when injection is detected
# Deliberately vague — don't tell the attacker what triggered it
INJECTION_RESPONSE = (
    "I wasn't able to process that message. "
    "I've flagged this conversation for a human agent who'll follow up with you shortly. "
    "If you have a genuine support question, feel free to ask and I'm happy to help."
)