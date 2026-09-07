"""
NOVA TRADE AI
analysis/pipeline.py

PIPELINE MULTI-TIMEFRAME

D1 + H4
    ↓
TENDANCE GLOBALE

H1 + M15
    ↓
VALIDATION STRUCTURE / SETUP

D1 + H4 + H1 + M15
    ↓
ALIGNEMENT PRINCIPAL OBLIGATOIRE

M5
    ↓
CONFIRMATION SECONDAIRE
    ↓
NON BLOQUANTE

SL / TP
    ↓
RR
    ↓
SCORE
    ↓
HORAIRES DU MARCHÉ
    ↓
DECISION
    ↓
SIGNAL

Aucune exécution réelle d'ordre.

IMPORTANT :
M5 ne bloque jamais un setup lorsque
D1/H4/H1/M15 sont parfaitement alignés.

News économiques non intégrées pour le moment.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.models import (
    Confirmation,
    Direction,
    TrendContext,
    Zone,
)

from analysis.trend import (
    detect_direction_from_structure,
)

from market_data import get_candles

from market_hours import (
    is_market_open,
    is_market_closing_soon,
)

from scoring.score_engine import (
    calculate_score,
    score_label,
    should_send_signal,
)

from signals.signal_engine import build_signal


# ============================================================
# CONFIGURATION
# ============================================================

ATR_PERIOD = 14

SWING_LOOKBACK = 2

M5_STRUCTURE_LOOKBACK = 8

SL_ATR_MULTIPLIER = 1.5

MIN_RR = 2.0

SIGNAL_THRESHOLD = 60.0


# ============================================================
# OUTILS CANDLES
# ============================================================

def _candle_value(
    candle: Any,
    field: str,
    default: float = 0.0,
) -> float:

    if candle is None:
        return float(default)

    if isinstance(candle, dict):
        value = candle.get(
            field,
            default,
        )
    else:
        value = getattr(
            candle,
            field,
            default,
        )

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return float(default)


def _highs(
    candles: List[Any],
) -> List[float]:

    return [
        _candle_value(
            candle,
            "high",
        )
        for candle in candles
    ]


def _lows(
    candles: List[Any],
) -> List[float]:

    return [
        _candle_value(
            candle,
            "low",
        )
        for candle in candles
    ]


def _closes(
    candles: List[Any],
) -> List[float]:

    return [
        _candle_value(
            candle,
            "close",
        )
        for candle in candles
    ]


# ============================================================
# SWING HIGH
# ============================================================

def detect_swing_highs(
    candles: List[Any],
    lookback: int = SWING_LOOKBACK,
) -> List[float]:

    highs = _highs(candles)

    if len(highs) < (
        lookback * 2 + 1
    ):
        return []

    swings: List[float] = []

    for i in range(
        lookback,
        len(highs) - lookback,
    ):

        current = highs[i]

        left = highs[
            i - lookback:i
        ]

        right = highs[
            i + 1:i + lookback + 1
        ]

        if (
            current >= max(left)
            and current >= max(right)
        ):
            swings.append(current)

    return swings


# ============================================================
# SWING LOW
# ============================================================

def detect_swing_lows(
    candles: List[Any],
    lookback: int = SWING_LOOKBACK,
) -> List[float]:

    lows = _lows(candles)

    if len(lows) < (
        lookback * 2 + 1
    ):
        return []

    swings: List[float] = []

    for i in range(
        lookback,
        len(lows) - lookback,
    ):

        current = lows[i]

        left = lows[
            i - lookback:i
        ]

        right = lows[
            i + 1:i + lookback + 1
        ]

        if (
            current <= min(left)
            and current <= min(right)
        ):
            swings.append(current)

    return swings


# ============================================================
# STRUCTURE
# ============================================================

def _count_structure(
    candles: List[Any],
) -> Tuple[int, int, int, int]:

    highs = detect_swing_highs(candles)

    lows = detect_swing_lows(candles)

    higher_highs = 0
    lower_highs = 0

    higher_lows = 0
    lower_lows = 0

    if len(highs) >= 2:

        for previous, current in zip(
            highs[:-1],
            highs[1:],
        ):

            if current > previous:
                higher_highs += 1

            elif current < previous:
                lower_highs += 1

    if len(lows) >= 2:

        for previous, current in zip(
            lows[:-1],
            lows[1:],
        ):

            if current > previous:
                higher_lows += 1

            elif current < previous:
                lower_lows += 1

    return (
        higher_highs,
        higher_lows,
        lower_highs,
        lower_lows,
    )


def determine_direction_from_candles(
    candles: List[Any],
) -> Direction:

    (
        higher_highs,
        higher_lows,
        lower_highs,
        lower_lows,
    ) = _count_structure(candles)

    return detect_direction_from_structure(
        higher_highs,
        higher_lows,
        lower_highs,
        lower_lows,
    )


# ============================================================
# STRUCTURE STRENGTH
# ============================================================

def calculate_structure_strength(
    candles: List[Any],
) -> float:

    (
        higher_highs,
        higher_lows,
        lower_highs,
        lower_lows,
    ) = _count_structure(candles)

    bullish = (
        higher_highs
        + higher_lows
    )

    bearish = (
        lower_highs
        + lower_lows
    )

    total = (
        bullish
        + bearish
    )

    if total == 0:
        return 0.0

    dominant = max(
        bullish,
        bearish,
    )

    return round(
        min(
            100.0,
            dominant / total * 100.0,
        ),
        2,
    )


# ============================================================
# PRIMARY ALIGNMENT
# ============================================================

def is_primary_alignment_valid(
    d1: Direction,
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> bool:

    directions = (
        d1,
        h4,
        h1,
        m15,
    )

    if any(
        direction == Direction.NEUTRAL
        for direction in directions
    ):
        return False

    return (
        d1 == h4
        and h4 == h1
        and h1 == m15
    )


def determine_primary_direction(
    d1: Direction,
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> Direction:

    if not is_primary_alignment_valid(
        d1,
        h4,
        h1,
        m15,
    ):
        return Direction.NEUTRAL

    return d1


# ============================================================
# BUILD TREND CONTEXT
# ============================================================

def build_multitimeframe_context(
    d1_direction: Direction,
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
    d1_strength: float,
    h4_strength: float,
    h1_strength: float,
    m15_strength: float,
) -> TrendContext:
    """
    TrendContext reste volontairement limité à D1/H4.

    H1/M15 sont conservés séparément dans le pipeline
    car le modèle TrendContext actuel représente la tendance
    globale D1 + H4.

    L'alignement D1/H4/H1/M15 est validé séparément.
    """

    _ = (
        h1_direction,
        m15_direction,
        h1_strength,
        m15_strength,
    )

    return TrendContext(
        d1=d1_direction,
        h4=h4_direction,
        d1_strength=max(
            0.0,
            min(
                100.0,
                float(d1_strength),
            ),
        ),
        h4_strength=max(
            0.0,
            min(
                100.0,
                float(h4_strength),
            ),
        ),
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles: List[Any],
    period: int = ATR_PERIOD,
) -> float:

    if len(candles) < (
        period + 1
    ):
        return 0.0

    true_ranges: List[float] = []

    for i in range(
        1,
        len(candles),
    ):

        current = candles[i]

        previous = candles[
            i - 1
        ]

        high = _candle_value(
            current,
            "high",
        )

        low = _candle_value(
            current,
            "low",
        )

        previous_close = _candle_value(
            previous,
            "close",
        )

        true_range = max(
            high - low,
            abs(
                high
                - previous_close
            ),
            abs(
                low
                - previous_close
            ),
        )

        true_ranges.append(
            true_range
        )

    if len(true_ranges) < period:
        return 0.0

    return (
        sum(
            true_ranges[-period:]
        )
        / period
    )


# ============================================================
# ZONE
# ============================================================

def build_zone(
    direction: Direction,
    h1_candles: List[Any],
    m15_candles: List[Any],
    structure_confirmed: bool,
) -> Zone:

    h1_strength = calculate_structure_strength(
        h1_candles
    )

    m15_strength = calculate_structure_strength(
        m15_candles
    )

    h1_highs = _highs(
        h1_candles
    )

    h1_lows = _lows(
        h1_candles
    )

    m15_highs = _highs(
        m15_candles
    )

    m15_lows = _lows(
        m15_candles
    )

    all_highs = (
        h1_highs
        + m15_highs
    )

    all_lows = (
        h1_lows
        + m15_lows
    )

    if not all_highs or not all_lows:

        return Zone(
            direction=direction,
            timeframe="H1/M15",
            low=0.0,
            high=0.0,
            h1_strength=h1_strength,
            m15_strength=m15_strength,
            structure_confirmed=False,
            liquidity_nearby=False,
            order_block=False,
            fvg=False,
            kind="NONE",
        )

    zone_low = min(
        all_lows
    )

    zone_high = max(
        all_highs
    )

    return Zone(
        direction=direction,
        timeframe="H1/M15",
        low=zone_low,
        high=zone_high,
        h1_strength=h1_strength,
        m15_strength=m15_strength,
        structure_confirmed=(
            structure_confirmed
        ),
        liquidity_nearby=True,
        order_block=False,
        fvg=False,
        kind="STRUCTURE",
    )


# ============================================================
# M5 BOUGIE
# ============================================================

def detect_candle_confirmation(
    candles: List[Any],
    direction: Direction,
) -> bool:

    if len(candles) < 2:
        return False

    previous = candles[-2]
    current = candles[-1]

    previous_open = _candle_value(
        previous,
        "open",
    )

    previous_close = _candle_value(
        previous,
        "close",
    )

    previous_high = _candle_value(
        previous,
        "high",
    )

    previous_low = _candle_value(
        previous,
        "low",
    )

    current_open = _candle_value(
        current,
        "open",
    )

    current_close = _candle_value(
        current,
        "close",
    )

    current_high = _candle_value(
        current,
        "high",
    )

    current_low = _candle_value(
        current,
        "low",
    )

    current_range = (
        current_high
        - current_low
    )

    if current_range <= 0:
        return False

    current_body = abs(
        current_close
        - current_open
    )

    body_ratio = (
        current_body
        / current_range
    )

    if direction == Direction.BUY:

        bullish = (
            current_close
            > current_open
        )

        breakout = (
            current_close
            > previous_high
        )

        strong_body = (
            body_ratio >= 0.45
        )

        two_bullish = (
            previous_close
            >= previous_open
            and bullish
            and body_ratio >= 0.55
        )

        return (
            bullish
            and strong_body
            and (
                breakout
                or two_bullish
            )
        )

    if direction == Direction.SELL:

        bearish = (
            current_close
            < current_open
        )

        breakout = (
            current_close
            < previous_low
        )

        strong_body = (
            body_ratio >= 0.45
        )

        two_bearish = (
            previous_close
            <= previous_open
            and bearish
            and body_ratio >= 0.55
        )

        return (
            bearish
            and strong_body
            and (
                breakout
                or two_bearish
            )
        )

    return False


# ============================================================
# M5 MICRO BOS
# ============================================================

def detect_micro_bos(
    candles: List[Any],
    direction: Direction,
    lookback: int = M5_STRUCTURE_LOOKBACK,
) -> bool:

    if len(candles) < (
        lookback + 2
    ):
        return False

    previous = candles[
        -lookback - 1:-1
    ]

    current = candles[-1]

    current_close = _candle_value(
        current,
        "close",
    )

    previous_high = max(
        _highs(previous)
    )

    previous_low = min(
        _lows(previous)
    )

    if direction == Direction.BUY:

        return (
            current_close
            > previous_high
        )

    if direction == Direction.SELL:

        return (
            current_close
            < previous_low
        )

    return False


# ============================================================
# M5 LIQUIDITY SWEEP
# ============================================================

def detect_liquidity_sweep(
    candles: List[Any],
    direction: Direction,
    lookback: int = M5_STRUCTURE_LOOKBACK,
) -> bool:

    if len(candles) < (
        lookback + 2
    ):
        return False

    previous = candles[
        -lookback - 1:-1
    ]

    current = candles[-1]

    previous_high = max(
        _highs(previous)
    )

    previous_low = min(
        _lows(previous)
    )

    current_high = _candle_value(
        current,
        "high",
    )

    current_low = _candle_value(
        current,
        "low",
    )

    current_close = _candle_value(
        current,
        "close",
    )

    if direction == Direction.BUY:

        return (
            current_low
            < previous_low
            and current_close
            > previous_low
        )

    if direction == Direction.SELL:

        return (
            current_high
            > previous_high
            and current_close
            < previous_high
        )

    return False


# ============================================================
# M5 REJECTION
# ============================================================

def detect_rejection(
    candles: List[Any],
    direction: Direction,
) -> bool:

    if not candles:
        return False

    candle = candles[-1]

    open_price = _candle_value(
        candle,
        "open",
    )

    high = _candle_value(
        candle,
        "high",
    )

    low = _candle_value(
        candle,
        "low",
    )

    close = _candle_value(
        candle,
        "close",
    )

    candle_range = (
        high - low
    )

    if candle_range <= 0:
        return False

    body = abs(
        close - open_price
    )

    upper_wick = (
        high
        - max(
            open_price,
            close,
        )
    )

    lower_wick = (
        min(
            open_price,
            close,
        )
        - low
    )

    if direction == Direction.BUY:

        return (
            lower_wick >= body
            and lower_wick
            >= candle_range * 0.30
        )

    if direction == Direction.SELL:

        return (
            upper_wick >= body
            and upper_wick
            >= candle_range * 0.30
        )

    return False


# ============================================================
# M5 RETEST
# ============================================================

def detect_retest(
    candles: List[Any],
    direction: Direction,
) -> bool:

    if len(candles) < 4:
        return False

    previous = candles[-4:-1]

    current = candles[-1]

    previous_high = max(
        _highs(previous)
    )

    previous_low = min(
        _lows(previous)
    )

    current_high = _candle_value(
        current,
        "high",
    )

    current_low = _candle_value(
        current,
        "low",
    )

    current_close = _candle_value(
        current,
        "close",
    )

    if direction == Direction.BUY:

        return (
            current_low
            <= previous_high
            and current_close
            >= previous_low
        )

    if direction == Direction.SELL:

        return (
            current_high
            >= previous_low
            and current_close
            <= previous_high
        )

    return False


# ============================================================
# BUILD M5 CONFIRMATION
# ============================================================

def build_m5_confirmation(
    candles: List[Any],
    direction: Direction,
) -> Confirmation:

    if direction == Direction.NEUTRAL:

        return Confirmation(
            direction=Direction.NEUTRAL,
            retest=False,
            rejection=False,
            liquidity_sweep=False,
            micro_bos=False,
            candle_confirmation=False,
        )

    retest = detect_retest(
        candles,
        direction,
    )

    rejection = detect_rejection(
        candles,
        direction,
    )

    liquidity_sweep = detect_liquidity_sweep(
        candles,
        direction,
    )

    micro_bos = detect_micro_bos(
        candles,
        direction,
    )

    candle_confirmation = detect_candle_confirmation(
        candles,
        direction,
    )

    return Confirmation(
        direction=direction,
        retest=retest,
        rejection=rejection,
        liquidity_sweep=liquidity_sweep,
        micro_bos=micro_bos,
        candle_confirmation=candle_confirmation,
    )


# ============================================================
# VALIDATION M5
# ============================================================

def confirmation_valid(
    confirmation: Confirmation,
) -> bool:

    if (
        confirmation.micro_bos
        and confirmation.candle_confirmation
    ):
        return True

    if (
        confirmation.liquidity_sweep
        and confirmation.rejection
        and confirmation.candle_confirmation
    ):
        return True

    if (
        confirmation.retest
        and confirmation.rejection
        and confirmation.candle_confirmation
    ):
        return True

    return False


# ============================================================
# SL / TP / RR
# ============================================================

def calculate_trade_levels(
    candles: List[Any],
    direction: Direction,
) -> Tuple[
    float,
    Optional[float],
    Optional[float],
    float,
]:

    if not candles:

        return (
            0.0,
            None,
            None,
            0.0,
        )

    entry = _candle_value(
        candles[-1],
        "close",
    )

    if entry <= 0:

        return (
            entry,
            None,
            None,
            0.0,
        )

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    if atr <= 0:

        return (
            round(entry, 6),
            None,
            None,
            0.0,
        )

    risk_distance = (
        atr
        * SL_ATR_MULTIPLIER
    )

    if direction == Direction.BUY:

        sl = (
            entry
            - risk_distance
        )

        tp = (
            entry
            + risk_distance
            * MIN_RR
        )

    elif direction == Direction.SELL:

        sl = (
            entry
            + risk_distance
        )

        tp = (
            entry
            - risk_distance
            * MIN_RR
        )

    else:

        return (
            round(entry, 6),
            None,
            None,
            0.0,
        )

    if direction == Direction.BUY:

        risk = entry - sl
        reward = tp - entry

    else:

        risk = sl - entry
        reward = entry - tp

    if risk <= 0:

        return (
            round(entry, 6),
            None,
            None,
            0.0,
        )

    rr = reward / risk

    return (
        round(entry, 6),
        round(sl, 6),
        round(tp, 6),
        round(rr, 2),
    )


# ============================================================
# STATUS
# ============================================================

def determine_status(
    direction: Direction,
    score: float,
    confirmation: Confirmation,
    rr: float,
    setup_aligned: bool = False,
    market_open: bool = True,
    market_closing_soon: bool = False,
) -> Tuple[str, str]:

    if direction == Direction.NEUTRAL:

        return (
            "REJECT",
            "Aucune direction principale valide.",
        )

    if not setup_aligned:

        return (
            "REJECT",
            (
                "D1/H4/H1/M15 ne sont pas "
                "parfaitement alignés."
            ),
        )

    if not market_open:

        return (
            "REJECT",
            "Marché fermé. Aucun nouveau signal.",
        )

    if market_closing_soon:

        return (
            "REJECT",
            (
                "Marché proche de la fermeture. "
                "Nouveau signal bloqué."
            ),
        )

    if rr < MIN_RR:

        return (
            "REJECT",
            (
                f"RR insuffisant : "
                f"{rr:.2f}. "
                f"Minimum : {MIN_RR:.2f}."
            ),
        )

    if not should_send_signal(
        score,
        threshold=SIGNAL_THRESHOLD,
    ):

        return (
            "REJECT",
            (
                f"Score insuffisant : "
                f"{score:.2f}/100."
            ),
        )

    if confirmation_valid(
        confirmation
    ):

        return (
            "ACTIVE",
            (
                "Setup D1/H4/H1/M15 validé "
                "avec confirmation M5."
            ),
        )

    return (
        "ACTIVE",
        (
            "Setup D1/H4/H1/M15 validé. "
            "M5 non confirmé mais non bloquant."
        ),
    )


# ============================================================
# ANALYSE PRINCIPALE
# ============================================================

def analyze_market(
    symbol: str,
) -> Dict[str, Any]:

    # ========================================================
    # 1. DONNÉES MULTI-TIMEFRAME
    # ========================================================

    d1 = get_candles(
        symbol,
        "D1",
    )

    h4 = get_candles(
        symbol,
        "H4",
    )

    h1 = get_candles(
        symbol,
        "H1",
    )

    m15 = get_candles(
        symbol,
        "M15",
    )

    m5 = get_candles(
        symbol,
        "M5",
    )

    if not d1:
        raise RuntimeError(
            f"Aucune donnée D1 pour {symbol}."
        )

    if not h4:
        raise RuntimeError(
            f"Aucune donnée H4 pour {symbol}."
        )

    if not h1:
        raise RuntimeError(
            f"Aucune donnée H1 pour {symbol}."
        )

    if not m15:
        raise RuntimeError(
            f"Aucune donnée M15 pour {symbol}."
        )

    if not m5:
        raise RuntimeError(
            f"Aucune donnée M5 pour {symbol}."
        )

    # ========================================================
    # 2. D1
    # ========================================================

    d1_direction = determine_direction_from_candles(d1)

    d1_strength = calculate_structure_strength(d1)

    # ========================================================
    # 3. H4
    # ========================================================

    h4_direction = determine_direction_from_candles(h4)

    h4_strength = calculate_structure_strength(h4)

    # ========================================================
    # 4. H1
    # ========================================================

    h1_direction = determine_direction_from_candles(h1)

    h1_strength = calculate_structure_strength(h1)

    # ========================================================
    # 5. M15
    # ========================================================

    m15_direction = determine_direction_from_candles(m15)

    m15_strength = calculate_structure_strength(m15)

    # ========================================================
    # 6. CONTEXTE GLOBAL
    #
    # TrendContext = D1 + H4
    #
    # H1/M15 restent disponibles séparément.
    # ========================================================

    trend = build_multitimeframe_context(
        d1_direction=d1_direction,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
        d1_strength=d1_strength,
        h4_strength=h4_strength,
        h1_strength=h1_strength,
        m15_strength=m15_strength,
    )

    # ========================================================
    # 7. ALIGNEMENT PRINCIPAL
    #
    # D1 = H4 = H1 = M15
    # ========================================================

    setup_aligned = is_primary_alignment_valid(
        d1=d1_direction,
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
    )

    # ========================================================
    # 8. DIRECTION PRINCIPALE
    # ========================================================

    direction = determine_primary_direction(
        d1=d1_direction,
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
    )

    # ========================================================
    # 9. ZONE H1/M15
    # ========================================================

    zone = build_zone(
        direction=direction,
        h1_candles=h1,
        m15_candles=m15,
        structure_confirmed=setup_aligned,
    )

    # ========================================================
    # 10. M5
    #
    # Confirmation secondaire uniquement.
    # ========================================================

    confirmation = build_m5_confirmation(
        m5,
        direction,
    )

    m5_valid = confirmation_valid(
        confirmation
    )

    # ========================================================
    # 11. SL / TP / RR
    # ========================================================

    (
        entry,
        sl,
        tp,
        rr,
    ) = calculate_trade_levels(
        m5,
        direction,
    )

    # ========================================================
    # 12. SCORE
    # ========================================================

    if direction == Direction.NEUTRAL:

        score = 0.0

    else:

        score = calculate_score(
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            rr=rr,
            spread_ok=True,
            session_ok=True,
        )

    score = round(
        score,
        2,
    )

    quality = score_label(score)

    # ========================================================
    # 13. HORAIRES
    # ========================================================

    market_open = is_market_open(
        symbol
    )

    market_closing_soon = (
        is_market_closing_soon(symbol)
        if market_open
        else False
    )

    # ========================================================
    # 14. STATUS
    # ========================================================

    status, reason = determine_status(
        direction=direction,
        score=score,
        confirmation=confirmation,
        rr=rr,
        setup_aligned=setup_aligned,
        market_open=market_open,
        market_closing_soon=market_closing_soon,
    )

    # ========================================================
    # 15. CRÉATION DU SIGNAL
    #
    # IMPORTANT :
    #
    # On transmet explicitement D1/H4/H1/M15
    # au signal_engine.
    #
    # M5 reste NON BLOQUANT.
    # ========================================================

    signal = None

    if (
        status == "ACTIVE"
        and setup_aligned
        and sl is not None
        and tp is not None
    ):

        signal = build_signal(
            symbol=symbol,
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            spread_ok=True,
            session_ok=True,

            # SOURCE DE VÉRITÉ
            d1_direction=d1_direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

        if signal is None:

            status = "REJECT"

            reason = (
                "Échec de la validation finale "
                "du moteur de signal."
            )

    # ========================================================
    # 16. RESULTAT
    # ========================================================

    return {

        "symbol":
            symbol,

        "direction":
            direction.value,

        "score":
            score,

        "quality":
            quality,

        "status":
            status,

        "reason":
            reason,

        "signal":
            signal,

        # ====================================================
        # MULTI-TIMEFRAME
        # ====================================================

        "trend": {

            "D1":
                d1_direction.value,

            "H4":
                h4_direction.value,

            "H1":
                h1_direction.value,

            "M15":
                m15_direction.value,

            "D1_strength":
                d1_strength,

            "H4_strength":
                h4_strength,

            "H1_strength":
                h1_strength,

            "M15_strength":
                m15_strength,

            "aligned":
                setup_aligned,
        },

        # ====================================================
        # ZONE
        # ====================================================

        "zones": {

            "H1":
                h1_direction.value,

            "M15":
                m15_direction.value,

            "H1_strength":
                zone.h1_strength,

            "M15_strength":
                zone.m15_strength,

            "structure_confirmed":
                zone.structure_confirmed,

            "setup_aligned":
                setup_aligned,
        },

        # ====================================================
        # M5
        # ====================================================

        "confirmation": {

            "M5":
                (
                    "CONFIRMED"
                    if m5_valid
                    else "NOT CONFIRMED"
                ),

            "retest":
                confirmation.retest,

            "rejection":
                confirmation.rejection,

            "liquidity_sweep":
                confirmation.liquidity_sweep,

            "micro_bos":
                confirmation.micro_bos,

            "candle_confirmation":
                confirmation.candle_confirmation,

            "valid":
                m5_valid,

            "blocking":
                False,
        },

        # ====================================================
        # TRADE
        # ====================================================

        "trade": {

            "entry":
                entry,

            "sl":
                sl,

            "tp":
                tp,

            "rr":
                rr,
        },

        # ====================================================
        # MARKET
        # ====================================================

        "market": {

            "open":
                market_open,

            "closing_soon":
                market_closing_soon,

            "status":
                (
                    "CLOSING_SOON"
                    if market_closing_soon
                    else (
                        "OPEN"
                        if market_open
                        else "CLOSED"
                    )
                ),
        },

        # ====================================================
        # NEWS
        # ====================================================

        "news":
            "NOT CHECKED",

        # ====================================================
        # EXECUTION
        # ====================================================

        "execution": {

            "enabled":
                False,
        },
    }


# ============================================================
# COMPATIBILITÉ ANCIEN SYSTÈME
# ============================================================

def analyser_marche(
    symbol: str = "XAU/USD",
    timeframe: str = "M15",
) -> Dict[str, Any]:

    return analyze_market(
        symbol
    )


def analyze(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:

    return analyze_market(
        symbol
    )