"""
NOVA TRADE AI
analysis/pipeline.py

Pipeline déterministe principal.

Architecture :

DATA
 ↓
H4 : biais global
 ↓
H1 : structure
 ↓
M15 : structure + contexte SMC
 ↓
Liquidity / Displacement / OB / FVG
 ↓
Premium / Discount
 ↓
Support / Resistance
 ↓
M5 : confirmation secondaire
 ↓
Scenario
 ↓
Confluence
 ↓
Score
 ↓
RR / Risk
 ↓
News filter
 ↓
Signal final

Règles principales :
- D1 exclu.
- H4 donne une préférence directionnelle mais ne bloque pas
  automatiquement un setup valide.
- H1 + M15 constituent la validation structurelle principale.
- M5 est secondaire et non bloquant.
- Aucun signal forcé.
- Score minimum : CONFIG.SIGNAL_THRESHOLD.
- RR minimum : CONFIG.MINIMUM_RR.

Compatibilité données :
- Les moteurs peuvent recevoir des Candle ou des dict.
- Les données provenant de market_data sont normalisées
  en Candle avant toute analyse.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from config import CONFIG

from core.models import (
    Candle,
    Confirmation,
    Direction,
    TrendContext,
    Zone,
)

from market_data import get_candles

from analysis.structure import (
    analyze_structure,
)

from analysis.liquidity import (
    analyze_liquidity,
)

from analysis.displacement import (
    analyze_displacement,
    detect_displacement_after_sweep,
)

from analysis.order_blocks import (
    analyze_order_blocks,
    get_best_order_block,
)

from analysis.fvg import (
    analyze_fvg,
    get_best_fvg,
)

from analysis.premium_discount import (
    analyze_premium_discount,
)

from analysis.support_resistance import (
    analyze_support_resistance,
    get_best_support_resistance,
)

from analysis.confirmation import (
    validate_m5_confirmation,
    confirmation_strength,
)

from scoring.scoring_engine import (
    calculate_score,
    should_send_signal,
)

from risk.risk_manager import (
    calculate_rr,
    validate_trade_geometry,
)

from signals.signal_engine import (
    build_signal,
)


# ============================================================================
# CONSTANTES
# ============================================================================

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


# ============================================================================
# OUTILS GENERIQUES
# ============================================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)

        if result != result:
            return default

        return result

    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _normalize_direction(value: Any) -> Direction:
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


def _direction_value(value: Any) -> str:
    return _normalize_direction(value).value


def _get(
    obj: Any,
    key: str,
    default: Any = None,
) -> Any:
    """
    Lecture compatible objet/dict.

    Permet au pipeline de manipuler aussi bien :
        candle.close
    que :
        candle["close"]
    """

    if obj is None:
        return default

    if isinstance(obj, dict):
        if key in obj:
            return obj.get(key, default)

        # Compatibilité avec des données utilisant des majuscules.
        upper_key = key.upper()

        if upper_key in obj:
            return obj.get(upper_key, default)

        # Compatibilité avec quelques noms alternatifs.
        aliases = {
            "timestamp": (
                "datetime",
                "date",
                "time",
            ),
            "open": (
                "o",
            ),
            "high": (
                "h",
            ),
            "low": (
                "l",
            ),
            "close": (
                "c",
            ),
            "volume": (
                "v",
            ),
        }

        for alias in aliases.get(key, ()):
            if alias in obj:
                return obj.get(alias, default)

        return default

    return getattr(
        obj,
        key,
        default,
    )


def _parse_timestamp(
    value: Any,
) -> datetime:
    """
    Convertit différents formats de timestamp en datetime.

    Le pipeline n'a pas besoin d'un timestamp parfait pour les calculs
    numériques, mais Candle attend un objet datetime exploitable.
    """

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value

    if value is None:
        return datetime.now(timezone.utc)

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(
                float(value),
                tz=timezone.utc,
            )
        except Exception:
            return datetime.now(timezone.utc)

    text = str(value).strip()

    if not text:
        return datetime.now(timezone.utc)

    # ISO classique.
    try:
        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed

    except Exception:
        pass

    # Formats courants de market data.
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    )

    for fmt in formats:
        try:
            return datetime.strptime(
                text,
                fmt,
            ).replace(
                tzinfo=timezone.utc
            )
        except Exception:
            continue

    return datetime.now(timezone.utc)


def _normalize_candle(
    candle: Any,
) -> Optional[Candle]:
    """
    Convertit une bougie provenant de n'importe quelle source
    compatible en objet Candle.

    Accepte :
        Candle
        dict
        dict avec clés majuscules
        dict avec o/h/l/c
    """

    if candle is None:
        return None

    if isinstance(candle, Candle):
        return candle

    try:
        timestamp = _parse_timestamp(
            _get(
                candle,
                "timestamp",
                None,
            )
        )

        open_price = _safe_float(
            _get(
                candle,
                "open",
                0.0,
            )
        )

        high_price = _safe_float(
            _get(
                candle,
                "high",
                0.0,
            )
        )

        low_price = _safe_float(
            _get(
                candle,
                "low",
                0.0,
            )
        )

        close_price = _safe_float(
            _get(
                candle,
                "close",
                0.0,
            )
        )

        volume = _safe_float(
            _get(
                candle,
                "volume",
                0.0,
            )
        )

        # Une bougie sans OHLC exploitable est ignorée.
        if (
            open_price == 0.0
            and high_price == 0.0
            and low_price == 0.0
            and close_price == 0.0
        ):
            return None

        return Candle(
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        )

    except Exception:
        return None


def _normalize_candles(
    candles: Any,
) -> list[Candle]:
    """
    Normalise toute collection de bougies.

    Le résultat retourné par cette fonction est TOUJOURS :
        list[Candle]
    """

    if candles is None:
        return []

    if isinstance(candles, Candle):
        return [candles]

    try:
        raw_candles = list(candles)
    except TypeError:
        return []

    normalized: list[Candle] = []

    for candle in raw_candles:
        converted = _normalize_candle(candle)

        if converted is not None:
            normalized.append(converted)

    return normalized


def _last_candle(
    candles: list[Candle],
) -> Optional[Candle]:
    if not candles:
        return None

    return candles[-1]


def _last_price(
    candles: list[Candle],
) -> float:
    candle = _last_candle(candles)

    if candle is None:
        return 0.0

    return _safe_float(
        _get(
            candle,
            "close",
            0.0,
        )
    )


def _atr_from_candles(
    candles: list[Candle],
    period: int = 14,
) -> float:
    if len(candles) < 2:
        return 0.0

    ranges = []

    start = max(
        1,
        len(candles) - period,
    )

    for index in range(
        start,
        len(candles),
    ):
        current = candles[index]
        previous = candles[index - 1]

        high = _safe_float(
            _get(
                current,
                "high",
                0.0,
            )
        )

        low = _safe_float(
            _get(
                current,
                "low",
                0.0,
            )
        )

        previous_close = _safe_float(
            _get(
                previous,
                "close",
                0.0,
            )
        )

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )

        ranges.append(true_range)

    if not ranges:
        return 0.0

    return sum(ranges) / len(ranges)


def _call_analyser(
    function,
    *args,
    **kwargs,
):
    """
    Appelle un moteur spécialisé sans laisser une incompatibilité
    mineure de signature faire tomber tout le pipeline.
    """

    try:
        return function(
            *args,
            **kwargs,
        )

    except TypeError:
        try:
            return function(*args)

        except Exception:
            return None

    except Exception:
        return None


# ============================================================================
# STRUCTURE
# ============================================================================

def _analyse_structure(
    candles: list[Candle],
):
    if not candles:
        return None

    return _call_analyser(
        analyze_structure,
        candles,
    )


def _structure_direction(
    result: Any,
) -> Direction:
    if result is None:
        return Direction.NEUTRAL

    direction = _normalize_direction(
        _get(
            result,
            "direction",
            Direction.NEUTRAL,
        )
    )

    if direction != Direction.NEUTRAL:
        return direction

    bullish = _safe_bool(
        _get(
            result,
            "bullish_structure",
            False,
        )
    )

    bearish = _safe_bool(
        _get(
            result,
            "bearish_structure",
            False,
        )
    )

    if bullish and not bearish:
        return Direction.BUY

    if bearish and not bullish:
        return Direction.SELL

    return Direction.NEUTRAL


def _structure_strength(
    result: Any,
) -> float:
    if result is None:
        return 0.0

    return max(
        0.0,
        min(
            100.0,
            _safe_float(
                _get(
                    result,
                    "strength",
                    0.0,
                )
            ),
        ),
    )


def _structure_has_event(
    result: Any,
    event_name: str,
) -> bool:
    if result is None:
        return False

    events = _get(
        result,
        event_name,
        (),
    )

    if events is None:
        return False

    try:
        return len(events) > 0
    except TypeError:
        return False


# ============================================================================
# LIQUIDITY
# ============================================================================

def _analyse_liquidity(
    candles: list[Candle],
    direction: Direction,
):
    if not candles:
        return None

    return _call_analyser(
        analyze_liquidity,
        candles,
        direction=direction,
    )


def _liquidity_sweep(
    result: Any,
    direction: Direction,
) -> bool:
    if result is None:
        return False

    sweep = _get(
        result,
        "sweep",
        None,
    )

    if sweep is not None:
        sweep_direction = _normalize_direction(
            _get(
                sweep,
                "direction",
                Direction.NEUTRAL,
            )
        )

        valid = _safe_bool(
            _get(
                sweep,
                "valid",
                True,
            )
        )

        if valid:
            if sweep_direction == Direction.NEUTRAL:
                return True

            return sweep_direction == direction

    sweeps = _get(
        result,
        "sweeps",
        (),
    )

    if sweeps:
        for item in sweeps:
            item_direction = _normalize_direction(
                _get(
                    item,
                    "direction",
                    Direction.NEUTRAL,
                )
            )

            valid = _safe_bool(
                _get(
                    item,
                    "valid",
                    True,
                )
            )

            if valid and (
                item_direction == Direction.NEUTRAL
                or item_direction == direction
            ):
                return True

    return _safe_bool(
        _get(
            result,
            "liquidity_sweep",
            False,
        )
    )


def _liquidity_quality(
    result: Any,
) -> float:
    if result is None:
        return 0.0

    for key in (
        "strength",
        "quality",
        "score",
    ):
        value = _get(
            result,
            key,
            None,
        )

        if value is not None:
            return max(
                0.0,
                min(
                    100.0,
                    _safe_float(value),
                ),
            )

    return 0.0


# ============================================================================
# DISPLACEMENT
# ============================================================================

def _analyse_displacement(
    candles: list[Candle],
    direction: Direction,
):
    if not candles:
        return None

    return _call_analyser(
        analyze_displacement,
        candles,
        direction=direction,
    )


def _displacement_valid(
    result: Any,
    direction: Direction,
) -> bool:
    if result is None:
        return False

    valid = _safe_bool(
        _get(
            result,
            "valid",
            False,
        )
    )

    if not valid:
        return False

    result_direction = _normalize_direction(
        _get(
            result,
            "direction",
            Direction.NEUTRAL,
        )
    )

    if result_direction == Direction.NEUTRAL:
        return True

    return result_direction == direction


def _displacement_strength(
    result: Any,
) -> float:
    if result is None:
        return 0.0

    return max(
        0.0,
        min(
            100.0,
            _safe_float(
                _get(
                    result,
                    "strength",
                    0.0,
                )
            ),
        ),
    )


def _displacement_atr_ratio(
    result: Any,
) -> float:
    if result is None:
        return 0.0

    for key in (
        "atr_ratio",
        "range_atr_ratio",
        "body_atr_ratio",
    ):
        value = _get(
            result,
            key,
            None,
        )

        if value is not None:
            return max(
                0.0,
                _safe_float(value),
            )

    return 0.0


# ============================================================================
# ORDER BLOCK
# ============================================================================

def _analyse_order_blocks(
    candles: list[Candle],
    direction: Direction,
):
    if not candles:
        return None

    return _call_analyser(
        analyze_order_blocks,
        candles,
        direction=direction,
    )


def _best_order_block(
    result: Any,
    direction: Direction,
):
    if result is None:
        return None

    try:
        return get_best_order_block(
            _get(
                result,
                "order_blocks",
                (),
            ),
            direction,
        )
    except Exception:
        pass

    best = _get(
        result,
        "best",
        None,
    )

    if best is not None:
        return best

    return None


def _ob_exists(
    ob: Any,
) -> bool:
    return ob is not None


def _ob_fresh(
    ob: Any,
) -> bool:
    if ob is None:
        return False

    return _safe_bool(
        _get(
            ob,
            "fresh",
            False,
        )
    )


def _ob_mitigated(
    ob: Any,
) -> bool:
    if ob is None:
        return False

    return _safe_bool(
        _get(
            ob,
            "mitigated",
            False,
        )
    )


def _ob_displacement_origin(
    ob: Any,
) -> bool:
    if ob is None:
        return False

    return _safe_bool(
        _get(
            ob,
            "displacement_origin",
            False,
        )
    )


def _ob_strength(
    ob: Any,
) -> float:
    if ob is None:
        return 0.0

    return max(
        0.0,
        min(
            100.0,
            _safe_float(
                _get(
                    ob,
                    "strength",
                    0.0,
                )
            ),
        ),
    )


# ============================================================================
# FVG
# ============================================================================

def _analyse_fvg(
    candles: list[Candle],
    direction: Direction,
):
    if not candles:
        return None

    return _call_analyser(
        analyze_fvg,
        candles,
        direction=direction,
    )


def _best_fvg(
    result: Any,
    direction: Direction,
):
    if result is None:
        return None

    try:
        fvgs = _get(
            result,
            "fvgs",
            None,
        )

        if fvgs is not None:
            return get_best_fvg(
                fvgs,
                direction,
            )

    except Exception:
        pass

    best = _get(
        result,
        "fvg",
        None,
    )

    if best is not None:
        return best

    return None


def _fvg_exists(
    fvg: Any,
) -> bool:
    return fvg is not None


def _fvg_fresh(
    fvg: Any,
) -> bool:
    if fvg is None:
        return False

    return _safe_bool(
        _get(
            fvg,
            "fresh",
            False,
        )
    )


def _fvg_filled(
    fvg: Any,
) -> bool:
    if fvg is None:
        return False

    return _safe_bool(
        _get(
            fvg,
            "filled",
            False,
        )
    )


def _fvg_atr_ratio(
    fvg: Any,
) -> float:
    if fvg is None:
        return 0.0

    return max(
        0.0,
        _safe_float(
            _get(
                fvg,
                "atr_ratio",
                0.0,
            )
        ),
    )


# ============================================================================
# PREMIUM / DISCOUNT
# ============================================================================

def _analyse_premium_discount(
    candles: list[Candle],
    price: float,
    direction: Direction,
):
    if not candles:
        return None

    return _call_analyser(
        analyze_premium_discount,
        candles,
        price=price,
        direction=direction,
    )


def _premium_discount_zone(
    result: Any,
) -> str:
    if result is None:
        return "EQUILIBRIUM"

    zone = _get(
        result,
        "zone",
        "EQUILIBRIUM",
    )

    return str(zone).upper()


def _premium_discount_strength(
    result: Any,
) -> float:
    if result is None:
        return 0.0

    return max(
        0.0,
        min(
            100.0,
            _safe_float(
                _get(
                    result,
                    "strength",
                    0.0,
                )
            ),
        ),
    )


# ============================================================================
# SUPPORT / RESISTANCE
# ============================================================================

def _analyse_support_resistance(
    candles: list[Candle],
    price: float,
    direction: Direction,
):
    if not candles:
        return None

    return _call_analyser(
        analyze_support_resistance,
        candles,
        price=price,
        direction=direction,
    )


def _best_support_resistance(
    result: Any,
    direction: Direction,
):
    if result is None:
        return None

    try:
        levels = []

        supports = _get(
            result,
            "supports",
            (),
        )

        resistances = _get(
            result,
            "resistances",
            (),
        )

        levels.extend(
            list(supports or ())
        )

        levels.extend(
            list(resistances or ())
        )

        if levels:
            return get_best_support_resistance(
                levels,
                direction,
            )

    except Exception:
        pass

    return _get(
        result,
        "best",
        None,
    )


# ============================================================================
# M5 CONFIRMATION
# ============================================================================

def _build_m5_confirmation(
    candles: list[Candle],
    direction: Direction,
):
    if not candles:
        return validate_m5_confirmation(
            direction=direction,
            retest=False,
            rejection=False,
            liquidity_sweep=False,
            micro_bos=False,
            candle_confirmation=False,
        )

    structure = _analyse_structure(
        candles
    )

    structure_direction = _structure_direction(
        structure
    )

    micro_bos = (
        _structure_has_event(
            structure,
            "bos",
        )
        and (
            structure_direction == direction
            or structure_direction == Direction.NEUTRAL
        )
    )

    liquidity = _analyse_liquidity(
        candles,
        direction,
    )

    sweep = _liquidity_sweep(
        liquidity,
        direction,
    )

    displacement = _analyse_displacement(
        candles,
        direction,
    )

    displacement_valid = _displacement_valid(
        displacement,
        direction,
    )

    candle = _last_candle(
        candles
    )

    if candle is None:
        rejection = False
        candle_confirmation = False

    else:
        candle_open = _safe_float(
            _get(
                candle,
                "open",
                0.0,
            )
        )

        candle_close = _safe_float(
            _get(
                candle,
                "close",
                0.0,
            )
        )

        candle_high = _safe_float(
            _get(
                candle,
                "high",
                0.0,
            )
        )

        candle_low = _safe_float(
            _get(
                candle,
                "low",
                0.0,
            )
        )

        body = abs(
            candle_close
            - candle_open
        )

        candle_range = max(
            candle_high
            - candle_low,
            0.0,
        )

        body_ratio = (
            body / candle_range
            if candle_range > 0
            else 0.0
        )

        upper_wick = max(
            candle_high
            - max(
                candle_open,
                candle_close,
            ),
            0.0,
        )

        lower_wick = max(
            min(
                candle_open,
                candle_close,
            )
            - candle_low,
            0.0,
        )

        if direction == Direction.BUY:
            candle_confirmation = (
                candle_close > candle_open
                and body_ratio >= 0.45
            )

            rejection = (
                lower_wick > upper_wick
                and candle_close >= candle_open
            )

        elif direction == Direction.SELL:
            candle_confirmation = (
                candle_close < candle_open
                and body_ratio >= 0.45
            )

            rejection = (
                upper_wick > lower_wick
                and candle_close <= candle_open
            )

        else:
            candle_confirmation = False
            rejection = False

    retest = (
        sweep
        and rejection
    ) or (
        displacement_valid
        and rejection
    )

    return validate_m5_confirmation(
        direction=direction,
        retest=retest,
        rejection=rejection,
        liquidity_sweep=sweep,
        micro_bos=micro_bos,
        candle_confirmation=candle_confirmation,
    )


# ============================================================================
# DIRECTION
# ============================================================================

def resolve_direction(
    h4: Direction,
    h1: Direction,
    m15: Direction,
    requested_direction: Optional[Direction] = None,
) -> Direction:
    """
    Priorité :

    1. Direction explicitement demandée.
    2. H1 + M15 alignés.
    3. H4 + H1 alignés.
    4. H4 + M15 alignés.
    5. H4 seul.
    6. H1 seul.
    7. M15 seul.
    8. Neutral.
    """

    requested = _normalize_direction(
        requested_direction
    )

    if requested != Direction.NEUTRAL:
        return requested

    h4 = _normalize_direction(h4)
    h1 = _normalize_direction(h1)
    m15 = _normalize_direction(m15)

    if (
        h1 != Direction.NEUTRAL
        and h1 == m15
    ):
        return h1

    if (
        h4 != Direction.NEUTRAL
        and h4 == h1
    ):
        return h4

    if (
        h4 != Direction.NEUTRAL
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
    Validation principale souple.

    H4 n'est pas un blocage absolu.
    """

    return any(
        direction != Direction.NEUTRAL
        for direction in (
            h4,
            h1,
            m15,
        )
    )


# ============================================================================
# SCENARIO
# ============================================================================

def _determine_scenario(
    h4: Direction,
    h1: Direction,
    m15: Direction,
    direction: Direction,
    liquidity_sweep: bool,
    displacement_valid: bool,
    bos: bool,
    choch: bool,
) -> str:

    if (
        liquidity_sweep
        and displacement_valid
        and (bos or choch)
    ):
        return "LIQUIDITY_REVERSAL"

    if (
        h4 != Direction.NEUTRAL
        and h1 == h4
        and m15 == h4
    ):
        return "CONTINUATION"

    if (
        h4 != Direction.NEUTRAL
        and h1 == h4
        and m15 != Direction.NEUTRAL
        and m15 != h4
    ):
        return "CORRECTION"

    if (
        h4 != Direction.NEUTRAL
        and h1 != Direction.NEUTRAL
        and h1 != h4
        and m15 == h1
    ):
        return "POTENTIAL_REVERSAL"

    if (
        h4 != Direction.NEUTRAL
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


# ============================================================================
# SL / TP
# ============================================================================

def _recent_low(
    candles: list[Candle],
    lookback: int = 20,
) -> float:

    subset = candles[-lookback:]

    if not subset:
        return 0.0

    return min(
        _safe_float(
            _get(
                candle,
                "low",
                0.0,
            )
        )
        for candle in subset
    )


def _recent_high(
    candles: list[Candle],
    lookback: int = 20,
) -> float:

    subset = candles[-lookback:]

    if not subset:
        return 0.0

    return max(
        _safe_float(
            _get(
                candle,
                "high",
                0.0,
            )
        )
        for candle in subset
    )


def _zone_low(
    zone: Any,
) -> float:
    return _safe_float(
        _get(
            zone,
            "low",
            0.0,
        )
    )


def _zone_high(
    zone: Any,
) -> float:
    return _safe_float(
        _get(
            zone,
            "high",
            0.0,
        )
    )


def _build_trade_geometry(
    candles: list[Candle],
    direction: Direction,
    entry: float,
    ob: Any = None,
    fvg: Any = None,
    sr: Any = None,
) -> tuple[float, float]:
    """
    Construit SL/TP à partir du contexte structurel.

    Priorité SL :
    1. OB
    2. S/R
    3. swing récent
    4. ATR

    TP :
    - minimum RR configuré.
    """

    atr = _atr_from_candles(
        candles
    )

    if atr <= 0:
        atr = max(
            abs(entry) * 0.001,
            0.00001,
        )

    buffer = atr * 0.25

    stop_loss = 0.0

    if ob is not None:
        ob_low = _safe_float(
            _get(
                ob,
                "low",
                0.0,
            )
        )

        ob_high = _safe_float(
            _get(
                ob,
                "high",
                0.0,
            )
        )

        if (
            direction == Direction.BUY
            and ob_low > 0
        ):
            stop_loss = (
                ob_low
                - buffer
            )

        elif (
            direction == Direction.SELL
            and ob_high > 0
        ):
            stop_loss = (
                ob_high
                + buffer
            )

    if (
        stop_loss <= 0
        and sr is not None
    ):
        sr_low = _safe_float(
            _get(
                sr,
                "low",
                0.0,
            )
        )

        sr_high = _safe_float(
            _get(
                sr,
                "high",
                0.0,
            )
        )

        if (
            direction == Direction.BUY
            and sr_low > 0
        ):
            stop_loss = (
                sr_low
                - buffer
            )

        elif (
            direction == Direction.SELL
            and sr_high > 0
        ):
            stop_loss = (
                sr_high
                + buffer
            )

    if stop_loss <= 0:
        if direction == Direction.BUY:
            swing_low = _recent_low(
                candles
            )

            stop_loss = (
                swing_low
                - buffer
            )

        else:
            swing_high = _recent_high(
                candles
            )

            stop_loss = (
                swing_high
                + buffer
            )

    if direction == Direction.BUY:
        risk_distance = (
            entry
            - stop_loss
        )
    else:
        risk_distance = (
            stop_loss
            - entry
        )

    if risk_distance <= 0:
        risk_distance = atr

        if direction == Direction.BUY:
            stop_loss = (
                entry
                - risk_distance
            )

        else:
            stop_loss = (
                entry
                + risk_distance
            )

    target_distance = (
        risk_distance
        * max(
            2.0,
            _safe_float(
                CONFIG.MINIMUM_RR,
                2.0,
            ),
        )
    )

    if direction == Direction.BUY:
        take_profit = (
            entry
            + target_distance
        )

    else:
        take_profit = (
            entry
            - target_distance
        )

    return (
        stop_loss,
        take_profit,
    )


# ============================================================================
# ZONE
# ============================================================================

def _build_zone(
    direction: Direction,
    sr: Any,
    ob: Any,
    fvg: Any,
    h1_strength: float,
    m15_strength: float,
    structure_confirmed: bool,
    liquidity_nearby: bool,
) -> Optional[Zone]:

    level_type = "NONE"
    key_level = 0.0
    low = 0.0
    high = 0.0

    if sr is not None:
        raw_type = str(
            _get(
                sr,
                "level_type",
                "NONE",
            )
        ).upper()

        if raw_type in {
            "SUPPORT",
            "RESISTANCE",
        }:
            level_type = raw_type

            key_level = _safe_float(
                _get(
                    sr,
                    "key_level",
                    0.0,
                )
            )

            low = _safe_float(
                _get(
                    sr,
                    "low",
                    0.0,
                )
            )

            high = _safe_float(
                _get(
                    sr,
                    "high",
                    0.0,
                )
            )

    if (
        key_level <= 0
        and ob is not None
    ):
        low = _safe_float(
            _get(
                ob,
                "low",
                0.0,
            )
        )

        high = _safe_float(
            _get(
                ob,
                "high",
                0.0,
            )
        )

        if (
            low > 0
            and high > 0
        ):
            key_level = (
                low + high
            ) / 2.0

            level_type = (
                "SUPPORT"
                if direction == Direction.BUY
                else "RESISTANCE"
            )

    if (
        key_level <= 0
        and fvg is not None
    ):
        low = _safe_float(
            _get(
                fvg,
                "low",
                0.0,
            )
        )

        high = _safe_float(
            _get(
                fvg,
                "high",
                0.0,
            )
        )

        if (
            low > 0
            and high > 0
        ):
            key_level = (
                low + high
            ) / 2.0

            level_type = (
                "SUPPORT"
                if direction == Direction.BUY
                else "RESISTANCE"
            )

    if key_level <= 0:
        return None

    if low <= 0:
        low = key_level

    if high <= 0:
        high = key_level

    breakout = (
        _safe_bool(
            _get(
                sr,
                "breakout",
                False,
            )
        )
        if sr is not None
        else False
    )

    breakout_direction = (
        _normalize_direction(
            _get(
                sr,
                "breakout_direction",
                Direction.NEUTRAL,
            )
        )
        if sr is not None
        else Direction.NEUTRAL
    )

    retest = (
        _safe_bool(
            _get(
                sr,
                "retest",
                False,
            )
        )
        if sr is not None
        else False
    )

    rejection = (
        _safe_bool(
            _get(
                sr,
                "rejection",
                False,
            )
        )
        if sr is not None
        else False
    )

    return Zone(
        direction=direction,
        timeframe="H1+M15",
        low=low,
        high=high,
        h1_strength=h1_strength,
        m15_strength=m15_strength,
        kind=(
            "SUPPORT"
            if direction == Direction.BUY
            else "RESISTANCE"
        ),
        structure_confirmed=structure_confirmed,
        liquidity_nearby=liquidity_nearby,
        order_block=ob is not None,
        fvg=fvg is not None,
        level_type=level_type,
        key_level=key_level,
        breakout_confirmed=breakout,
        breakout_direction=breakout_direction,
        retest_confirmed=retest,
        rejection_confirmed=rejection,
        candle_confirmation=False,
        entry_valid=False,
        entry_distance=0.0,
    )


# ============================================================================
# CONFLUENCE
# ============================================================================

def _count_confluences(
    structure_confirmed: bool,
    liquidity_sweep: bool,
    displacement_valid: bool,
    order_block: bool,
    fvg: bool,
    premium_discount_valid: bool,
    sr: Any,
    m5_confirmation: Confirmation,
) -> int:

    count = 0

    if structure_confirmed:
        count += 1

    if liquidity_sweep:
        count += 1

    if displacement_valid:
        count += 1

    if order_block:
        count += 1

    if fvg:
        count += 1

    if premium_discount_valid:
        count += 1

    if sr is not None:
        count += 1

    if (
        m5_confirmation.rejection
        or m5_confirmation.micro_bos
        or m5_confirmation.liquidity_sweep
    ):
        count += 1

    return count


# ============================================================================
# NEWS
# ============================================================================

def _check_news(
    symbol: str,
) -> bool:
    """
    Filtre économique.

    Fail-open : une panne du calendrier ne doit pas
    inventer un blocage de marché.
    """

    try:
        from economic_calendar import economic_filter

        result = economic_filter(
            symbol
        )

        if isinstance(
            result,
            bool,
        ):
            return result

        if isinstance(
            result,
            dict,
        ):
            if "allowed" in result:
                return bool(
                    result["allowed"]
                )

            if "blocked" in result:
                return not bool(
                    result["blocked"]
                )

        return True

    except Exception:
        return True


# ============================================================================
# SCORE
# ============================================================================

def _calculate_final_score(
    *,
    trend: TrendContext,
    zone: Zone,
    confirmation: Confirmation,
    rr: float,
    h4: Direction,
    h1: Direction,
    m15: Direction,
    direction: Direction,
    scenario: str,
    liquidity_result: Any,
    displacement_result: Any,
    ob: Any,
    fvg: Any,
    premium_discount_result: Any,
    sr: Any,
    m5: Confirmation,
    spread_ok: bool = True,
    session_ok: bool = True,
) -> float:

    liquidity_sweep = _liquidity_sweep(
        liquidity_result,
        direction,
    )

    liquidity_quality = _liquidity_quality(
        liquidity_result
    )

    displacement_valid = _displacement_valid(
        displacement_result,
        direction,
    )

    displacement_direction = _normalize_direction(
        _get(
            displacement_result,
            "direction",
            Direction.NEUTRAL,
        )
    )

    displacement_atr_ratio = (
        _displacement_atr_ratio(
            displacement_result
        )
    )

    premium_discount = (
        _premium_discount_zone(
            premium_discount_result
        )
    )

    volatility_score = 0.0

    atr_ratio = _displacement_atr_ratio(
        displacement_result
    )

    if atr_ratio > 0:
        volatility_score = min(
            100.0,
            atr_ratio * 50.0,
        )

    try:
        return float(
            calculate_score(
                trend=trend,
                zone=zone,
                confirmation=confirmation,
                rr=rr,
                spread_ok=spread_ok,
                session_ok=session_ok,

                h4=h4,
                h1=h1,
                m15=m15,
                direction=direction,
                scenario=scenario,

                liquidity_sweep=liquidity_sweep,
                liquidity_sweep_quality=(
                    liquidity_quality
                ),

                displacement_valid=(
                    displacement_valid
                ),
                displacement_direction=(
                    displacement_direction
                ),
                displacement_atr_ratio=(
                    displacement_atr_ratio
                ),

                order_block=(
                    ob is not None
                ),
                order_block_fresh=(
                    _ob_fresh(ob)
                ),
                order_block_mitigated=(
                    _ob_mitigated(ob)
                ),
                order_block_displacement_origin=(
                    _ob_displacement_origin(ob)
                ),
                order_block_direction=(
                    _normalize_direction(
                        _get(
                            ob,
                            "direction",
                            Direction.NEUTRAL,
                        )
                    )
                ),

                fvg=(
                    fvg is not None
                ),
                fvg_fresh=(
                    _fvg_fresh(fvg)
                ),
                fvg_filled=(
                    _fvg_filled(fvg)
                ),
                fvg_atr_ratio=(
                    _fvg_atr_ratio(fvg)
                ),

                premium_discount=(
                    premium_discount
                ),

                support_resistance=(
                    {
                        "type": _get(
                            sr,
                            "level_type",
                            "NONE",
                        ),
                        "strength": _safe_float(
                            _get(
                                sr,
                                "strength",
                                0.0,
                            )
                        ),
                        "reactions": int(
                            _safe_float(
                                _get(
                                    sr,
                                    "reactions",
                                    0,
                                )
                            )
                        ),
                        "breakout": _safe_bool(
                            _get(
                                sr,
                                "breakout",
                                False,
                            )
                        ),
                        "retest": _safe_bool(
                            _get(
                                sr,
                                "retest",
                                False,
                            )
                        ),
                        "rejection": _safe_bool(
                            _get(
                                sr,
                                "rejection",
                                False,
                            )
                        ),
                        "distance": _safe_float(
                            _get(
                                sr,
                                "distance",
                                0.0,
                            )
                        ),
                    }
                    if sr is not None
                    else None
                ),

                volatility_score=(
                    volatility_score
                ),
                volatility_valid=(
                    volatility_score > 0
                ),

                m5_confirmation=True,
                m5_direction=(
                    m5.direction
                ),
                m5_retest=(
                    m5.retest
                ),
                m5_rejection=(
                    m5.rejection
                ),
                m5_liquidity_sweep=(
                    m5.liquidity_sweep
                ),
                m5_micro_bos=(
                    m5.micro_bos
                ),
                m5_candle_confirmation=(
                    m5.candle_confirmation
                ),
                m5_displacement=(
                    m5.micro_bos
                    or m5.liquidity_sweep
                ),
            )
        )

    except TypeError:
        return float(
            calculate_score(
                trend=trend,
                zone=zone,
                confirmation=confirmation,
                rr=rr,
                spread_ok=spread_ok,
                session_ok=session_ok,
            )
        )


# ============================================================================
# ANALYSE PRINCIPALE
# ============================================================================

def analyser_marche(
    symbol: str = "XAU/USD",
    timeframe: str = "15min",
    requested_direction: Optional[Direction] = None,
) -> dict[str, Any]:
    """
    Analyse complète multi-timeframe.

    Retourne toujours un dictionnaire exploitable par Telegram.
    """

    symbol = str(
        symbol
    ).upper().strip()

    requested_direction = _normalize_direction(
        requested_direction
    )

    # ------------------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------------------

    candles_by_tf: dict[str, list[Candle]] = {}

    for tf in TIMEFRAMES:
        api_interval = TIMEFRAME_TO_API[
            tf
        ]

        try:
            raw_candles = get_candles(
                symbol,
                api_interval,
            )

            # ================================================================
            # CORRECTION CRITIQUE
            # ================================================================
            #
            # market_data peut retourner :
            #
            #     {"open": ..., "high": ..., ...}
            #
            # alors que les moteurs utilisent :
            #
            #     candle.open
            #     candle.high
            #     candle.low
            #     candle.close
            #
            # On normalise donc immédiatement les données.
            #
            candles_by_tf[tf] = _normalize_candles(
                raw_candles
            )

        except Exception:
            candles_by_tf[tf] = []

    h4_candles = candles_by_tf[
        "H4"
    ]

    h1_candles = candles_by_tf[
        "H1"
    ]

    m15_candles = candles_by_tf[
        "M15"
    ]

    m5_candles = candles_by_tf[
        "M5"
    ]

    if not m15_candles:
        return {
            "status": "NO_DATA",
            "symbol": symbol,
            "direction": (
                Direction.NEUTRAL.value
            ),
            "score": 0.0,
            "rr": 0.0,
            "scenario": "NO_DATA",
            "reason": (
                "M15_DATA_UNAVAILABLE"
            ),
        }

    # ------------------------------------------------------------------------
    # PRICE
    # ------------------------------------------------------------------------

    entry = _last_price(
        m15_candles
    )

    if entry <= 0:
        return {
            "status": "NO_DATA",
            "symbol": symbol,
            "direction": (
                Direction.NEUTRAL.value
            ),
            "score": 0.0,
            "rr": 0.0,
            "scenario": "NO_DATA",
            "reason": "INVALID_PRICE",
        }

    # ------------------------------------------------------------------------
    # H4 / H1 / M15 STRUCTURE
    # ------------------------------------------------------------------------

    h4_structure = _analyse_structure(
        h4_candles
    )

    h1_structure = _analyse_structure(
        h1_candles
    )

    m15_structure = _analyse_structure(
        m15_candles
    )

    h4_direction = _structure_direction(
        h4_structure
    )

    h1_direction = _structure_direction(
        h1_structure
    )

    m15_direction = _structure_direction(
        m15_structure
    )

    h4_strength = _structure_strength(
        h4_structure
    )

    h1_strength = _structure_strength(
        h1_structure
    )

    m15_strength = _structure_strength(
        m15_structure
    )

    # ------------------------------------------------------------------------
    # DIRECTION
    # ------------------------------------------------------------------------

    direction = resolve_direction(
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
        requested_direction=(
            requested_direction
        ),
    )

    if direction == Direction.NEUTRAL:
        return {
            "status": "REJECT",
            "symbol": symbol,
            "direction": (
                Direction.NEUTRAL.value
            ),
            "score": 0.0,
            "rr": 0.0,
            "scenario": "RANGE",
            "reason": (
                "NO_VALID_DIRECTION"
            ),
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": Direction.NEUTRAL.value,
        }

    if not _primary_alignment_valid(
        h4_direction,
        h1_direction,
        m15_direction,
    ):
        return {
            "status": "REJECT",
            "symbol": symbol,
            "direction": direction.value,
            "score": 0.0,
            "rr": 0.0,
            "scenario": "RANGE",
            "reason": (
                "PRIMARY_STRUCTURE_INVALID"
            ),
        }

    # ------------------------------------------------------------------------
    # TREND CONTEXT
    # ------------------------------------------------------------------------

    trend = TrendContext(
        h4=h4_direction,
        h4_strength=h4_strength,
    )

    # ------------------------------------------------------------------------
    # M15 LIQUIDITY
    # ------------------------------------------------------------------------

    liquidity_result = _analyse_liquidity(
        m15_candles,
        direction,
    )

    liquidity_sweep = _liquidity_sweep(
        liquidity_result,
        direction,
    )

    liquidity_quality = _liquidity_quality(
        liquidity_result
    )

    # ------------------------------------------------------------------------
    # M15 DISPLACEMENT
    # ------------------------------------------------------------------------

    displacement_result = _analyse_displacement(
        m15_candles,
        direction,
    )

    displacement_valid = _displacement_valid(
        displacement_result,
        direction,
    )

    # ------------------------------------------------------------------------
    # DISPLACEMENT AFTER SWEEP
    # ------------------------------------------------------------------------

    displacement_after_sweep = False

    if liquidity_sweep:
        try:
            displacement_after_sweep = bool(
                detect_displacement_after_sweep(
                    m15_candles,
                    direction=direction,
                )
            )

        except Exception:
            displacement_after_sweep = (
                displacement_valid
            )

    # ------------------------------------------------------------------------
    # ORDER BLOCK
    # ------------------------------------------------------------------------

    ob_result = _analyse_order_blocks(
        m15_candles,
        direction,
    )

    ob = _best_order_block(
        ob_result,
        direction,
    )

    # ------------------------------------------------------------------------
    # FVG
    # ------------------------------------------------------------------------

    fvg_result = _analyse_fvg(
        m15_candles,
        direction,
    )

    fvg = _best_fvg(
        fvg_result,
        direction,
    )

    # ------------------------------------------------------------------------
    # PREMIUM / DISCOUNT
    # ------------------------------------------------------------------------

    premium_discount_result = (
        _analyse_premium_discount(
            m15_candles,
            entry,
            direction,
        )
    )

    premium_discount_zone = (
        _premium_discount_zone(
            premium_discount_result
        )
    )

    premium_discount_strength = (
        _premium_discount_strength(
            premium_discount_result
        )
    )

    premium_discount_valid = (
        _safe_bool(
            _get(
                premium_discount_result,
                "valid",
                False,
            )
        )
    )

    # ------------------------------------------------------------------------
    # SUPPORT / RESISTANCE
    # ------------------------------------------------------------------------

    sr_result = _analyse_support_resistance(
        m15_candles,
        entry,
        direction,
    )

    sr = _best_support_resistance(
        sr_result,
        direction,
    )

    # ------------------------------------------------------------------------
    # M5 CONFIRMATION
    # ------------------------------------------------------------------------

    m5_confirmation = _build_m5_confirmation(
        m5_candles,
        direction,
    )

    m5_strength = confirmation_strength(
        m5_confirmation
    )

    # M5 volontairement NON BLOQUANT.
    m5_direction = (
        m5_confirmation.direction
    )

    # ------------------------------------------------------------------------
    # BOS / CHOCH
    # ------------------------------------------------------------------------

    h1_bos = _structure_has_event(
        h1_structure,
        "bos",
    )

    h1_choch = _structure_has_event(
        h1_structure,
        "choch",
    )

    m15_bos = _structure_has_event(
        m15_structure,
        "bos",
    )

    m15_choch = _structure_has_event(
        m15_structure,
        "choch",
    )

    bos = (
        h1_bos
        or m15_bos
    )

    choch = (
        h1_choch
        or m15_choch
    )

    # ------------------------------------------------------------------------
    # SCENARIO
    # ------------------------------------------------------------------------

    scenario = _determine_scenario(
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
        direction=direction,
        liquidity_sweep=liquidity_sweep,
        displacement_valid=(
            displacement_valid
            or displacement_after_sweep
        ),
        bos=bos,
        choch=choch,
    )

    # ------------------------------------------------------------------------
    # CONFLUENCE
    # ------------------------------------------------------------------------

    structure_confirmed = (
        h1_direction == direction
        or m15_direction == direction
        or (
            h4_direction == direction
            and h1_direction == Direction.NEUTRAL
        )
    )

    confluences = _count_confluences(
        structure_confirmed=(
            structure_confirmed
        ),
        liquidity_sweep=(
            liquidity_sweep
        ),
        displacement_valid=(
            displacement_valid
            or displacement_after_sweep
        ),
        order_block=(
            ob is not None
        ),
        fvg=(
            fvg is not None
        ),
        premium_discount_valid=(
            premium_discount_valid
        ),
        sr=sr,
        m5_confirmation=(
            m5_confirmation
        ),
    )

    # ------------------------------------------------------------------------
    # ZONE
    # ------------------------------------------------------------------------

    zone = _build_zone(
        direction=direction,
        sr=sr,
        ob=ob,
        fvg=fvg,
        h1_strength=h1_strength,
        m15_strength=m15_strength,
        structure_confirmed=(
            structure_confirmed
        ),
        liquidity_nearby=(
            liquidity_sweep
            or liquidity_quality >= 50
        ),
    )

    if zone is None:
        return {
            "status": "REJECT",
            "symbol": symbol,
            "direction": direction.value,
            "score": 0.0,
            "rr": 0.0,
            "scenario": scenario,
            "reason": "NO_VALID_ZONE",
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": m5_direction.value,
            "confluences": confluences,
        }

    # ------------------------------------------------------------------------
    # SL / TP
    # ------------------------------------------------------------------------

    stop_loss, take_profit = (
        _build_trade_geometry(
            candles=m15_candles,
            direction=direction,
            entry=entry,
            ob=ob,
            fvg=fvg,
            sr=sr,
        )
    )

    # ------------------------------------------------------------------------
    # RR
    # ------------------------------------------------------------------------

    try:
        rr = float(
            calculate_rr(
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        )

    except Exception:
        rr = 0.0

    # ------------------------------------------------------------------------
    # GEOMETRY
    # ------------------------------------------------------------------------

    geometry_valid = False

    try:
        geometry_valid = bool(
            validate_trade_geometry(
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                direction=direction,
            )
        )

    except TypeError:
        try:
            geometry_valid = bool(
                validate_trade_geometry(
                    entry,
                    stop_loss,
                    take_profit,
                    direction,
                )
            )

        except Exception:
            geometry_valid = (
                rr >= CONFIG.MINIMUM_RR
            )

    except Exception:
        geometry_valid = (
            rr >= CONFIG.MINIMUM_RR
        )

    if not geometry_valid:
        return {
            "status": "REJECT",
            "symbol": symbol,
            "direction": direction.value,
            "score": 0.0,
            "rr": rr,
            "scenario": scenario,
            "reason": (
                "INVALID_TRADE_GEOMETRY"
            ),
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": m5_direction.value,
        }

    if rr < CONFIG.MINIMUM_RR:
        return {
            "status": "REJECT",
            "symbol": symbol,
            "direction": direction.value,
            "score": 0.0,
            "rr": rr,
            "scenario": scenario,
            "reason": "RR_BELOW_MINIMUM",
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": m5_direction.value,
        }

    # ------------------------------------------------------------------------
    # FINAL ZONE VALIDATION
    # ------------------------------------------------------------------------

    entry_distance = abs(
        entry
        - zone.key_level
    )

    zone = Zone(
        direction=zone.direction,
        timeframe=zone.timeframe,
        low=zone.low,
        high=zone.high,
        h1_strength=zone.h1_strength,
        m15_strength=zone.m15_strength,
        kind=zone.kind,
        structure_confirmed=(
            zone.structure_confirmed
        ),
        liquidity_nearby=(
            zone.liquidity_nearby
        ),
        order_block=(
            zone.order_block
        ),
        fvg=(
            zone.fvg
        ),
        created_at=zone.created_at,
        level_type=zone.level_type,
        key_level=zone.key_level,
        breakout_confirmed=(
            zone.breakout_confirmed
        ),
        breakout_direction=(
            zone.breakout_direction
        ),
        retest_confirmed=(
            zone.retest_confirmed
        ),
        rejection_confirmed=(
            zone.rejection_confirmed
            or m5_confirmation.rejection
        ),
        candle_confirmation=(
            m5_confirmation.candle_confirmation
        ),
        entry_valid=(
            zone.low <= entry <= zone.high
            or (
                entry_distance
                <= max(
                    abs(
                        zone.high
                        - zone.low
                    ),
                    _atr_from_candles(
                        m15_candles
                    ) * 0.50,
                )
            )
        ),
        entry_distance=entry_distance,
    )

    # ------------------------------------------------------------------------
    # SCORE
    # ------------------------------------------------------------------------

    score = _calculate_final_score(
        trend=trend,
        zone=zone,
        confirmation=m5_confirmation,
        rr=rr,
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
        direction=direction,
        scenario=scenario,
        liquidity_result=liquidity_result,
        displacement_result=(
            displacement_result
        ),
        ob=ob,
        fvg=fvg,
        premium_discount_result=(
            premium_discount_result
        ),
        sr=sr,
        m5=m5_confirmation,
        spread_ok=True,
        session_ok=True,
    )

    score = max(
        0.0,
        min(
            100.0,
            score,
        ),
    )

    # ------------------------------------------------------------------------
    # NEWS
    # ------------------------------------------------------------------------

    news_allowed = _check_news(
        symbol
    )

    if not news_allowed:
        return {
            "status": "NEWS_BLOCKED",
            "symbol": symbol,
            "direction": direction.value,
            "score": score,
            "rr": rr,
            "scenario": scenario,
            "reason": (
                "HIGH_IMPACT_NEWS"
            ),
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": m5_direction.value,
        }

    # ------------------------------------------------------------------------
    # SCORE THRESHOLD
    # ------------------------------------------------------------------------

    if not should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    ):
        return {
            "status": "REJECT",
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
            "reason": (
                "SCORE_BELOW_THRESHOLD"
            ),
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": m5_direction.value,
            "confluences": confluences,
            "premium_discount": (
                premium_discount_zone
            ),
            "premium_discount_strength": (
                premium_discount_strength
            ),
            "liquidity_sweep": (
                liquidity_sweep
            ),
            "liquidity_quality": (
                liquidity_quality
            ),
            "displacement": (
                displacement_valid
            ),
            "displacement_after_sweep": (
                displacement_after_sweep
            ),
            "order_block": (
                ob is not None
            ),
            "fvg": (
                fvg is not None
            ),
            "m5_strength": (
                m5_strength
            ),
        }

    # ------------------------------------------------------------------------
    # BUILD SIGNAL
    # ------------------------------------------------------------------------

    signal = None

    try:
        signal = build_signal(
            symbol=symbol,
            trend=trend,
            zone=zone,
            confirmation=m5_confirmation,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            spread_ok=True,
            session_ok=True,
            requested_direction=direction,
            scenario=scenario,
        )

    except Exception:
        signal = None

    # ------------------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------------------

    if signal is None:
        return {
            "status": "REJECT",
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
            "reason": (
                "SIGNAL_ENGINE_REJECTED"
            ),
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": m5_direction.value,
            "confluences": confluences,
        }

    return {
        "status": "ACTIVE",
        "symbol": symbol,
        "direction": direction.value,

        "score": round(
            _safe_float(
                _get(
                    signal,
                    "score",
                    score,
                )
            ),
            2,
        ),

        "rr": round(
            _safe_float(
                _get(
                    signal,
                    "rr",
                    rr,
                )
            ),
            2,
        ),

        "entry": round(
            entry,
            8,
        ),

        "stop_loss": round(
            stop_loss,
            8,
        ),

        "take_profit": round(
            take_profit,
            8,
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

        "confluences": confluences,

        "liquidity_sweep": (
            liquidity_sweep
        ),

        "liquidity_quality": round(
            liquidity_quality,
            2,
        ),

        "displacement": (
            displacement_valid
        ),

        "displacement_after_sweep": (
            displacement_after_sweep
        ),

        "order_block": (
            ob is not None
        ),

        "order_block_fresh": (
            _ob_fresh(ob)
        ),

        "order_block_mitigated": (
            _ob_mitigated(ob)
        ),

        "order_block_strength": round(
            _ob_strength(ob),
            2,
        ),

        "fvg": (
            fvg is not None
        ),

        "fvg_fresh": (
            _fvg_fresh(fvg)
        ),

        "fvg_filled": (
            _fvg_filled(fvg)
        ),

        "fvg_atr_ratio": round(
            _fvg_atr_ratio(fvg),
            4,
        ),

        "premium_discount": (
            premium_discount_zone
        ),

        "premium_discount_strength": round(
            premium_discount_strength,
            2,
        ),

        "support_resistance": (
            {
                "type": _get(
                    sr,
                    "level_type",
                    "NONE",
                ),
                "key_level": _safe_float(
                    _get(
                        sr,
                        "key_level",
                        0.0,
                    )
                ),
                "strength": _safe_float(
                    _get(
                        sr,
                        "strength",
                        0.0,
                    )
                ),
                "reactions": int(
                    _safe_float(
                        _get(
                            sr,
                            "reactions",
                            0,
                        )
                    )
                ),
                "breakout": _safe_bool(
                    _get(
                        sr,
                        "breakout",
                        False,
                    )
                ),
                "retest": _safe_bool(
                    _get(
                        sr,
                        "retest",
                        False,
                    )
                ),
                "rejection": _safe_bool(
                    _get(
                        sr,
                        "rejection",
                        False,
                    )
                ),
            }
            if sr is not None
            else None
        ),

        "m5_confirmation": {
            "retest": (
                m5_confirmation.retest
            ),
            "rejection": (
                m5_confirmation.rejection
            ),
            "liquidity_sweep": (
                m5_confirmation.liquidity_sweep
            ),
            "micro_bos": (
                m5_confirmation.micro_bos
            ),
            "candle_confirmation": (
                m5_confirmation.candle_confirmation
            ),
        },

        "signal": signal,
    }


# ============================================================================
# ALIASES COMPATIBILITE
# ============================================================================

analyser_marche_complet = (
    analyser_marche
)

run_analysis = (
    analyser_marche
)

analyze_market = (
    analyser_marche
)

analyser_pipeline = (
    analyser_marche
)