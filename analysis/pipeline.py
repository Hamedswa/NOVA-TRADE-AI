"""
NOVA TRADE AI
analysis/pipeline.py

Pipeline principal d'analyse multi-timeframe.

Architecture :

H4
 ↓
TENDANCE GLOBALE

H1
 ↓
STRUCTURE PRINCIPALE

M15
 ↓
CONTEXTE / ZONES / LIQUIDITÉ

H4 + H1 + M15
 ↓
VALIDATION PRINCIPALE

M5
 ↓
CONFIRMATION SECONDAIRE
 ↓
NON BLOQUANTE

Score >= 60
RR >= 2
 ↓
SIGNAL
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from config import CONFIG
from core.models import (
    Candle,
    Direction,
    TrendContext,
    Zone,
    Confirmation,
)

from market_data import get_candles

from analysis.trend import (
    build_trend_context,
)

from analysis.structure import (
    analyze_structure,
)

from analysis.liquidity import (
    analyze_liquidity,
)

from analysis.displacement import (
    analyze_displacement,
)

from analysis.order_blocks import (
    analyze_order_blocks,
)

from analysis.fvg import (
    analyze_fvg,
)

from analysis.premium_discount import (
    analyze_premium_discount,
)

from analysis.support_resistance import (
    analyze_support_resistance,
)

from analysis.confirmation import (
    validate_m5_confirmation,
    confirmation_strength,
)

from scoring.scoring_engine import (
    calculate_score,
)

from risk.risk_manager import (
    calculate_rr,
)

from signals.signal_engine import (
    build_signal,
)


TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
)


TIMEFRAME_TO_API = {
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}


def _normalize_candle(candle: Any) -> Candle:
    """
    Convertit une donnée brute en Candle.
    """

    if isinstance(candle, Candle):
        return candle

    if isinstance(candle, dict):
        return Candle(
            timestamp=candle.get(
                "timestamp",
                candle.get("datetime"),
            ),
            open=float(candle["open"]),
            high=float(candle["high"]),
            low=float(candle["low"]),
            close=float(candle["close"]),
            volume=float(
                candle.get("volume", 0.0)
                or 0.0
            ),
        )

    return Candle(
        timestamp=getattr(
            candle,
            "timestamp",
            getattr(candle, "datetime", None),
        ),
        open=float(candle.open),
        high=float(candle.high),
        low=float(candle.low),
        close=float(candle.close),
        volume=float(
            getattr(candle, "volume", 0.0)
            or 0.0
        ),
    )


def _normalize_candles(
    candles: Any,
) -> list[Candle]:
    """
    Normalise une série complète de bougies.
    """

    if candles is None:
        return []

    return [
        _normalize_candle(candle)
        for candle in candles
    ]


def _calculate_atr(
    candles: list[Candle],
    period: int = 14,
) -> float:
    """
    Calcule l'ATR simple nécessaire au moteur
    de displacement.

    Aucun appel API.
    Aucun appel IA.
    """

    if not candles:
        return 0.0

    if len(candles) < 2:
        return 0.0

    true_ranges: list[float] = []

    for index in range(1, len(candles)):
        current = candles[index]
        previous = candles[index - 1]

        high = float(current.high)
        low = float(current.low)
        previous_close = float(
            previous.close
        )

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )

        true_ranges.append(
            max(0.0, true_range)
        )

    if not true_ranges:
        return 0.0

    selected = true_ranges[
        -max(1, period):
    ]

    return sum(selected) / len(selected)


def _normalize_direction(
    value: Any,
) -> Direction:
    """
    Convertit proprement une valeur en Direction.
    """

    if isinstance(value, Direction):
        return value

    if value is None:
        return Direction.NEUTRAL

    text = str(value).upper().strip()

    if text in {
        "BUY",
        "LONG",
        "BULLISH",
    }:
        return Direction.BUY

    if text in {
        "SELL",
        "SHORT",
        "BEARISH",
    }:
        return Direction.SELL

    return Direction.NEUTRAL


def resolve_direction(
    h4: Direction,
    h1: Direction,
    m15: Direction,
    requested_direction: Optional[
        Direction
    ] = None,
) -> Direction:
    """
    Détermine la direction finale.

    Priorité :

    1. Direction explicitement demandée
    2. H1 + M15
    3. H4 + H1
    4. H4 + M15
    5. H4
    6. H1
    7. M15
    8. NEUTRAL
    """

    h4 = _normalize_direction(h4)
    h1 = _normalize_direction(h1)
    m15 = _normalize_direction(m15)

    if requested_direction is not None:
        requested = _normalize_direction(
            requested_direction
        )

        if requested != Direction.NEUTRAL:
            return requested

    if (
        h1 != Direction.NEUTRAL
        and h1 == m15
    ):
        return h1

    if (
        h4 != Direction.NEUTRAL
        and h1 != Direction.NEUTRAL
        and h4 == h1
    ):
        return h4

    if (
        h4 != Direction.NEUTRAL
        and m15 != Direction.NEUTRAL
        and h4 == m15
    ):
        return h4

    if h4 != Direction.NEUTRAL:
        return h4

    if h1 != Direction.NEUTRAL:
        return h1

    if m15 != Direction.NEUTRAL:
        return m15

    return Direction.NEUTRAL


def _primary_alignment_valid(
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> bool:
    """
    Validation principale H4/H1/M15.

    Les trois timeframes ne doivent pas
    obligatoirement être identiques.

    Au moins une direction exploitable
    doit être disponible.
    """

    directions = (
        _normalize_direction(h4),
        _normalize_direction(h1),
        _normalize_direction(m15),
    )

    return any(
        direction != Direction.NEUTRAL
        for direction in directions
    )


def _determine_scenario(
    h4: Direction,
    h1: Direction,
    m15: Direction,
    direction: Direction,
    liquidity_sweep: bool = False,
    displacement: bool = False,
    bos: bool = False,
    choch: bool = False,
) -> str:
    """
    Détermine le scénario structurel.
    """

    h4 = _normalize_direction(h4)
    h1 = _normalize_direction(h1)
    m15 = _normalize_direction(m15)
    direction = _normalize_direction(direction)

    if (
        liquidity_sweep
        and displacement
        and (bos or choch)
    ):
        return "LIQUIDITY_REVERSAL"

    if (
        h4 != Direction.NEUTRAL
        and h1 != Direction.NEUTRAL
        and m15 != Direction.NEUTRAL
        and h4 == h1 == m15
    ):
        return "CONTINUATION"

    if (
        h4 != Direction.NEUTRAL
        and h1 != Direction.NEUTRAL
        and m15 != Direction.NEUTRAL
        and h4 == h1
        and m15 != h4
    ):
        return "CORRECTION"

    if (
        h4 != Direction.NEUTRAL
        and h1 != Direction.NEUTRAL
        and m15 != Direction.NEUTRAL
        and h4 != h1
        and m15 == h1
    ):
        return "POTENTIAL_REVERSAL"

    if (
        direction != Direction.NEUTRAL
        and h4 != Direction.NEUTRAL
        and direction != h4
        and h1 == direction
        and m15 == direction
    ):
        return "COUNTER_TREND"

    if choch:
        return "STRUCTURAL_REVERSAL"

    if bos:
        return "STRUCTURAL_CONTINUATION"

    if direction == Direction.BUY:
        return "SHORT_TERM_BULLISH"

    if direction == Direction.SELL:
        return "SHORT_TERM_BEARISH"

    return "RANGE"


def _extract_direction(
    result: Any,
) -> Direction:
    """
    Extrait la direction d'un résultat
    d'analyse.
    """

    if result is None:
        return Direction.NEUTRAL

    if isinstance(result, Direction):
        return result

    if isinstance(result, dict):
        for key in (
            "direction",
            "bias",
            "trend",
        ):
            if key in result:
                return _normalize_direction(
                    result[key]
                )

    for key in (
        "direction",
        "bias",
        "trend",
    ):
        if hasattr(result, key):
            return _normalize_direction(
                getattr(result, key)
            )

    return Direction.NEUTRAL


def _extract_strength(
    result: Any,
) -> float:
    """
    Extrait une force normalisée.
    """

    if result is None:
        return 0.0

    if isinstance(result, dict):
        for key in (
            "strength",
            "score",
            "confidence",
        ):
            if key in result:
                try:
                    return max(
                        0.0,
                        min(
                            100.0,
                            float(
                                result[key]
                            ),
                        ),
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    pass

    for key in (
        "strength",
        "score",
        "confidence",
    ):
        if hasattr(result, key):
            try:
                return max(
                    0.0,
                    min(
                        100.0,
                        float(
                            getattr(
                                result,
                                key,
                            )
                        ),
                    ),
                )
            except (
                TypeError,
                ValueError,
            ):
                pass

    return 0.0


def _extract_bool(
    result: Any,
    *keys: str,
) -> bool:
    """
    Extrait un booléen depuis un résultat.
    """

    if result is None:
        return False

    if isinstance(result, dict):
        return any(
            bool(result.get(key, False))
            for key in keys
        )

    return any(
        bool(
            getattr(
                result,
                key,
                False,
            )
        )
        for key in keys
    )


def _extract_bos(
    result: Any,
) -> bool:
    return _extract_bool(
        result,
        "bos",
        "break_of_structure",
        "has_bos",
    )


def _extract_choch(
    result: Any,
) -> bool:
    return _extract_bool(
        result,
        "choch",
        "change_of_character",
        "has_choch",
    )


def _build_zone(
    direction: Direction,
    sr_result: Any,
    ob_result: Any,
    fvg_result: Any,
) -> Optional[Zone]:
    """
    Construit la zone de trading.

    Priorité :

    1. Support / Résistance
    2. Order Block
    3. FVG
    """

    direction = _normalize_direction(
        direction
    )

    if sr_result is not None:
        sr = (
            sr_result
            if isinstance(
                sr_result,
                dict,
            )
            else getattr(
                sr_result,
                "best",
                sr_result,
            )
        )

        if isinstance(sr, dict):
            low = float(
                sr.get("low", 0.0)
                or 0.0
            )
            high = float(
                sr.get("high", 0.0)
                or 0.0
            )
            key_level = float(
                sr.get("key_level", 0.0)
                or sr.get("level", 0.0)
                or 0.0
            )

            if low > 0 and high > 0:
                return Zone(
                    direction=direction,
                    timeframe="M15",
                    low=low,
                    high=high,
                    h1_strength=0.0,
                    m15_strength=_extract_strength(
                        sr_result
                    ),
                    kind="SUPPORT_RESISTANCE",
                    structure_confirmed=True,
                    liquidity_nearby=False,
                    order_block=False,
                    fvg=False,
                    level_type=(
                        "SUPPORT"
                        if direction
                        == Direction.BUY
                        else "RESISTANCE"
                    ),
                    key_level=(
                        key_level
                        if key_level > 0
                        else (
                            low
                            if direction
                            == Direction.BUY
                            else high
                        )
                    ),
                )

    if ob_result is not None:
        ob = (
            ob_result
            if isinstance(
                ob_result,
                dict,
            )
            else getattr(
                ob_result,
                "best",
                ob_result,
            )
        )

        if isinstance(ob, dict):
            low = float(
                ob.get("low", 0.0)
                or 0.0
            )
            high = float(
                ob.get("high", 0.0)
                or 0.0
            )

            if low > 0 and high > 0:
                return Zone(
                    direction=direction,
                    timeframe="M15",
                    low=low,
                    high=high,
                    h1_strength=0.0,
                    m15_strength=_extract_strength(
                        ob_result
                    ),
                    kind="ORDER_BLOCK",
                    structure_confirmed=True,
                    liquidity_nearby=False,
                    order_block=True,
                    fvg=False,
                )

    if fvg_result is not None:
        fvg = (
            fvg_result
            if isinstance(
                fvg_result,
                dict,
            )
            else getattr(
                fvg_result,
                "best",
                fvg_result,
            )
        )

        if isinstance(fvg, dict):
            low = float(
                fvg.get("low", 0.0)
                or 0.0
            )
            high = float(
                fvg.get("high", 0.0)
                or 0.0
            )

            if low > 0 and high > 0:
                return Zone(
                    direction=direction,
                    timeframe="M15",
                    low=low,
                    high=high,
                    h1_strength=0.0,
                    m15_strength=_extract_strength(
                        fvg_result
                    ),
                    kind="FVG",
                    structure_confirmed=True,
                    liquidity_nearby=False,
                    order_block=False,
                    fvg=True,
                )

    return None


def _build_trade_geometry(
    direction: Direction,
    entry: float,
    zone: Optional[Zone],
    atr: float = 0.0,
) -> tuple[float, float, float]:
    """
    Construit Entry / SL / TP.

    RR minimum garanti à 2.
    """

    direction = _normalize_direction(
        direction
    )

    entry = float(entry)

    atr = max(
        0.0,
        float(atr or 0.0),
    )

    if atr <= 0:
        atr = max(
            abs(entry) * 0.001,
            0.01,
        )

    if zone is not None:
        if direction == Direction.BUY:
            stop_loss = min(
                zone.low,
                entry - atr,
            )
        else:
            stop_loss = max(
                zone.high,
                entry + atr,
            )
    else:
        if direction == Direction.BUY:
            stop_loss = entry - atr
        else:
            stop_loss = entry + atr

    risk_distance = abs(
        entry - stop_loss
    )

    minimum_rr = max(
        2.0,
        float(CONFIG.MINIMUM_RR),
    )

    reward_distance = (
        risk_distance * minimum_rr
    )

    if direction == Direction.BUY:
        take_profit = (
            entry + reward_distance
        )
    else:
        take_profit = (
            entry - reward_distance
        )

    return (
        entry,
        stop_loss,
        take_profit,
    )


def _calculate_final_score(
    h4: Any,
    h1: Any,
    m15: Any,
    m5: Any,
    liquidity: Any,
    displacement: Any,
    order_blocks: Any,
    fvg: Any,
    premium_discount: Any,
    support_resistance: Any,
    direction: Direction,
    rr: float,
    volatility_valid: bool = True,
) -> float:
    """
    Calcule le score final du setup.

    IMPORTANT :
    M5 est une confirmation secondaire
    et non bloquante.

    M5 ne reçoit des points que si une
    véritable confirmation est détectée.
    """

    h4_direction = _extract_direction(
        h4
    )

    h1_direction = _extract_direction(
        h1
    )

    m15_direction = _extract_direction(
        m15
    )

    m5_direction = _extract_direction(
        m5
    )

    liquidity_sweep = _extract_bool(
        liquidity,
        "sweep",
        "liquidity_sweep",
        "has_sweep",
    )

    liquidity_quality = (
        _extract_strength(liquidity)
        if liquidity_sweep
        else 0.0
    )

    displacement_detected = _extract_bool(
        displacement,
        "displacement",
        "has_displacement",
        "strong_displacement",
    )

    ob_fresh = _extract_bool(
        order_blocks,
        "fresh",
        "is_fresh",
    )

    ob_mitigated = _extract_bool(
        order_blocks,
        "mitigated",
        "is_mitigated",
    )

    ob_displacement_origin = _extract_bool(
        order_blocks,
        "displacement_origin",
        "is_displacement_origin",
    )

    ob_direction = _extract_direction(
        order_blocks
    )

    support_resistance_score = (
        _extract_strength(
            support_resistance
        )
    )

    m5_confirmation = (
        m5.retest
        or m5.rejection
        or m5.liquidity_sweep
        or m5.micro_bos
        or m5.candle_confirmation
    )

    m5_retest = bool(
        getattr(
            m5,
            "retest",
            False,
        )
    )

    m5_rejection = bool(
        getattr(
            m5,
            "rejection",
            False,
        )
    )

    m5_liquidity_sweep = bool(
        getattr(
            m5,
            "liquidity_sweep",
            False,
        )
    )

    m5_micro_bos = bool(
        getattr(
            m5,
            "micro_bos",
            False,
        )
    )

    m5_candle_confirmation = bool(
        getattr(
            m5,
            "candle_confirmation",
            False,
        )
    )

    m5_displacement = (
        m5_micro_bos
        or m5_liquidity_sweep
    )

    try:
        score = calculate_score(
            h4=h4,
            h1=h1,
            m15=m15,
            direction=direction,

            structure_htf=(
                _extract_strength(h1)
            ),

            liquidity=(
                liquidity_quality
            ),

            displacement=(
                100.0
                if displacement_detected
                else 0.0
            ),

            order_block=(
                _extract_strength(
                    order_blocks
                )
            ),

            fvg=(
                _extract_strength(fvg)
            ),

            premium_discount=(
                _extract_strength(
                    premium_discount
                )
            ),

            support_resistance=(
                support_resistance_score
            ),

            volatility_valid=(
                volatility_valid
            ),

            rr=rr,

            liquidity_sweep_quality=(
                liquidity_quality
            ),

            order_block_fresh=(
                ob_fresh
            ),

            order_block_mitigated=(
                ob_mitigated
            ),

            order_block_displacement_origin=(
                ob_displacement_origin
            ),

            order_block_direction=(
                ob_direction
            ),

            m5_confirmation=(
                m5_confirmation
            ),

            m5_direction=(
                m5_direction
            ),

            m5_retest=(
                m5_retest
            ),

            m5_rejection=(
                m5_rejection
            ),

            m5_liquidity_sweep=(
                m5_liquidity_sweep
            ),

            m5_micro_bos=(
                m5_micro_bos
            ),

            m5_candle_confirmation=(
                m5_candle_confirmation
            ),

            m5_displacement=(
                m5_displacement
            ),
        )

        return max(
            0.0,
            min(
                100.0,
                float(score),
            ),
        )

    except TypeError:
        score = calculate_score(
            h4=h4,
            h1=h1,
            m15=m15,
            direction=direction,
            rr=rr,
        )

        return max(
            0.0,
            min(
                100.0,
                float(score),
            ),
        )


def analyze_market(
    symbol: str,
    requested_direction: Optional[
        Direction
    ] = None,
) -> Dict[str, Any]:
    """
    Pipeline complet d'analyse.
    """

    market_data = {}

    for timeframe in TIMEFRAMES:
        interval = TIMEFRAME_TO_API[
            timeframe
        ]

        candles = get_candles(
            symbol,
            interval,
        )

        market_data[timeframe] = (
            _normalize_candles(candles)
        )

    h4_candles = market_data["H4"]
    h1_candles = market_data["H1"]
    m15_candles = market_data["M15"]
    m5_candles = market_data["M5"]

    if not h4_candles:
        return {
            "status": "NO_DATA",
            "symbol": symbol,
            "direction": Direction.NEUTRAL.value,
            "score": 0.0,
            "rr": 0.0,
        }

    # ========================================================
    # ATR
    # ========================================================
    #
    # analyze_displacement() exige obligatoirement un ATR.
    # Chaque timeframe utilise son propre ATR afin de mesurer
    # correctement la force relative de ses bougies.
    #

    m15_atr = _calculate_atr(
        m15_candles,
        period=14,
    )

    m5_atr = _calculate_atr(
        m5_candles,
        period=14,
    )

    h4_structure = analyze_structure(
        h4_candles
    )

    h1_structure = analyze_structure(
        h1_candles
    )

    m15_structure = analyze_structure(
        m15_candles
    )

    m5_structure = analyze_structure(
        m5_candles
    )

    h4_direction = _extract_direction(
        h4_structure
    )

    h1_direction = _extract_direction(
        h1_structure
    )

    m15_direction = _extract_direction(
        m15_structure
    )

    m5_direction = _extract_direction(
        m5_structure
    )

    h4_strength = _extract_strength(
        h4_structure
    )

    h1_strength = _extract_strength(
        h1_structure
    )

    m15_strength = _extract_strength(
        m15_structure
    )

    m5_strength = _extract_strength(
        m5_structure
    )

    trend_context = build_trend_context(
        h4=h4_direction,
        h4_strength=h4_strength,
    )

    liquidity = analyze_liquidity(
        m15_candles
    )

    displacement = analyze_displacement(
        m15_candles,
        m15_atr,
    )

    order_blocks = analyze_order_blocks(
        m15_candles
    )

    fvg = analyze_fvg(
        m15_candles
    )

    premium_discount = (
        analyze_premium_discount(
            m15_candles
        )
    )

    support_resistance = (
        analyze_support_resistance(
            m15_candles
        )
    )

    m5_liquidity = analyze_liquidity(
        m5_candles
    )

    m5_displacement = (
        analyze_displacement(
            m5_candles,
            m5_atr,
        )
    )

    m5_liquidity_sweep = (
        _extract_bool(
            m5_liquidity,
            "sweep",
            "liquidity_sweep",
            "has_sweep",
        )
    )

    m5_micro_bos = (
        _extract_bos(
            m5_structure
        )
    )

    m5_retest = (
        _extract_bool(
            m5_structure,
            "retest",
            "retest_confirmed",
        )
    )

    m5_rejection = (
        _extract_bool(
            m5_structure,
            "rejection",
            "rejection_confirmed",
        )
    )

    m5_candle_confirmation = False

    if m5_candles:
        last_candle = m5_candles[-1]

        m5_candle_confirmation = (
            last_candle.bullish
            or last_candle.bearish
        )

    m5_confirmation = (
        validate_m5_confirmation(
            direction=m5_direction,
            retest=m5_retest,
            rejection=m5_rejection,
            liquidity_sweep=(
                m5_liquidity_sweep
            ),
            micro_bos=m5_micro_bos,
            candle_confirmation=(
                m5_candle_confirmation
            ),
        )
    )

    direction = resolve_direction(
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
        requested_direction=(
            requested_direction
        ),
    )

    primary_alignment = (
        _primary_alignment_valid(
            h4=h4_direction,
            h1=h1_direction,
            m15=m15_direction,
        )
    )

    scenario = _determine_scenario(
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
        direction=direction,
        liquidity_sweep=(
            _extract_bool(
                liquidity,
                "sweep",
                "liquidity_sweep",
                "has_sweep",
            )
        ),
        displacement=(
            _extract_bool(
                displacement,
                "displacement",
                "has_displacement",
                "strong_displacement",
            )
        ),
        bos=_extract_bos(
            m15_structure
        ),
        choch=_extract_choch(
            m15_structure
        ),
    )

    latest_price = float(
        m5_candles[-1].close
        if m5_candles
        else (
            m15_candles[-1].close
            if m15_candles
            else h4_candles[-1].close
        )
    )

    # L'ATR M15 sert de référence pour la
    # géométrie principale du trade.
    atr = m15_atr

    zone = _build_zone(
        direction=direction,
        sr_result=support_resistance,
        ob_result=order_blocks,
        fvg_result=fvg,
    )

    (
        entry,
        stop_loss,
        take_profit,
    ) = _build_trade_geometry(
        direction=direction,
        entry=latest_price,
        zone=zone,
        atr=atr,
    )

    rr = calculate_rr(
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        direction=direction,
    )

    score = _calculate_final_score(
        h4=h4_direction,
        h1=h1_structure,
        m15=m15_structure,
        m5=m5_confirmation,
        liquidity=liquidity,
        displacement=displacement,
        order_blocks=order_blocks,
        fvg=fvg,
        premium_discount=(
            premium_discount
        ),
        support_resistance=(
            support_resistance
        ),
        direction=direction,
        rr=rr,
        volatility_valid=True,
    )

    status = "ACTIVE"

    if direction == Direction.NEUTRAL:
        status = "REJECT"

    elif not primary_alignment:
        status = "REJECT"

    elif score < CONFIG.SIGNAL_THRESHOLD:
        status = "REJECT"

    elif rr < CONFIG.MINIMUM_RR:
        status = "REJECT"

    return {
        "status": status,
        "symbol": symbol,
        "direction": direction.value,
        "score": round(
            score,
            2,
        ),
        "rr": round(
            rr,
            2,
        ),
        "scenario": scenario,

        "h4": h4_direction.value,
        "h1": h1_direction.value,
        "m15": m15_direction.value,
        "m5": m5_direction.value,

        "h4_strength": round(
            h4_strength,
            2,
        ),
        "h1_strength": round(
            h1_strength,
            2,
        ),
        "m15_strength": round(
            m15_strength,
            2,
        ),
        "m5_strength": round(
            m5_strength,
            2,
        ),

        "m5_confirmation": (
            confirmation_strength(
                m5_confirmation
            )
        ),

        "zone": zone,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,

        "trend_context": trend_context,

        "h4_structure": h4_structure,
        "h1_structure": h1_structure,
        "m15_structure": m15_structure,
        "m5_structure": m5_structure,

        "liquidity": liquidity,
        "displacement": displacement,
        "order_blocks": order_blocks,
        "fvg": fvg,
        "premium_discount": (
            premium_discount
        ),
        "support_resistance": (
            support_resistance
        ),

        "confirmation": m5_confirmation,
    }


def analyser_marche(
    symbol: str = "XAU/USD",
    requested_direction: Optional[
        Direction
    ] = None,
) -> Dict[str, Any]:
    """
    Alias français compatible.
    """

    return analyze_market(
        symbol=symbol,
        requested_direction=(
            requested_direction
        ),
    )


def analyser_market(
    symbol: str = "XAU/USD",
    requested_direction: Optional[
        Direction
    ] = None,
) -> Dict[str, Any]:
    """
    Alias anglais.
    """

    return analyze_market(
        symbol=symbol,
        requested_direction=(
            requested_direction
        ),
    )