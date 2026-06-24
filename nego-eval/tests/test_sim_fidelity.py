"""Counterparty-sim fidelity checks (counterparty_sim.md §6).

The most important guarantee is testable on the prompt directly and holds for
both stub and live: the sim is given the route-out trigger but NEVER the
creation-door description (the door stays hidden by mindset). The behavioral
checks here exercise the stub sim's scripted accept/walk contract.
"""

from __future__ import annotations

import negoeval  # noqa: F401
from negoeval.cases import load_all, load_case, DEFAULT_CASES_DIR
from negoeval.orchestrator import run_episode
from negoeval.sim.prompt import render_system_prompt


def test_sim_prompt_never_signposts_the_door():
    for case in load_all():
        door = case.fixture["ground_truth"].get("creation_door", {})
        desc = (door.get("description") or "").strip()
        prompt = render_system_prompt(case)
        assert desc and desc not in prompt, f"{case.case_id}: door description leaked into sim prompt"
        # but the route-out trigger IS injected
        trigger = (door.get("route_out_trigger") or "").strip()
        if trigger:
            assert trigger in prompt, f"{case.case_id}: route_out_trigger missing from sim prompt"


def test_sim_accepts_compound_offer_par():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="on", agent_profile="par")
    assert out.terminal_reason == "settled"
    # the sim accepted a deal that carries a non-cash component
    assert out.final_deal.price.in_kind, "par settlement should include non-cash"


def test_sim_walks_on_cave_route_out():
    p1 = load_case(DEFAULT_CASES_DIR / "P1.jsonc")
    out = run_episode(p1, mode="stub", skills="on", agent_profile="cave")
    assert out.terminal_reason == "walk_away"
    # B never volunteered a non-cash arrangement of its own
    assert all(not (t.speaker == "B" and t.offer and t.offer.price.in_kind) for t in out.transcript)
