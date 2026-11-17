import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.detectors.types import PiiType
from app.policy.beliefs import (
    PRIOR_SENSITIVITY,
    BeliefLearner,
    Beta,
    Feedback,
    InMemoryBeliefStore,
)

T = PiiType


def learner(decay: float = 1.0) -> BeliefLearner:
    return BeliefLearner(InMemoryBeliefStore(), decay)


def test_every_type_has_a_prior() -> None:
    assert set(PRIOR_SENSITIVITY) == set(PiiType)


def test_priors_order() -> None:
    lr = learner()
    assert (
        lr.sensitivity("o", T.AADHAAR)
        > lr.sensitivity("o", T.PHONE)
        > lr.sensitivity("o", T.GENDER)
    )


def test_keep_feedback_lowers_sensitivity_and_persists() -> None:
    lr = learner()
    before = lr.store.get("org1", T.LOCATION).sensitivity.mean
    for _ in range(10):
        lr.record("org1", T.LOCATION, Feedback.KEEP)
    after = lr.store.get("org1", T.LOCATION).sensitivity.mean
    assert after < before
    assert after == pytest.approx(4 / 20)  # Beta(4, 6) + 10 keeps -> 4 / 20
    # next scan for the same org sees it; another org does not (FR-17)
    assert lr.store.get("org2", T.LOCATION).sensitivity.mean == pytest.approx(before)


def test_false_alarm_does_not_lower_sensitivity() -> None:
    lr = learner()
    s0 = lr.store.get("o", T.PHONE).sensitivity
    p0 = lr.store.get("o", T.PHONE).precision.mean
    for _ in range(5):
        lr.record("o", T.PHONE, Feedback.NOT_PII)
    b = lr.store.get("o", T.PHONE)
    assert b.sensitivity == s0
    assert b.precision.mean < p0


def test_uncertainty_shrinks_with_evidence() -> None:
    lr = learner()
    std0 = lr.store.get("o", T.EMAIL).sensitivity.std
    for _ in range(20):
        lr.record("o", T.EMAIL, Feedback.PROTECT)
    assert lr.store.get("o", T.EMAIL).sensitivity.std < std0


def test_decay_forgets_old_feedback() -> None:
    no_decay, decay = learner(1.0), learner(0.8)
    for lr in (no_decay, decay):
        for _ in range(30):
            lr.record("o", T.AGE, Feedback.PROTECT)
        for _ in range(5):
            lr.record("o", T.AGE, Feedback.KEEP)
    # with forgetting, the recent "keep" votes count for more
    assert (
        decay.store.get("o", T.AGE).sensitivity.mean
        < no_decay.store.get("o", T.AGE).sensitivity.mean
    )


def test_json_round_trip_and_reset() -> None:
    lr = learner()
    lr.record("o", T.PAN, Feedback.KEEP)
    store = lr.store
    assert isinstance(store, InMemoryBeliefStore)
    again = InMemoryBeliefStore.from_json(store.to_json())
    assert again.get("o", T.PAN) == store.get("o", T.PAN)
    again.reset("o")
    assert again.get("o", T.PAN).sensitivity.mean == pytest.approx(PRIOR_SENSITIVITY[T.PAN])


def test_bad_decay_rejected() -> None:
    with pytest.raises(ValueError):
        learner(0.0)


@given(st.lists(st.sampled_from(list(Feedback)), max_size=60), st.floats(0.5, 1.0))
def test_beliefs_stay_valid(events: list[Feedback], decay: float) -> None:
    lr = learner(decay)
    for fb in events:
        b = lr.record("o", T.PERSON, fb)
        for beta in (b.sensitivity, b.precision):
            assert beta.alpha > 0 and beta.beta > 0
            assert 0.0 <= beta.mean <= 1.0 and 0.0 <= beta.cautious <= 1.0


def test_beta_mean_std() -> None:
    b = Beta(2, 2)
    assert b.mean == 0.5 and b.std == pytest.approx(0.2236, abs=1e-4)
