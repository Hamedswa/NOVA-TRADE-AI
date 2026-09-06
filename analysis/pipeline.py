"""
NOVA TRADE AI
Pipeline principal d'analyse multi-timeframe.

Architecture :
    D1 + H4  -> tendance globale
    H1 + M15 -> structure / contexte
    M5       -> confirmation
    Score    -> validation
    RR       -> validation

IMPORTANT :
    Ce module ne passe aucun ordre réel.
    Le filtre News est volontairement laissé de côté pour le moment.
"""

from __future__ import annotations

from typing import Any

from config import CONFIG
from market_data import get_candles

from core.models import (
    Direction,
    Zone,
    Confirmation,
)

from analysis.trend import (
    detect_direction_from_structure,
    build_trend_context,
)

from analysis.zones import calculate_zone_quality

from analysis.confirmation import (
    validate_m5_confirmation,
)

from scoring.score_engine import (
    calculate_score,
    should_send_signal,
)

from risk.risk_manager import calculate_rr


# ============================================================
# OUTILS GÉNÉRAUX
# ============================================================

def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(maximum, value),
    )


# ============================================================
# STRUCTURE DE MARCHÉ
# ============================================================

def _find_swing_points(
    candles,
    left: int = 2,
    right: int = 2,
):
    """
    Détecte les sommets et creux locaux.

    Un swing high est un sommet supérieur aux bougies
    qui l'entourent.

    Un swing low est un creux inférieur aux bougies
    qui l'entourent.
    """

    swing_highs = []
    swing_lows = []

    if len(candles) < left + right + 1:
        return swing_highs, swing_lows

    for i in range(
        left,
        len(candles) - right,
    ):

        current = candles[i]

        left_highs = [
            candles[j].high
            for j in range(
                i - left,
                i,
            )
        ]

        right_highs = [
            candles[j].high
            for j in range(
                i + 1,
                i + right + 1,
            )
        ]

        left_lows = [
            candles[j].low
            for j in range(
                i - left,
                i,
            )
        ]

        right_lows = [
            candles[j].low
            for j in range(
                i + 1,
                i + right + 1,
            )
        ]

        if (
            current.high > max(left_highs)
            and current.high > max(right_highs)
        ):
            swing_highs.append(current.high)

        if (
            current.low < min(left_lows)
            and current.low < min(right_lows)
        ):
            swing_lows.append(current.low)

    return swing_highs, swing_lows


def _count_structure(
    candles,
):
    """
    Compte les HH, HL, LH et LL.

    On compare les derniers swings entre eux.
    """

    swing_highs, swing_lows = _find_swing_points(
        candles
    )

    higher_highs = 0
    lower_highs = 0
    higher_lows = 0
    lower_lows = 0

    if len(swing_highs) >= 2:

        for previous, current in zip(
            swing_highs[:-1],
            swing_highs[1:],
        ):

            if current > previous:
                higher_highs += 1

            elif current < previous:
                lower_highs += 1

    if len(swing_lows) >= 2:

        for previous, current in zip(
            swing_lows[:-1],
            swing_lows[1:],
        ):

            if current > previous:
                higher_lows += 1

            elif current < previous:
                lower_lows += 1

    return {
        "higher_highs": higher_highs,
        "higher_lows": higher_lows,
        "lower_highs": lower_highs,
        "lower_lows": lower_lows,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
    }


def determine_direction_from_candles(
    candles,
) -> Direction:
    """
    Détermine la direction à partir de la structure
    HH / HL / LH / LL.

    La décision est confiée à detect_direction_from_structure()
    présente dans analysis.trend.
    """

    if len(candles) < 15:
        return Direction.NEUTRAL

    structure = _count_structure(
        candles
    )

    return detect_direction_from_structure(
        higher_highs=structure["higher_highs"],
        higher_lows=structure["higher_lows"],
        lower_highs=structure["lower_highs"],
        lower_lows=structure["lower_lows"],
    )


def calculate_structure_strength(
    candles,
    direction: Direction,
) -> float:
    """
    Calcule une force structurelle de 0 à 100.

    Plus les éléments HH/HL ou LH/LL sont nombreux et
    cohérents, plus la force augmente.
    """

    if direction == Direction.NEUTRAL:
        return 0.0

    structure = _count_structure(
        candles
    )

    bullish = (
        structure["higher_highs"]
        + structure["higher_lows"]
    )

    bearish = (
        structure["lower_highs"]
        + structure["lower_lows"]
    )

    total = bullish + bearish

    if total == 0:
        return 0.0

    if direction == Direction.BUY:

        favorable = bullish
        unfavorable = bearish

    else:

        favorable = bearish
        unfavorable = bullish

    ratio = favorable / total

    strength = 50.0 + (
        ratio * 50.0
    )

    return clamp(
        strength,
        0.0,
        100.0,
    )


# ============================================================
# CONFIRMATION M5
# ============================================================

def detect_retest(
    candles,
    direction: Direction,
) -> bool:

    if len(candles) < 6:
        return False

    previous = candles[-2]
    current = candles[-1]

    if direction == Direction.BUY:

        return (
            current.low <= previous.close
            and current.close > current.open
        )

    if direction == Direction.SELL:

        return (
            current.high >= previous.close
            and current.close < current.open
        )

    return False


def detect_rejection(
    candles,
    direction: Direction,
) -> bool:

    if not candles:
        return False

    candle = candles[-1]

    body = abs(
        candle.close - candle.open
    )

    if body <= 0:
        return False

    upper_wick = (
        candle.high
        - max(
            candle.open,
            candle.close,
        )
    )

    lower_wick = (
        min(
            candle.open,
            candle.close,
        )
        - candle.low
    )

    if direction == Direction.BUY:

        return (
            lower_wick >= body * 0.8
        )

    if direction == Direction.SELL:

        return (
            upper_wick >= body * 0.8
        )

    return False


def detect_liquidity_sweep(
    candles,
    direction: Direction,
) -> bool:

    if len(candles) < 10:
        return False

    current = candles[-1]

    reference = candles[-8:-1]

    if direction == Direction.BUY:

        liquidity_low = min(
            candle.low
            for candle in reference
        )

        return (
            current.low < liquidity_low
            and current.close > liquidity_low
        )

    if direction == Direction.SELL:

        liquidity_high = max(
            candle.high
            for candle in reference
        )

        return (
            current.high > liquidity_high
            and current.close < liquidity_high
        )

    return False


def detect_micro_bos(
    candles,
    direction: Direction,
) -> bool:

    if len(candles) < 6:
        return False

    current = candles[-1]

    reference = candles[-4:-1]

    if direction == Direction.BUY:

        reference_high = max(
            candle.high
            for candle in reference
        )

        return (
            current.close > reference_high
        )

    if direction == Direction.SELL:

        reference_low = min(
            candle.low
            for candle in reference
        )

        return (
            current.close < reference_low
        )

    return False


def detect_candle_confirmation(
    candles,
    direction: Direction,
) -> bool:

    if not candles:
        return False

    candle = candles[-1]

    if direction == Direction.BUY:
        return candle.close > candle.open

    if direction == Direction.SELL:
        return candle.close < candle.open

    return False


# ============================================================
# ZONE H1 + M15
# ============================================================

def build_zone(
    h1_candles,
    m15_candles,
    direction: Direction,
) -> Zone:

    h1_recent = h1_candles[-20:]
    m15_recent = m15_candles[-20:]

    h1_low = min(
        candle.low
        for candle in h1_recent
    )

    h1_high = max(
        candle.high
        for candle in h1_recent
    )

    m15_low = min(
        candle.low
        for candle in m15_recent
    )

    m15_high = max(
        candle.high
        for candle in m15_recent
    )

    # Intersection des zones H1/M15.
    low = max(
        h1_low,
        m15_low,
    )

    high = min(
        h1_high,
        m15_high,
    )

    # Si aucune intersection propre,
    # on utilise la zone M15.
    if low >= high:

        low = m15_low
        high = m15_high

    h1_structure = calculate_structure_strength(
        h1_candles,
        direction,
    )

    m15_structure = calculate_structure_strength(
        m15_candles,
        direction,
    )

    return Zone(
        direction=direction,
        timeframe="H1/M15",
        low=low,
        high=high,
        h1_strength=clamp(
            h1_structure,
            0.0,
            100.0,
        ),
        m15_strength=clamp(
            m15_structure,
            0.0,
            100.0,
        ),
        kind="SMC_CONTEXT",
        structure_confirmed=(
            h1_structure >= 50.0
            and m15_structure >= 50.0
        ),
        liquidity_nearby=True,
        order_block=True,
        fvg=True,
    )


# ============================================================
# NIVEAUX DE TRADE
# ============================================================

def calculate_trade_levels(
    candles,
    direction: Direction,
):

    if len(candles) < 10:
        return None, None, None

    current = candles[-1]

    entry = current.close

    recent = candles[-10:]

    if direction == Direction.BUY:

        structural_low = min(
            candle.low
            for candle in recent
        )

        risk = (
            entry
            - structural_low
        )

        if risk <= 0:
            return None, None, None

        stop_loss = structural_low

        take_profit = (
            entry
            + (
                risk
                * CONFIG.MINIMUM_RR
            )
        )

        return (
            entry,
            stop_loss,
            take_profit,
        )

    if direction == Direction.SELL:

        structural_high = max(
            candle.high
            for candle in recent
        )

        risk = (
            structural_high
            - entry
        )

        if risk <= 0:
            return None, None, None

        stop_loss = structural_high

        take_profit = (
            entry
            - (
                risk
                * CONFIG.MINIMUM_RR
            )
        )

        return (
            entry,
            stop_loss,
            take_profit,
        )

    return None, None, None


# ============================================================
# RÉPONSE STANDARD DE REJET
# ============================================================

def _reject_result(
    symbol: str,
    d1: Direction,
    h4: Direction,
    h1: Direction,
    m15: Direction,
    reason: str,
    score: float = 0.0,
    entry=None,
    stop_loss=None,
    take_profit=None,
    rr: float = 0.0,
    m5: str = "NOT CONFIRMED",
):
    return {
        "symbol": symbol,
        "direction": (
            "NO TRADE"
            if score == 0
            else (
                d1.value
                if d1 != Direction.NEUTRAL
                else h4.value
            )
        ),
        "score": round(
            score,
            2,
        ),
        "quality": (
            "NO SIGNAL"
            if score < 60
            else "C"
        ),
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr": round(
            rr,
            2,
        ),
        "d1": d1.value,
        "h4": h4.value,
        "h1": h1.value,
        "m15": m15.value,
        "m5": m5,
        "news_status": "NOT CHECKED",
        "status": "REJECT",
        "reason": reason,
    }


# ============================================================
# ANALYSE PRINCIPALE
# ============================================================

def analyze_market(
    symbol: str,
) -> dict[str, Any]:

    symbol = symbol.strip().upper()

    # --------------------------------------------------------
    # 1. DONNÉES MULTI-TIMEFRAME
    # --------------------------------------------------------

    d1 = get_candles(
        symbol,
        "D1",
        outputsize=100,
    )

    h4 = get_candles(
        symbol,
        "H4",
        outputsize=100,
    )

    h1 = get_candles(
        symbol,
        "H1",
        outputsize=100,
    )

    m15 = get_candles(
        symbol,
        "M15",
        outputsize=100,
    )

    m5 = get_candles(
        symbol,
        "M5",
        outputsize=100,
    )

    # --------------------------------------------------------
    # 2. TENDANCE D1 + H4
    # --------------------------------------------------------

    d1_direction = (
        determine_direction_from_candles(d1)
    )

    h4_direction = (
        determine_direction_from_candles(h4)
    )

    d1_strength = (
        calculate_structure_strength(
            d1,
            d1_direction,
        )
    )

    h4_strength = (
        calculate_structure_strength(
            h4,
            h4_direction,
        )
    )

    trend = build_trend_context(
        d1=d1_direction,
        h4=h4_direction,
        d1_strength=d1_strength,
        h4_strength=h4_strength,
    )

    direction = trend.direction

    # --------------------------------------------------------
    # D1 + H4 NON ALIGNÉS
    # --------------------------------------------------------

    if direction == Direction.NEUTRAL:

        return _reject_result(
            symbol=symbol,
            d1=d1_direction,
            h4=h4_direction,
            h1=Direction.NEUTRAL,
            m15=Direction.NEUTRAL,
            reason=(
                "D1 et H4 ne donnent pas "
                "une direction commune."
            ),
        )

    # --------------------------------------------------------
    # 3. STRUCTURE H1 + M15
    # --------------------------------------------------------

    h1_direction = (
        determine_direction_from_candles(h1)
    )

    m15_direction = (
        determine_direction_from_candles(m15)
    )

    # --------------------------------------------------------
    # H1 / M15 CONTRE LA TENDANCE
    # --------------------------------------------------------

    if (
        h1_direction != Direction.NEUTRAL
        and h1_direction != direction
    ):

        return _reject_result(
            symbol=symbol,
            d1=d1_direction,
            h4=h4_direction,
            h1=h1_direction,
            m15=m15_direction,
            reason=(
                "La structure H1 est opposée "
                "à la tendance D1/H4."
            ),
        )

    if (
        m15_direction != Direction.NEUTRAL
        and m15_direction != direction
    ):

        return _reject_result(
            symbol=symbol,
            d1=d1_direction,
            h4=h4_direction,
            h1=h1_direction,
            m15=m15_direction,
            reason=(
                "La structure M15 est opposée "
                "à la tendance D1/H4."
            ),
        )

    # --------------------------------------------------------
    # 4. ZONE H1 + M15
    # --------------------------------------------------------

    zone = build_zone(
        h1_candles=h1,
        m15_candles=m15,
        direction=direction,
    )

    zone_quality = calculate_zone_quality(
        zone
    )

    # --------------------------------------------------------
    # 5. CONFIRMATION M5
    # --------------------------------------------------------

    retest = detect_retest(
        m5,
        direction,
    )

    rejection = detect_rejection(
        m5,
        direction,
    )

    liquidity_sweep = detect_liquidity_sweep(
        m5,
        direction,
    )

    micro_bos = detect_micro_bos(
        m5,
        direction,
    )

    candle_confirmation = (
        detect_candle_confirmation(
            m5,
            direction,
        )
    )

    confirmation = validate_m5_confirmation(
        direction=direction,
        retest=retest,
        rejection=rejection,
        liquidity_sweep=liquidity_sweep,
        micro_bos=micro_bos,
        candle_confirmation=candle_confirmation,
    )

    # --------------------------------------------------------
    # 6. NIVEAUX ENTRY / SL / TP
    # --------------------------------------------------------

    entry, stop_loss, take_profit = (
        calculate_trade_levels(
            m5,
            direction,
        )
    )

    if entry is None:

        return _reject_result(
            symbol=symbol,
            d1=d1_direction,
            h4=h4_direction,
            h1=h1_direction,
            m15=m15_direction,
            reason=(
                "Impossible de construire "
                "un niveau SL/TP cohérent."
            ),
            m5=(
                "CONFIRMED"
                if confirmation.valid
                else "NOT CONFIRMED"
            ),
        )

    # --------------------------------------------------------
    # 7. RR
    # --------------------------------------------------------

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    # --------------------------------------------------------
    # 8. SCORE
    # --------------------------------------------------------

    score = calculate_score(
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        rr=rr,
        spread_ok=True,
        session_ok=True,
    )

    score = clamp(
        float(score),
        0.0,
        100.0,
    )

    # --------------------------------------------------------
    # 9. QUALITÉ
    # --------------------------------------------------------

    if score >= 90:
        quality = "A+"

    elif score >= 80:
        quality = "A"

    elif score >= 70:
        quality = "B"

    elif score >= 60:
        quality = "C"

    else:
        quality = "NO SIGNAL"

    # --------------------------------------------------------
    # 10. VALIDATION SCORE
    # --------------------------------------------------------

    valid_score = should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    )

    if not valid_score:

        return {
            "symbol": symbol,
            "direction": direction.value,
            "score": round(
                score,
                2,
            ),
            "quality": quality,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": round(
                rr,
                2,
            ),
            "d1": d1_direction.value,
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": (
                "CONFIRMED"
                if confirmation.valid
                else "NOT CONFIRMED"
            ),
            "news_status": "NOT CHECKED",
            "status": "REJECT",
            "reason": (
                f"Score insuffisant : "
                f"{score:.2f}/100 "
                f"(minimum "
                f"{CONFIG.SIGNAL_THRESHOLD})."
            ),
        }

    # --------------------------------------------------------
    # 11. VALIDATION RR
    # --------------------------------------------------------

    if rr < CONFIG.MINIMUM_RR:

        return {
            "symbol": symbol,
            "direction": direction.value,
            "score": round(
                score,
                2,
            ),
            "quality": quality,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": round(
                rr,
                2,
            ),
            "d1": d1_direction.value,
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": (
                "CONFIRMED"
                if confirmation.valid
                else "NOT CONFIRMED"
            ),
            "news_status": "NOT CHECKED",
            "status": "REJECT",
            "reason": (
                f"RR insuffisant : "
                f"{rr:.2f}. "
                f"Minimum requis : "
                f"{CONFIG.MINIMUM_RR:.2f}."
            ),
        }

    # --------------------------------------------------------
    # 12. VALIDATION M5
    # --------------------------------------------------------

    if not confirmation.valid:

        return {
            "symbol": symbol,
            "direction": direction.value,
            "score": round(
                score,
                2,
            ),
            "quality": quality,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": round(
                rr,
                2,
            ),
            "d1": d1_direction.value,
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": "NOT CONFIRMED",
            "news_status": "NOT CHECKED",
            "status": "REJECT",
            "reason": (
                "La confirmation M5 complète "
                "n'est pas validée."
            ),
        }

    # --------------------------------------------------------
    # 13. SIGNAL VALIDÉ
    # --------------------------------------------------------

    return {
        "symbol": symbol,
        "direction": direction.value,
        "score": round(
            score,
            2,
        ),
        "quality": quality,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr": round(
            rr,
            2,
        ),
        "d1": d1_direction.value,
        "h4": h4_direction.value,
        "h1": h1_direction.value,
        "m15": m15_direction.value,
        "m5": "CONFIRMED",
        "news_status": "NOT CHECKED",
        "status": "SIGNAL VALIDÉ",
        "reason": (
            "Tendance D1/H4 alignée, "
            "structure H1/M15 compatible, "
            "confirmation M5 validée "
            "et RR conforme."
        ),
    }