"""OfferExtractor — turn an agent's free-text turn into a structured ``Deal``.

The broker emits prose, but the deterministic metrics (M3/M4/M5/M7/M9/M10)
need structured offers. ``extract_turn`` asks the provider for a Deal that the
message proposes (stub returns a canned, fixture-aligned
Deal); resource names are snapped to the case's resource-set ids; unmentioned
fields carry forward. ``extract_final`` is pure assembly (no LLM): pick the
accepted/last offer, set status, and ensure every required field carries a
provenance tag (load-bearing for M1/M2).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..dealnorm import coerce_deal
from ..jsonutil import extract_json
from ..schemas import Deal

_PROV_DEFAULTS = {
    "subject": "stated",
    "price.cash": "inferred",
    "price.in_kind": "inferred",
    "terms.format": "inferred",
    "terms.timing.deadline": "stated",
    "terms.delivery_standard": "inferred",
    "obligations": "inferred",
    "status": "inferred",
}


class OfferExtractor:
    def __init__(self, case, provider):
        self.case = case
        self.provider = provider
        gt = case.fixture.get("ground_truth", {})
        self.provider_party = "B" if case.side == "sell" else "A"
        self.resource_ids = [r["id"] for r in gt.get("controllable_resource_set", [])]
        self.resource_labels = {r["id"]: r.get("label", r["id"]) for r in gt.get("controllable_resource_set", [])}
        self.required_fields: List[str] = (
            case.fixture.get("answers", {}).get("M1", {}).get("required_fields", [])
        )
        # Tracks rounds where extraction fell back to prev_offer (parse or validation failure).
        self.fallback_turns: List[str] = []
        # Post-hoc sanity warnings on the final deal (non-blocking; surfaced for review).
        self.warnings: List[str] = []

    # -- per-turn structured offer ---------------------------------------- #
    def extract_turn(
        self, text: str, *, prev_offer: Optional[Deal], speaker: str, round_no: int = 0
    ) -> Optional[Deal]:
        messages = self._prompt(text, prev_offer)
        raw = self.provider.chat_completion(messages=messages, temperature=0.0)
        data = extract_json(raw)
        if not data:
            self.fallback_turns.append(f"r{round_no}:no_json")
            return prev_offer
        try:
            deal = Deal.model_validate(coerce_deal(data, provider_party=self.provider_party))
        except Exception:
            self.fallback_turns.append(f"r{round_no}:validation_error")
            return prev_offer
        self._snap_resources(deal)
        self._carry_forward(deal, prev_offer)
        return deal

    def _prompt(self, text: str, prev_offer: Optional[Deal]) -> List[Dict[str, Any]]:
        prev = prev_offer.model_dump() if prev_offer else None
        system = (
            "你是一个信息抽取器。把谈判者这一轮发言中提出的交易条款抽成一个 Deal JSON。"
            "字段：subject, price{cash{amount,currency}, in_kind[{resource,description,from_party}]}, "
            "terms{timing{when,deadline,duration},format,deliverables,delivery_standard}, "
            "obligations[{party,text,maps_to_resource}], status, provenance。"
            f"in_kind.resource 与 obligations.maps_to_resource 必须取自：{self.resource_ids}。"
            "未提及的字段沿用上一版。"
            "【只抽真实出现的内容】只抽本轮发言里【真实明确出现】的条款,不要补全、不要脑补。"
            "(1) timing.when/deadline/duration：只有发言里出现【明确的日期/期限/时长】才填,"
            "像'近期''配合排期''尽快'这类模糊措辞一律留 null,不要凭空落定具体日期。"
            "(2) in_kind 与 obligations.maps_to_resource：只有发言里【真实提出了对应的非现金对价或义务】"
            "才写入对应 resource;不要因为发言提到某个话题就给它挂一个 resource。没有就留空数组。"
            "【多版本消歧】若本轮发言里出现多个价格/方案(例如主方案+括号备选、版本一/版本二、"
            "或'要么…要么…'),只抽取谈判者本轮【最终主推/确认】的那一个方案,不要抽取被否决的旧值、"
            "括号里的备选、或仅作对比的参照价。"
            "【并列的完整方案】若一轮里摆出两个并列的完整方案(如'方案一:单场七三分成'+'方案二:独家六四分成'),"
            "且上下文显示对方只接受/主推其中一个、pass 掉另一个,则只把【被接受/主推那个方案】的 in_kind 与 "
            "obligations 抽进来;被 pass/拒绝方案独有的条款(分成比例、独家性、额外资源)绝不抽入,"
            "避免最终 deal 里混入两个互斥方案的条款。"
            "【无数字的现金承诺】若本轮发言明确承诺了现金付费但没有给出具体数字"
            "(如'按你的公开刊例价走''价格你定我们照付''预算不是问题按市场价来'),"
            "cash.amount 填 -1 表示'已承诺现金、金额未定'——绝不能留 null(null 表示无现金承诺)。"
            "【绝不加总】绝不把并列方案的金额相加;附加佣金/返点/奖励若属于未被选中的方案,不计入 cash。只输出 JSON。"
        )
        user = f"上一版 Deal:\n{json.dumps(prev, ensure_ascii=False)}\n\n本轮发言:\n{text}"
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _snap_resources(self, deal: Deal) -> None:
        ids = set(self.resource_ids)
        for item in deal.price.in_kind:
            if item.resource not in ids:
                item.resource = self._match_resource(item.resource, item.description) or item.resource
        for ob in deal.obligations:
            if ob.maps_to_resource and ob.maps_to_resource not in ids:
                ob.maps_to_resource = self._match_resource(ob.maps_to_resource, ob.text)

    def _match_resource(self, name: str, hint: str) -> Optional[str]:
        text = f"{name} {hint}"
        for rid, label in self.resource_labels.items():
            if rid in text or (label and label[:4] and label[:4] in text):
                return rid
        return None

    def _carry_forward(self, deal: Deal, prev_offer: Optional[Deal]) -> None:
        init = self.case.input.initial_deal
        # subject 抽取偶尔吐出空值或字面量 "None"/"null"，回退到 v0 原值。
        # 注意：真重构出的新 subject（有意义的新标的）不会命中这些坏值，不受影响。
        if not deal.subject or str(deal.subject).strip() in ("None", "none", "null", ""):
            deal.subject = init.subject
        # 继承 v0 的真实 provenance（stated/open），只补缺失项、不覆盖抽取已标的，
        # 让 final_deal 的来源标记与 v0 一致（M1 结构检查与输出消费者依赖它）。
        for _field, _prov in (init.provenance or {}).items():
            deal.provenance.setdefault(_field, _prov)
        # NOTE: deadline is intentionally NOT carried forward from v0. The v0
        # placeholder ("近期" etc.) is not a negotiated term; carrying it into
        # the final deal made M2 see a fabricated deadline. Leave null unless a
        # turn explicitly states one.
        if prev_offer is not None:
            if deal.price.cash.amount is None and prev_offer.price.cash.amount is not None:
                deal.price.cash = prev_offer.price.cash.model_copy()
            # A concrete number in prev must not be degraded to the undefined-cash
            # sentinel by a later vague turn ("那就按说好的来").
            prev_amt = prev_offer.price.cash.amount
            if (deal.price.cash.amount is not None and float(deal.price.cash.amount) == -1
                    and prev_amt is not None and float(prev_amt) != -1):
                deal.price.cash = prev_offer.price.cash.model_copy()
            if not deal.price.in_kind and prev_offer.price.in_kind:
                deal.price.in_kind = [i.model_copy() for i in prev_offer.price.in_kind]

    # -- final deal assembly (no LLM) ------------------------------------- #
    @staticmethod
    def _nonempty(deal: Optional[Deal]) -> bool:
        return deal is not None and (
            deal.price.cash.amount is not None or bool(deal.price.in_kind) or bool(deal.obligations)
        )

    def extract_accepted(
        self, accept_text: str, a_text: str, prev_offer: Optional[Deal]
    ) -> Optional[Deal]:
        """Resolve which offer B actually accepted when B accepts in natural
        language (no structured offer of its own).

        Bug this fixes: when A puts multiple parallel plans on the table
        (组合A/组合B, 方案一/方案二) and B accepts one of them by name in prose,
        the orchestrator used to fall back to ``prev_offer`` — the A turn already
        collapsed to whichever plan the extractor picked first, not the one B
        chose. Here we re-extract using B's acceptance text plus A's full offer
        text so the extractor can bind to the plan B named.
        """
        prev = prev_offer.model_dump() if prev_offer else None
        system = (
            "你是一个信息抽取器。上一方(A)在其发言里可能摆出了【多个并列方案】"
            "(如 组合A/组合B、方案一/方案二、或'要么…要么…'),对方(B)随后用自然语言"
            "【明确接受了其中某一个方案】。你的任务：结合 B 的接受话术,判断 B 到底选了 A 的哪个方案,"
            "然后【只抽取 B 实际接受的那个方案】的条款,抽成一个 Deal JSON。\n"
            "【关键】以 B 接受话术里指名/描述的方案为准(如 B 说'方案B/1.5万那个/深度绑定档'),"
            "从 A 发言中定位对应方案,抽取该方案的 cash 与 in_kind。"
            "绝不抽取 B 未选的那个方案的价格或资源。若 B 的话术里直接确认了某个具体数字(如'1.5万'),"
            "以该数字为准。\n"
            f"in_kind.resource 与 obligations.maps_to_resource 必须取自：{self.resource_ids}。\n"
            "字段：subject, price{cash{amount,currency}, in_kind[{resource,description,from_party}]}, "
            "terms{timing{when,deadline,duration},format,deliverables,delivery_standard}, "
            "obligations[{party,text,maps_to_resource}], status, provenance。"
            "未在本轮明确出现的字段沿用上一版。"
            "【绝不加总】绝不把两个方案的金额相加;附加佣金/返点若属于 B 未选中的方案,绝不计入 cash。"
            "【无数字的现金承诺】若被接受的方案承诺现金但无具体数字(如'按刊例价'),cash.amount 填 -1。只输出 JSON。"
        )
        user = (
            f"上一版 Deal:\n{json.dumps(prev, ensure_ascii=False)}\n\n"
            f"A 的发言(含并列方案)：\n{a_text}\n\n"
            f"B 的接受话术(指明接受哪个方案)：\n{accept_text}"
        )
        raw = self.provider.chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0,
        )
        data = extract_json(raw)
        if not data:
            self.fallback_turns.append("accepted:no_json")
            return None
        try:
            deal = Deal.model_validate(coerce_deal(data, provider_party=self.provider_party))
        except Exception:
            self.fallback_turns.append("accepted:validation_error")
            return None
        self._snap_resources(deal)
        self._carry_forward(deal, prev_offer)
        return deal

    def extract_final(self, turns, *, accepted_offer: Optional[Deal], status: str) -> Deal:
        # When settled, the accepted offer IS the deal — it reflects exactly what
        # B agreed to, so withdrawn/rejected terms from earlier rounds are not in
        # it. Prefer it over scanning back for the last non-empty A offer (which
        # could resurrect a superseded version). Fall back to the last-offer scan
        # only when there is no usable accepted offer (e.g. walk_away / round_cap).
        base = None
        if status == "settled" and self._nonempty(accepted_offer):
            base = accepted_offer
        if base is None:
            for t in reversed(turns):
                if t.speaker == "A" and self._nonempty(t.offer):
                    base = t.offer
                    break
        if base is None and self._nonempty(accepted_offer):
            base = accepted_offer
        if base is None:
            for t in reversed(turns):
                if self._nonempty(t.offer):
                    base = t.offer
                    break
        if base is None:
            base = accepted_offer or self.case.input.initial_deal
        deal = base.model_copy(deep=True)
        deal.status = status
        # Undefined-cash sentinel (-1): the transcript committed to cash without a
        # number ("按刊例价"). Normalize the record to None but surface a warning
        # that M5 treats as blocking — a settled deal may not contain an
        # undefined cash commitment (it evades the cash cap otherwise).
        if deal.price.cash.amount is not None and float(deal.price.cash.amount) == -1:
            deal.price.cash.amount = None
            self.warnings.append("undefined_cash_commitment")
        self._ensure_provenance(deal)
        self._sanity_check(deal, turns)
        return deal

    def _sanity_check(self, deal: Deal, turns) -> None:
        """Post-hoc, non-blocking checks against the transcript. Flags (not fixes)
        the high-frequency extraction errors so the judge no longer silently
        absorbs them and downstream code can audit them:

          - cash amount that never appears anywhere in the dialogue (likely an
            extraction artifact — e.g. an abandoned/alternate quote);
          - in_kind / obligation resources outside the case resource-set.
        """
        ids = set(self.resource_ids)
        cash = deal.price.cash.amount
        if cash is not None and cash != 0:
            spoken = " ".join((t.message or "") for t in turns).replace(",", "")
            # match the integer and common comma/decimal forms
            n = int(cash) if float(cash).is_integer() else cash
            if str(n) not in spoken and f"{n:,}" not in (t.message or "" for t in turns):
                # second-chance: any offer on record carrying this cash value
                in_offers = any(
                    t.offer is not None and t.offer.price.cash.amount == cash for t in turns
                )
                if not in_offers:
                    self.warnings.append(f"cash_not_in_transcript:{n}")
        _seen_res = {}
        for item in deal.price.in_kind:
            if item.resource not in ids:
                self.warnings.append(f"inkind_unknown_resource:{item.resource}")
            # 同一 resource 出现多条 → 可能并列方案混入 (非阻塞 flag, 供审阅)
            _seen_res[item.resource] = _seen_res.get(item.resource, 0) + 1
        for _r, _c in _seen_res.items():
            if _c >= 2:
                self.warnings.append(f"inkind_duplicate_resource:{_r}x{_c}")
        for ob in deal.obligations:
            if ob.maps_to_resource and ob.maps_to_resource not in ids:
                self.warnings.append(f"obl_unknown_resource:{ob.maps_to_resource}")

    def _ensure_provenance(self, deal: Deal) -> None:
        for field in self.required_fields:
            if field not in deal.provenance:
                deal.provenance[field] = _PROV_DEFAULTS.get(field, "inferred")
