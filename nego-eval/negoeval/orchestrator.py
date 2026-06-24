"""Run one negotiation episode: agent (seat A) vs counterparty sim (seat B).

Turn loop, sim-driven termination (ACCEPT/WALK) or ``round_cap``, structured-offer
extraction per turn, and trajectory capture. Produces an ``EpisodeOutput``.
"""

from __future__ import annotations

from typing import Optional

from .agent.adapter import build_broker_request, to_transcript_history
from .agent.runner import AgentUnderTest
from .broker.skills import all_skill_names
from .extract.offer_extractor import OfferExtractor
from .llm.registry import build_provider
from .schemas import Deal, EpisodeOutput, Turn
from .sim.counterparty import CounterpartySim

_STATUS = {"settled": "settled", "walk_away": "walked_away", "round_cap": "draft"}


def run_episode(
    case,
    *,
    mode: str = "stub",
    skills: str = "on",
    agent_profile: str = "par",
    live_config=None,
) -> EpisodeOutput:
    inp = case.input
    side = case.side
    tools_enabled = skills == "on"
    request, agent_side, sim_side = build_broker_request(inp, side, value_tools_enabled=tools_enabled)
    allowlist = all_skill_names() if skills == "on" else set()

    # Per-role models in live mode: agent = model-under-test; aux = fixed neutral.
    agent_cfg = live_config.agent if (mode == "live" and live_config) else None
    aux_cfg = live_config.aux if (mode == "live" and live_config) else None

    agent = AgentUnderTest(
        request,
        build_provider("agent", mode=mode, case=case, agent_profile=agent_profile, llm_config=agent_cfg),
        allowlist=allowlist,
    )
    sim = CounterpartySim(
        case, build_provider("sim", mode=mode, case=case, agent_profile=agent_profile, llm_config=aux_cfg)
    )
    extractor = OfferExtractor(
        case, build_provider("extractor", mode=mode, case=case, agent_profile=agent_profile, llm_config=aux_cfg)
    )

    turns = []
    terminal = "round_cap"
    accepted_offer: Optional[Deal] = None
    prev_offer: Optional[Deal] = None

    for r in range(1, inp.config.round_cap + 1):
        history = to_transcript_history(turns, agent_side, sim_side)
        a_text = agent.play_turn(side=agent_side, round_number=r, transcript_history=history)
        a_offer = extractor.extract_turn(a_text, prev_offer=prev_offer, speaker="A", round_no=r)
        if a_offer is not None:
            prev_offer = a_offer
        turns.append(Turn(round=r, speaker="A", message=a_text, offer=a_offer))

        sim_turn = sim.respond(turns, r)
        turns.append(Turn(round=r, speaker="B", message=sim_turn.message, offer=sim_turn.offer))

        if sim_turn.action == "ACCEPT":
            terminal = "settled"
            accepted_offer = sim_turn.offer or prev_offer
            break
        if sim_turn.action == "WALK":
            terminal = "walk_away"
            break

    rounds = turns[-1].round if turns else 0
    final_deal = extractor.extract_final(
        turns,
        accepted_offer=accepted_offer if terminal == "settled" else None,
        status=_STATUS[terminal],
    )
    process = {
        "skills_used": list(agent.skills_used),
        "tool_calls": list(agent.executor.tool_calls),
        "trace": list(agent.emitter.trace),
        "extract_fallbacks": list(extractor.fallback_turns),
        "extract_warnings": list(extractor.warnings),
        "mode": mode,
        "skills": skills,
        "agent_profile": agent_profile,
        "agent_side": agent_side,
        "sim_side": sim_side,
    }
    return EpisodeOutput(
        episode_id=inp.episode_id,
        final_deal=final_deal,
        transcript=turns,
        rounds=rounds,
        terminal_reason=terminal,
        process=process,
    )
