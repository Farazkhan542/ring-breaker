"""Acceptance tests: data isolation, no raw account IDs leave a bank, and the policy agent blocks forbidden asks."""
import json

import pytest

from ringbreaker.bank_agent import BankAgent
from ringbreaker.config import BANKS
from ringbreaker.data import load_world, partition
from ringbreaker.investigation import run_local
from ringbreaker.policy import RAW_ID, Policy


@pytest.fixture(scope="module")
def setup():
    world = load_world()
    policy = Policy.load()
    agents = {b: BankAgent(partition(world, b), policy) for b in BANKS}
    return world, policy, agents


def test_partition_holds_only_own_customers_and_no_labels(setup):
    _, _, agents = setup
    for b, ag in agents.items():
        assert set(ag.view.accounts["bank"]) == {b}
        tx = ag.view.tx
        assert ((tx["From Bank"] == b) | (tx["To Bank"] == b)).all()
        assert "Is Laundering" not in tx.columns and "Ring ID" not in tx.columns


def test_no_raw_account_ids_cross_banks(setup):
    _, policy, agents = setup
    policy.audit.clear()
    for b, ag in agents.items():
        for a in list(ag.flags)[:5]:
            run_local(agents, b, a, policy, overreach_demo=True)
    cross = [e for e in policy.audit if e["kind"] in ("request", "response")]
    assert cross, "expected cross-bank messages"
    for e in cross:
        assert not RAW_ID.search(json.dumps(e["payload"])), e


def test_forbidden_fields_are_blocked(setup):
    _, policy, _ = setup
    d = policy.check_request({"type": "flag_status", "subject": "M-abc", "fields": ["name", "balance"]}, 0)
    assert not d.allowed and d.rule_id == "R5-forbidden-fields"


def test_unflagged_customer_is_withheld(setup):
    _, _, agents = setup
    ag = agents["BANK_B"]
    unflagged = next(a for a in ag.view.accounts.index if a not in ag.flags)
    from ringbreaker.masking import mask
    resp = ag.handle({"type": "linked_counterparties", "subject": mask(unflagged)})
    assert resp["status"] == "withheld"


def test_demo_case_finds_ring_across_three_banks_with_one_block(setup):
    _, policy, agents = setup
    policy.audit.clear()
    res = run_local(agents, "BANK_C", "C-00717", policy, overreach_demo=True)
    assert res["banks"] == ["BANK_A", "BANK_B", "BANK_C"] and len(res["ring"]) >= 5
    assert sum(1 for e in policy.audit if not e["allowed"]) == 1
