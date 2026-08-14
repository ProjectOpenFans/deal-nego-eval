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


def _live_role_specs(case, live_config):
    """Resolve v2 side-specific roles, with v1 agent/aux compatibility."""
    if hasattr(live_config, "role_spec"):
        if case.side == "sell":
            negotiator_role = "seller_negotiator"
            counterparty_role = "buyer_counterparty"
        else:
            negotiator_role = "buyer_negotiator"
            counterparty_role = "seller_counterparty"
        return (
            live_config.role_spec(negotiator_role),
            live_config.role_spec(counterparty_role),
            live_config.role_spec("offer_extractor"),
        )
    return live_config.agent, live_config.aux, live_config.aux


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
    # A6 adds a `-cap` suffix (clean-cap / on-cap) that appends the value-capture
    # directive. It is orthogonal to the skills axis, so strip it before deciding
    # tools and the allowlist and pass it through only on the prompt variant.
    capture = skills.endswith("-cap")
    base_skills = skills[: -len("-cap")] if capture else skills
    tools_enabled = base_skills == "on"
    prompt_variant = "clean" if base_skills == "clean" else "full"
    if capture:
        prompt_variant += "-cap"
    request, agent_side, sim_side = build_broker_request(inp, side, value_tools_enabled=tools_enabled)
    allowlist = all_skill_names() if tools_enabled else set()

    agent_cfg = sim_cfg = extractor_cfg = None
    if mode == "live" and live_config:
        agent_cfg, sim_cfg, extractor_cfg = _live_role_specs(case, live_config)

    agent = AgentUnderTest(
        request,
        build_provider("agent", mode=mode, case=case, agent_profile=agent_profile, llm_config=agent_cfg),
        allowlist=allowlist,
        prompt_variant=prompt_variant,
    )
    sim = CounterpartySim(
        case,
        build_provider(
            "sim",
            mode=mode,
            case=case,
            agent_profile=agent_profile,
            llm_config=sim_cfg,
        ),
    )
    extractor = OfferExtractor(
        case,
        build_provider(
            "extractor",
            mode=mode,
            case=case,
            agent_profile=agent_profile,
            llm_config=extractor_cfg,
        ),
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
            if sim_turn.offer is not None:
                # B countered with its own structured offer and then accepted it.
                accepted_offer = sim_turn.offer
            else:
                # B accepted in natural language. If A's last turn put multiple
                # parallel plans on the table, prev_offer may be the wrong plan.
                # Re-extract from B's acceptance text + A's full offer text so we
                # bind to the plan B actually named. Fall back to prev_offer if
                # re-extraction fails or yields nothing.
                resolved = extractor.extract_accepted(
                    accept_text=sim_turn.message, a_text=a_text, prev_offer=prev_offer
                )
                accepted_offer = resolved if resolved is not None else prev_offer
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
        "skills_forced": list(agent.skills_forced),
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
