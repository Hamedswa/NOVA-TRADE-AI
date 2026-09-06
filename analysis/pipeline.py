"""
NOVA TRADE AI
analysis/pipeline.py

PIPELINE PRINCIPAL

Architecture :

    D1 + H4
        ↓
    TENDANCE
        ↓
    H1 + M15
        ↓
    STRUCTURE / ZONE
        ↓
    M5
        ↓
    CONFIRMATION
        ↓
    SCORE
        ↓
    RR / SL / TP
        ↓
    DECISION

Important :
- Aucun ordre réel n'est exécuté ici.
- Les annonces économiques ne sont pas intégrées pour le moment.
- M5 peut être NON CONFIRMED sans mettre automatiquement le score à 0.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.models import (
    Candle,
    Confirmation,
    Direction,
    TrendContext,
    Zone,
)

from analysis.trend import (
    detect_direction_from_structure,
    build_trend_context,
)

from market_data import get_candles

from scoring.score_engine import (
    calculate_score,
    score_label,
    should_send_signal,
)


# ============================================================
# CONFIGURATION
# ============================================================

ATR_PERIOD = 14

SWING_LOOKBACK = 2

M5_STRUCTURE_LOOKBACK = 8

SL_ATR_MULTIPLIER = 1.5

MIN_RR = 2.0

MIN_ZONE_STRENGTH = 35.0


# ============================================================
# OUTILS CANDLE
# ============================================================

def _candle_value(
    candle: Any,
    field: str,
    default: float = 0.0,
) -> float:
    """
    Compatible avec :
    - Candle dataclass
    - dictionnaire
    """

    if candle is None:
        return float(default)

    if isinstance(candle, dict):
        value = candle.get(field, default)
    else:
        value = getattr(candle, field, default)

    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _closes(candles: List[Any]) -> List[float]:
    return [
        _candle_value(c, "close")
        for c in candles
    ]


def _highs(candles: List[Any]) -> List[float]:
    return [
        _candle_value(c, "high")
        for c in candles
    ]


def _lows(candles: List[Any]) -> List[float]:
    return [
        _candle_value(c, "low")
        for c in candles
    ]


# ============================================================
# SWINGS
# ============================================================

def detect_swing_highs(
    candles: List[Any],
    lookback: int = SWING_LOOKBACK,
) -> List[float]:

    highs = _highs(candles)

    if len(highs) < (lookback * 2 + 1):
        return []

    swings = []

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


def detect_swing_lows(
    candles: List[Any],
    lookback: int = SWING_LOOKBACK,
) -> List[float]:

    lows = _lows(candles)

    if len(lows) < (lookback * 2 + 1):
        return []

    swings = []

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
# STRENGTH STRUCTURE
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

    total = bullish + bearish

    if total == 0:
        return 0.0

    dominant = max(
        bullish,
        bearish,
    )

    strength = (
        dominant
        / total
        * 100.0
    )

    return round(
        min(100.0, strength),
        2,
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles: List[Any],
    period: int = ATR_PERIOD,
) -> float:

    if len(candles) < period + 1:
        return 0.0

    trs = []

    for i in range(
        1,
        len(candles),
    ):

        current = candles[i]
        previous = candles[i - 1]

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
            abs(high - previous_close),
            abs(low - previous_close),
        )

        trs.append(true_range)

    if len(trs) < period:
        return 0.0

    return sum(
        trs[-period:]
    ) / period


# ============================================================
# ZONE
# ============================================================

def build_zone(
    direction: Direction,
    h1_candles: List[Any],
    m15_candles: List[Any],
) -> Zone:

    h1_strength = calculate_structure_strength(
        h1_candles
    )

    m15_strength = calculate_structure_strength(
        m15_candles
    )

    all_prices = (
        _highs(h1_candles)
        + _lows(h1_candles)
        + _highs(m15_candles)
        + _lows(m15_candles)
    )

    if not all_prices:

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

    zone_low = min(all_prices)
    zone_high = max(all_prices)

    structure_confirmed = (
        direction != Direction.NEUTRAL
        and h1_strength >= MIN_ZONE_STRENGTH
        and m15_strength >= MIN_ZONE_STRENGTH
    )

    return Zone(
        direction=direction,
        timeframe="H1/M15",
        low=zone_low,
        high=zone_high,
        h1_strength=h1_strength,
        m15_strength=m15_strength,
        structure_confirmed=structure_confirmed,
        liquidity_nearby=True,
        order_block=False,
        fvg=False,
        kind="STRUCTURE",
    )


# ============================================================
# M5 : BOUGIE
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

    # BUY
    if direction == Direction.BUY:

        bullish_current = (
            current_close
            > current_open
        )

        bullish_previous = (
            previous_close
            >= previous_open
        )

        return (
            bullish_current
            and body_ratio >= 0.45
            and (
                current_close
                > previous_high
                if (
                    previous_high := _candle_value(
                        previous,
                        "high",
                    )
                )
                else False
            )
            or (
                bullish_current
                and bullish_previous
                and body_ratio >= 0.55
            )
        )

    # SELL
    if direction == Direction.SELL:

        bearish_current = (
            current_close
            < current_open
        )

        bearish_previous = (
            previous_close
            <= previous_open
        )

        return (
            bearish_current
            and body_ratio >= 0.45
            and (
                current_close
                < (
                    _candle_value(
                        previous,
                        "low",
                    )
                )
            )
            or (
                bearish_current
                and bearish_previous
                and body_ratio >= 0.55
            )
        )

    return False


# ============================================================
# M5 : MICRO BOS
# ============================================================

def detect_micro_bos(
    candles: List[Any],
    direction: Direction,
    lookback: int = M5_STRUCTURE_LOOKBACK,
) -> bool:

    if len(candles) < lookback + 2:
        return False

    recent = candles[-lookback - 1:]

    previous = recent[:-1]
    current = recent[-1]

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

        return current_close > previous_high

    if direction == Direction.SELL:

        return current_close < previous_low

    return False


# ============================================================
# M5 : LIQUIDITY SWEEP
# ============================================================

def detect_liquidity_sweep(
    candles: List[Any],
    direction: Direction,
    lookback: int = M5_STRUCTURE_LOOKBACK,
) -> bool:

    if len(candles) < lookback + 2:
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

    # BUY :
    # sweep sous le low puis clôture au-dessus
    if direction == Direction.BUY:

        return (
            current_low < previous_low
            and current_close > previous_low
        )

    # SELL :
    # sweep au-dessus du high puis clôture en-dessous
    if direction == Direction.SELL:

        return (
            current_high > previous_high
            and current_close < previous_high
        )

    return False


# ============================================================
# M5 : REJECTION
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

    candle_range = high - low

    if candle_range <= 0:
        return False

    body = abs(
        close - open_price
    )

    upper_wick = (
        high
        - max(open_price, close)
    )

    lower_wick = (
        min(open_price, close)
        - low
    )

    # BUY : rejet de la partie basse
    if direction == Direction.BUY:

        return (
            lower_wick >= body
            and lower_wick >= candle_range * 0.30
        )

    # SELL : rejet de la partie haute
    if direction == Direction.SELL:

        return (
            upper_wick >= body
            and upper_wick >= candle_range * 0.30
        )

    return False


# ============================================================
# M5 : RETEST
# ============================================================

def detect_retest(
    candles: List[Any],
    direction: Direction,
) -> bool:

    if len(candles) < 4:
        return False

    previous_candles = candles[-4:-1]
    current = candles[-1]

    current_close = _candle_value(
        current,
        "close",
    )

    previous_high = max(
        _highs(previous_candles)
    )

    previous_low = min(
        _lows(previous_candles)
    )

    current_low = _candle_value(
        current,
        "low",
    )

    current_high = _candle_value(
        current,
        "high",
    )

    # BUY :
    # le prix revient tester une zone basse
    if direction == Direction.BUY:

        return (
            current_low <= previous_high
            and current_close >= previous_low
        )

    # SELL :
    # le prix revient tester une zone haute
    if direction == Direction.SELL:

        return (
            current_high >= previous_low
            and current_close <= previous_high
        )

    return False


# ============================================================
# CONFIRMATION M5
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


def confirmation_valid(
    confirmation: Confirmation,
) -> bool:

    # Confirmation forte :
    # BOS + bougie
    if (
        confirmation.micro_bos
        and confirmation.candle_confirmation
    ):
        return True

    # Alternative :
    # sweep + rejet + bougie
    if (
        confirmation.liquidity_sweep
        and confirmation.rejection
        and confirmation.candle_confirmation
    ):
        return True

    # Alternative plus prudente :
    # retest + rejet + bougie
    if (
        confirmation.retest
        and confirmation.rejection
        and confirmation.candle_confirmation
    ):
        return True

    return False


# ============================================================
# NIVEAUX DE TRADE
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

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    if entry <= 0:
        return (
            entry,
            None,
            None,
            0.0,
        )

    if atr <= 0:
        return (
            entry,
            None,
            None,
            0.0,
        )

    risk_distance = (
        atr
        * SL_ATR_MULTIPLIER
    )

    if direction == Direction.BUY:

        sl = entry - risk_distance

        tp = entry + (
            risk_distance
            * MIN_RR
        )

    elif direction == Direction.SELL:

        sl = entry + risk_distance

        tp = entry - (
            risk_distance
            * MIN_RR
        )

    else:

        return (
            entry,
            None,
            None,
            0.0,
        )

    if direction == Direction.BUY:

        reward = tp - entry
        risk = entry - sl

    else:

        reward = entry - tp
        risk = sl - entry

    if risk <= 0:
        return (
            entry,
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
# DÉCISION
# ============================================================

def determine_status(
    direction: Direction,
    score: float,
    confirmation: Confirmation,
    rr: float,
) -> Tuple[str, str]:

    if direction == Direction.NEUTRAL:

        return (
            "REJECT",
            "Aucune direction multi-timeframe valide.",
        )

    if rr < MIN_RR:

        return (
            "REJECT",
            f"RR insuffisant : {rr:.2f}. "
            f"Minimum requis : {MIN_RR:.2f}.",
        )

    if not confirmation_valid(
        confirmation
    ):

        return (
            "REJECT",
            "La confirmation M5 complète "
            "n'est pas validée.",
        )

    if not should_send_signal(
        score,
        threshold=60.0,
    ):

        return (
            "REJECT",
            f"Score insuffisant : "
            f"{score:.2f}/100.",
        )

    return (
        "ACTIVE",
        "Setup validé par le pipeline "
        "multi-timeframe.",
    )


# ============================================================
# ANALYSE PRINCIPALE
# ============================================================

def analyze_market(
    symbol: str,
) -> Dict[str, Any]:

    # --------------------------------------------------------
    # 1. RÉCUPÉRATION DES DONNÉES
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Vérification
    # --------------------------------------------------------

    if not d1:
        raise RuntimeError(
            f"Aucune donnée D1 disponible pour {symbol}."
        )

    if not h4:
        raise RuntimeError(
            f"Aucune donnée H4 disponible pour {symbol}."
        )

    if not h1:
        raise RuntimeError(
            f"Aucune donnée H1 disponible pour {symbol}."
        )

    if not m15:
        raise RuntimeError(
            f"Aucune donnée M15 disponible pour {symbol}."
        )

    if not m5:
        raise RuntimeError(
            f"Aucune donnée M5 disponible pour {symbol}."
        )

    # --------------------------------------------------------
    # 2. TENDANCE D1 / H4
    # --------------------------------------------------------

    d1_direction = (
        determine_direction_from_candles(d1)
    )

    h4_direction = (
        determine_direction_from_candles(h4)
    )

    d1_strength = (
        calculate_structure_strength(d1)
    )

    h4_strength = (
        calculate_structure_strength(h4)
    )

    trend = build_trend_context(
        d1=d1_direction,
        h4=h4_direction,
        d1_strength=d1_strength,
        h4_strength=h4_strength,
    )

    # --------------------------------------------------------
    # 3. DIRECTION PRINCIPALE
    # --------------------------------------------------------

    direction = trend.direction

    # D1/H4 doivent être alignés
    trend_aligned = (
        d1_direction != Direction.NEUTRAL
        and h4_direction != Direction.NEUTRAL
        and d1_direction == h4_direction
    )

    # --------------------------------------------------------
    # 4. H1 / M15
    # --------------------------------------------------------

    h1_direction = (
        determine_direction_from_candles(h1)
    )

    m15_direction = (
        determine_direction_from_candles(m15)
    )

    # --------------------------------------------------------
    # Si D1/H4 sont alignés, H1/M15 doivent idéalement
    # suivre la même direction.
    # --------------------------------------------------------

    if trend_aligned:

        h1_confirms = (
            h1_direction == direction
        )

        m15_confirms = (
            m15_direction == direction
        )

    else:

        h1_confirms = False
        m15_confirms = False

    # --------------------------------------------------------
    # 5. ZONE
    # --------------------------------------------------------

    zone = build_zone(
        direction=direction,
        h1_candles=h1,
        m15_candles=m15,
    )

    # On renforce la confirmation structurelle
    zone.structure_confirmed = (
        trend_aligned
        and h1_confirms
        and m15_confirms
    )

    # --------------------------------------------------------
    # 6. M5 CONFIRMATION
    # --------------------------------------------------------

    confirmation = build_m5_confirmation(
        m5,
        direction,
    )

    m5_valid = confirmation_valid(
        confirmation
    )

    # --------------------------------------------------------
    # 7. NIVEAUX
    # --------------------------------------------------------

    (
        entry,
        sl,
        tp,
        rr,
    ) = calculate_trade_levels(
        m5,
        direction,
    )

    # --------------------------------------------------------
    # 8. SCORE
    #
    # IMPORTANT :
    # On calcule le score même si M5 n'est pas confirmé.
    # --------------------------------------------------------

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

    label = score_label(
        score
    )

    # --------------------------------------------------------
    # 9. STATUT
    # --------------------------------------------------------

    if not trend_aligned:

        status = "REJECT"

        reason = (
            "D1 et H4 ne sont pas alignés."
        )

    elif not h1_confirms:

        status = "REJECT"

        reason = (
            "H1 ne confirme pas la tendance "
            "D1/H4."
        )

    elif not m15_confirms:

        status = "REJECT"

        reason = (
            "M15 ne confirme pas la tendance "
            "D1/H4."
        )

    else:

        status, reason = determine_status(
            direction=direction,
            score=score,
            confirmation=confirmation,
            rr=rr,
        )

    # --------------------------------------------------------
    # 10. RETOUR COMPLET
    # --------------------------------------------------------

    return {
        "symbol": symbol,

        "direction": direction.value,

        "score": round(
            score,
            2,
        ),

        "quality": label,

        "status": status,

        "reason": reason,

        "trend": {
            "D1": d1_direction.value,
            "H4": h4_direction.value,
            "D1_strength": round(
                d1_strength,
                2,
            ),
            "H4_strength": round(
                h4_strength,
                2,
            ),
            "aligned": trend_aligned,
        },

        "zones": {
            "H1": h1_direction.value,
            "M15": m15_direction.value,
            "H1_strength": round(
                zone.h1_strength,
                2,
            ),
            "M15_strength": round(
                zone.m15_strength,
                2,
            ),
            "structure_confirmed":
                zone.structure_confirmed,
        },

        "confirmation": {
            "M5": (
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
        },

        "trade": {
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": rr,
        },

        "news": "NOT CHECKED",

        "execution": {
            "enabled": False,
        },
    }


# ============================================================
# COMPATIBILITÉ
# ============================================================

def analyser_marche(
    symbol: str = "XAU/USD",
    timeframe: str = "M15",
) -> Dict[str, Any]:
    """
    Compatibilité avec l'ancien système.

    Le nouveau pipeline reste multi-timeframe.
    Le paramètre timeframe est conservé pour
    éviter de casser les anciens appels.
    """

    return analyze_market(
        symbol
    )


def analyze(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:

    return analyze_market(
        symbol
    )