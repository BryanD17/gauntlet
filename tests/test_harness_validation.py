import pytest

from gauntlet.harness import HarnessError, parse_actions


@pytest.mark.parametrize("action", [
    {"action_type": "noop", "target": "qa"},
    {"action_type": "noop", "target": "qa", "params": None},
    {"action_type": "noop", "target": "qa", "params": []},
    {"action_type": "noop", "target": "qa", "params": ""},
    {"action_type": "noop", "params": {}},
    {"action_type": "noop", "target": [], "params": {}},
    {"action_type": "noop", "target": "qa", "params": {}, "note": {}},
])
def test_required_action_fields_keep_their_documented_types(action):
    with pytest.raises(HarnessError):
        parse_actions([action])


@pytest.mark.parametrize("note", [None, "needs review"])
def test_valid_action_fields_are_preserved(note):
    action = parse_actions([{
        "action_type": "flag",
        "target": "INV-1",
        "params": {},
        "note": note,
    }])[0]

    assert action.target == "INV-1"
    assert action.params == {}
    assert action.note == note
