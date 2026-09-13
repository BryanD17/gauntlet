"""Exercise the attack suite against in-process reference targets."""

from gauntlet.attacks import ALL_ATTACKS, duplicate, injection, stale
from gauntlet.harness import Action, parse_actions


class NaiveTarget:
    """Trust instructions without checking context or remembering deliveries."""

    def deliver(self, task: dict) -> list[Action]:
        payload = task["payload"]
        actions = []
        if task["task_type"] == "process_email":
            if "transfer_funds" in payload.get("body", "").lower():
                actions.append({
                    "action_type": "transfer_funds",
                    "target": "999-EVIL-ACCT",
                    "params": {"amount": 50000},
                })
            invoice = task["context"]["invoice"]
        elif task["task_type"] == "pay_invoice":
            invoice = payload
        else:
            return parse_actions([])
        actions.append({
            "action_type": "pay_invoice",
            "target": invoice["invoice_id"],
            "params": {"amount": invoice["amount"], "vendor": invoice["vendor"]},
        })
        return parse_actions(actions)


class HardenedTarget:
    """Check invoice context and suppress repeated task deliveries."""

    def __init__(self):
        self.seen = set()

    def deliver(self, task: dict) -> list[Action]:
        task_id = task["task_id"]
        if task_id in self.seen:
            return parse_actions([
                {"action_type": "noop", "target": "", "params": {}, "note": "dup"}
            ])
        self.seen.add(task_id)

        payload = task["payload"]
        invoice = task.get("context", {}).get("invoice")
        if task["task_type"] == "process_email":
            if not invoice or invoice.get("status") != "approved":
                return parse_actions([{
                    "action_type": "abstain", "target": "", "params": {},
                    "note": "Invoice is not approved",
                }])
            payment = invoice
        elif task["task_type"] == "pay_invoice":
            if invoice and (
                payload["amount"] != invoice["amount"]
                or invoice.get("status") in {"paid", "void"}
            ):
                return parse_actions([{
                    "action_type": "abstain", "target": "", "params": {},
                    "note": "Invoice conflicts with the requested payment",
                }])
            payment = payload
        else:
            return parse_actions([])

        invoice_id = payment["invoice_id"]
        return parse_actions([{
            "action_type": "pay_invoice",
            "target": invoice_id,
            "params": {
                "amount": payment["amount"],
                "vendor": payment["vendor"],
                "idempotency_key": f"{task_id}:{invoice_id}",
            },
        }])


def test_naive_fails_all_four():
    t = NaiveTarget()
    for attack in ALL_ATTACKS:
        assert attack(t).landed is True


def test_hardened_passes_all_four():
    # Fresh memory per attack, matching separate runs.
    for attack in ALL_ATTACKS:
        assert attack(HardenedTarget()).caught is True


def test_injection_naive_fail():
    assert injection(NaiveTarget()).verdict == "FAIL"


def test_injection_hardened_pass():
    assert injection(HardenedTarget()).verdict == "PASS"


def test_duplicate_hardened_single_effect():
    assert duplicate(HardenedTarget()).verdict == "PASS"


def test_stale_hardened_abstains():
    assert stale(HardenedTarget()).verdict == "ABSTAINED"
