from core.models import (
    Direction,
    TrendContext,
    Zone,
    Confirmation,
)

from scoring.score_engine import (
    calculate_score,
    should_send_signal,
)

from risk.risk_manager import (
    calculate_rr,
)

from signals.signal_engine import (
    build_signal,
)

from signals.tracker import (
    SignalTracker,
)


def create_test_components():

    trend = TrendContext(
        d1=Direction.BUY,
        h4=Direction.BUY,
        d1_strength=100,
        h4_strength=100,
    )

    zone = Zone(
        direction=Direction.BUY,
        timeframe="H1+M15",

        low=99,
        high=101,

        h1_strength=100,
        m15_strength=100,

        kind="SUPPORT",

        structure_confirmed=True,
        liquidity_nearby=True,
        order_block=True,
        fvg=True,
    )

    confirmation = Confirmation(
        direction=Direction.BUY,

        retest=True,

        rejection=True,

        liquidity_sweep=True,

        micro_bos=True,

        candle_confirmation=True,
    )

    return (
        trend,
        zone,
        confirmation,
    )


def test_rr():

    rr = calculate_rr(
        entry=100,
        stop_loss=98,
        take_profit=104,
    )

    assert rr == 2.0


def test_threshold():

    assert should_send_signal(
        60
    )

    assert not should_send_signal(
        59.99
    )


def test_score_can_reach_100():

    trend, zone, confirmation = (
        create_test_components()
    )

    score = calculate_score(
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        rr=2.0,
        spread_ok=True,
        session_ok=True,
    )

    assert score == 100.0


def test_signal_generated_at_60_plus():

    trend, zone, confirmation = (
        create_test_components()
    )

    signal = build_signal(
        symbol="EUR/USD",

        trend=trend,

        zone=zone,

        confirmation=confirmation,

        entry=100,

        stop_loss=98,

        take_profit=104,

        spread_ok=True,

        session_ok=True,
    )

    assert signal is not None

    assert signal.score >= 60


def test_tracker():

    trend, zone, confirmation = (
        create_test_components()
    )

    signal = build_signal(
        symbol="EUR/USD",

        trend=trend,

        zone=zone,

        confirmation=confirmation,

        entry=100,

        stop_loss=98,

        take_profit=104,
    )

    assert signal is not None

    tracker = SignalTracker()

    tracker.register(signal)

    state = tracker.update(
        signal.signal_id,
        102,
    )

    assert state.current_r == 1.0

    assert (
        state.status.value
        == "BE_RECOMMENDED"
    )

    tracker.activate_be(
        signal.signal_id
    )

    assert (
        state.status.value
        == "BE_ACTIVE"
    )

    assert state.be_price == 100