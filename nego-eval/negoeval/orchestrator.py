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


def _usage(provider) -> dict:
    """Token tally snapshot; {} for providers without accounting (e.g. stub)."""
    snap = getattr(provider, "usage_snapshot", None)
    return snap() if callable(snap) else {}


def _model_of(provider) -> str:
    """Model id a provider is bound to; "" for stub providers."""
    return str(getattr(provider, "model", "") or "")


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
    prompt_variant = "clean" if skills == "clean" else "full"
    request, agent_side, sim_side = build_broker_request(inp, side, value_tools_enabled=tools_enabled)
    allowlist = all_skill_names() if skills == "on" else set()

    # Per-role models in live mode: agent = model-under-test; aux = fixed neutral
    # (extractor + judges). The sim is an experimental variable, not part of the
    # measuring instrument, so it gets its own optional block.
    agent_cfg = live_config.agent if (mode == "live" and live_config) else None
    aux_cfg = live_config.aux if (mode == "live" and live_config) else None
    # === SIM_CFG_PATCH (v0811) ===
    # sim reads `sim:` when the config defines it, else falls back to aux
    # (legacy behaviour preserved for every config written before this patch).
    sim_cfg = (getattr(live_config, "sim", None) or aux_cfg) if (mode == "live" and live_config) else None

    # === TOKEN_USAGE_PATCH (v0811) ===
    # Hold named refs so per-role token tallies can be read after the episode.
    agent_provider = build_provider(
        "agent", mode=mode, case=case, agent_profile=agent_profile, llm_config=agent_cfg
    )
    sim_provider = build_provider(
        "sim", mode=mode, case=case, agent_profile=agent_profile, llm_config=sim_cfg
    )
    extractor_provider = build_provider(
        "extractor", mode=mode, case=case, agent_profile=agent_profile, llm_config=aux_cfg
    )

    agent = AgentUnderTest(
        request,
        agent_provider,
        allowlist=allowlist,
        prompt_variant=prompt_variant,
    )
    sim = CounterpartySim(case, sim_provider)
    extractor = OfferExtractor(case, extractor_provider)

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
        # === TOKEN_USAGE_PATCH (v0811) ===
        # Per-role token accounting. Judge is added later by the caller (it runs
        # inside evaluate()). Stub providers have no tally -> {}.
        "token_usage": {
            "agent": _usage(agent_provider),
            "sim": _usage(sim_provider),
            "extractor": _usage(extractor_provider),
        },
        # === SIM_CFG_PATCH (v0811) ===
        # Which model actually ran each role. Without this a result file cannot
        # prove which arm it belongs to — needed now that arms differ in tier
        # (flash vs pro). Judge is filled in by evaluate(), same as token_usage.
        "model_by_role": {
            "agent": _model_of(agent_provider),
            "sim": _model_of(sim_provider),
            "extractor": _model_of(extractor_provider),
        },
    }
    return EpisodeOutput(
        episode_id=inp.episode_id,
        final_deal=final_deal,
        transcript=turns,
        rounds=rounds,
        terminal_reason=terminal,
        process=process,
    )
