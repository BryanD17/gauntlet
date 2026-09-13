import pytest

from gauntlet.attacks import duplicate, injection, midwrite, stale
from gauntlet.harness import Action


class AlwaysRaises:
    def deliver(self, task):
        raise TimeoutError("offline")


class SecondRaises:
    def __init__(self):
        self.calls = 0

    def deliver(self, task):
        self.calls += 1
        if self.calls == 2:
            raise TimeoutError("offline")
        return [Action("pay_invoice", task["payload"]["invoice_id"], {"amount": task["payload"]["amount"]})]


class ReturnsEmpty:
    def deliver(self, task):
        return []


@pytest.mark.parametrize("attack", [injection, stale])
def test_first_delivery_error_retains_attempted_input(attack):
    result = attack(AlwaysRaises())

    assert result.verdict == "ERROR"
    assert len(result.inputs) == 1
    assert result.outputs == []


@pytest.mark.parametrize("attack", [duplicate, midwrite])
def test_second_delivery_error_retains_first_response(attack):
    result = attack(SecondRaises())

    assert result.verdict == "ERROR"
    assert len(result.inputs) == 2
    assert len(result.outputs) == 1
    assert result.outputs[0][0].action_type == "pay_invoice"


@pytest.mark.parametrize("attack", [duplicate, midwrite])
def test_zero_write_error_retains_both_response_groups(attack):
    result = attack(ReturnsEmpty())

    assert result.verdict == "ERROR"
    assert len(result.inputs) == 2
    assert result.outputs == [[], []]
