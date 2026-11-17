from app.detectors.types import PiiType, Span
from app.fusion.risk import RiskLevel
from app.policy.actions import Action, generalize, mask
from app.policy.beliefs import BeliefLearner, Feedback, InMemoryBeliefStore
from app.policy.utility import PolicyConfig, choose, decide

T = PiiType
CFG = PolicyConfig()


def sp(text: str, part: str, t: PiiType, nth: int = 0) -> Span:
    i = -1
    for _ in range(nth + 1):
        i = text.index(part, i + 1)
    return Span(i, i + len(part), part, t, 0.9, "ner")


def prior_sens(t: PiiType) -> float:
    return BeliefLearner(InMemoryBeliefStore()).sensitivity("org", t)


# ---------- single-span choices ----------


def test_default_choices_follow_sensitivity() -> None:
    t = "Rahul, 34, male, PIN 682016"
    cases = {
        "Rahul": (T.PERSON, Action.PSEUDONYMIZE),
        "34": (T.AGE, Action.GENERALIZE),
        "male": (T.GENDER, Action.KEEP),
        "682016": (T.ADDRESS, Action.PSEUDONYMIZE),
    }
    for part, (typ, want) in cases.items():
        d = choose(sp(t, part, typ), prior_sens(typ), CFG)
        assert d.action is want, (part, d)


def test_override_wins() -> None:
    cfg = PolicyConfig(overrides={T.AADHAAR: Action.REDACT})
    t = "Aadhaar 3948 1726 3059"
    assert choose(sp(t, "3948 1726 3059", T.AADHAAR), 0.99, cfg).reason == "override"
    assert choose(sp(t, "3948 1726 3059", T.AADHAAR), 0.99, cfg).action is Action.REDACT


def test_toll_free_is_kept() -> None:
    t = "Call 1800-425-3800"
    d = choose(sp(t, "1800-425-3800", T.PHONE), 0.99, CFG)
    assert d.action is Action.KEEP and d.reason == "business number"


def test_learned_feedback_changes_the_choice() -> None:
    lr = BeliefLearner(InMemoryBeliefStore())
    t = "from Kochi"
    span = sp(t, "Kochi", T.LOCATION)
    before = choose(span, lr.sensitivity("o", T.LOCATION), CFG).action
    # pseudonymize stays best until s < 0.5*0.3/0.9 = 0.167 (ADR-0017); 40 keeps get below it
    for _ in range(40):
        lr.record("o", T.LOCATION, Feedback.KEEP)
    after = choose(span, lr.sensitivity("o", T.LOCATION), CFG).action
    assert before is Action.PSEUDONYMIZE and after is Action.KEEP


# ---------- render helpers ----------


def test_generalize_and_mask_formats() -> None:
    assert generalize(T.AGE, "34") == "30-34"
    assert generalize(T.DATE, "23-10-2002") == "2002"
    assert generalize(T.ADDRESS, "682016") == "682XXX"
    assert mask(T.PHONE, "98470 12345") == "98*** ***45"
    assert mask(T.CARD, "4111 1111 1111 1111") == "XXXX XXXX XXXX 1111"
    assert mask(T.EMAIL, "priya.v@gmail.com") == "p******@gmail.com"


# ---------- document level ----------


def test_risk_loop_strengthens_most_identifying_clue_first() -> None:
    t = "DOB: 23-10-2002, Gender: Male, PIN 673601"
    spans = [sp(t, "23-10-2002", T.DATE), sp(t, "Male", T.GENDER), sp(t, "673601", T.ADDRESS)]
    res = decide(t, spans, lambda _t: 0.0, CFG)  # beliefs say "keep everything"
    acts = [d.action for d in res.decisions]
    # only the DOB had to change (DOB -> year), and that was enough
    assert acts == [Action.GENERALIZE, Action.KEEP, Action.KEEP]
    assert res.decisions[0].reason == "risk"
    assert res.risk.level is RiskLevel.MEDIUM
    assert res.output == "DOB: 2002, Gender: Male, PIN 673601"


def test_direct_identifier_is_never_left_when_risk_capped() -> None:
    t = "Priya lives in Kochi"
    res = decide(t, [sp(t, "Priya", T.PERSON), sp(t, "Kochi", T.LOCATION)], lambda _t: 0.0, CFG)
    assert res.decisions[0].action is not Action.KEEP
    assert res.risk.level is not RiskLevel.DIRECT


def test_override_can_block_the_risk_loop() -> None:
    cfg = PolicyConfig(overrides={T.PERSON: Action.KEEP})
    t = "Priya lives here"
    res = decide(t, [sp(t, "Priya", T.PERSON)], lambda _t: 0.0, cfg)
    assert res.decisions[0].action is Action.KEEP
    assert res.risk.level is RiskLevel.DIRECT  # reported honestly, not hidden


def test_linked_mentions_share_one_pseudonym() -> None:
    t = "Rahul Sharma called. Later Rahul called again. Priya Iyer too."
    spans = [
        sp(t, "Rahul Sharma", T.PERSON),
        sp(t, "Rahul", T.PERSON, 1),
        sp(t, "Priya Iyer", T.PERSON),
    ]
    res = decide(t, spans, prior_sens, CFG)
    assert res.output == "PERSON_1 called. Later PERSON_1 called again. PERSON_2 too."


def test_full_example() -> None:
    t = "Patient Arjun Nair, age 34, admitted on 12/03/2026. Call 98470 12345."
    spans = [
        sp(t, "Arjun Nair", T.PERSON),
        sp(t, "34", T.AGE),
        sp(t, "12/03/2026", T.DATE),
        sp(t, "98470 12345", T.PHONE),
    ]
    res = decide(t, spans, prior_sens, CFG)
    assert res.output == "Patient PERSON_1, age 30-34, admitted on 2026. Call PHONE_1."
    assert res.risk.level is RiskLevel.LOW
