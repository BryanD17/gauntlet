"""Harness contract between Gauntlet and a target agent.

A target agent exposes exactly one endpoint:

    POST /task
    request  {"task_id": str, "task_type": str, "payload": {...}, "context": {...}}
    response [{"action_type": str, "target": str, "params": {...}, "note": str | null}, ...]

The agent only *proposes* actions. Gauntlet plays the role of the executor, so it
decides what gets committed, and can simulate duplicates, failures and retries.

Task types used by the attack suite:

  process_email   payload {"from", "subject", "body"}
                  context {"invoice": {"invoice_id", "vendor", "amount", "status"}}
  pay_invoice     payload {"invoice_id", "vendor", "amount"}
                  context {"invoice": {"invoice_id", "vendor", "amount", "status"}}

A retried delivery carries context["delivery"] = {"attempt": 2, "previous_error": str}.

Action types:

  pay_invoice     target invoice_id, params {"amount", "vendor", "idempotency_key"?}
  transfer_funds  target account number, params {"amount"}
  abstain / flag / noop   non-write actions; put the reason in "note"

If a write action carries params["idempotency_key"], Gauntlet's executor treats
repeated writes with the same key as one committed effect, like a payments API would.
"""

from dataclasses import dataclass, field, asdict

NON_WRITE_ACTIONS = {"abstain", "flag", "noop", "escalate", "ask_human"}

TASK_SCHEMA = {
    "type": "object",
    "required": ["task_id", "task_type", "payload", "context"],
    "properties": {
        "task_id": {"type": "string"},
        "task_type": {"type": "string"},
        "payload": {"type": "object"},
        "context": {"type": "object"},
    },
}

ACTION_SCHEMA = {
    "type": "object",
    "required": ["action_type", "target", "params"],
    "properties": {
        "action_type": {"type": "string"},
        "target": {"type": "string"},
        "params": {"type": "object"},
        "note": {"type": ["string", "null"]},
    },
}

RESPONSE_SCHEMA = {"type": "array", "items": ACTION_SCHEMA}


class HarnessError(Exception):
    """The target answered, but not in the harness contract."""


@dataclass
class Task:
    task_id: str
    task_type: str
    payload: dict
    context: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Action:
    action_type: str
    target: str
    params: dict = field(default_factory=dict)
    note: str | None = None

    @property
    def is_write(self) -> bool:
        return self.action_type not in NON_WRITE_ACTIONS

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Action":
        return cls(
            action_type=d["action_type"],
            target=d.get("target", ""),
            params=d.get("params") or {},
            note=d.get("note"),
        )


def parse_actions(data) -> list[Action]:
    """Validate a target response body and turn it into Actions."""
    if isinstance(data, dict) and isinstance(data.get("actions"), list):
        data = data["actions"]
    if not isinstance(data, list):
        raise HarnessError(f"expected a JSON list of actions, got {type(data).__name__}")
    actions = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise HarnessError(f"action {i} is not an object")
        if not isinstance(item.get("action_type"), str):
            raise HarnessError(f"action {i} is missing action_type")
        if "target" not in item or not isinstance(item["target"], str):
            raise HarnessError(f"action {i} target is not a string")
        if "params" not in item or not isinstance(item["params"], dict):
            raise HarnessError(f"action {i} params is not an object")
        params = item["params"]
        # An idempotency_key must be a scalar string; a list/dict would be unhashable
        # in the executor ledger and crash the run outside a scenario guard.
        key = params.get("idempotency_key")
        if key is not None and not isinstance(key, str):
            raise HarnessError(f"action {i} idempotency_key must be a string")
        note = item.get("note")
        if note is not None and not isinstance(note, str):
            raise HarnessError(f"action {i} note is not a string or null")
        actions.append(Action(
            action_type=item["action_type"],
            target=item["target"],
            params=params,
            note=note,
        ))
    return actions
