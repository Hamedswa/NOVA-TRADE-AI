"""
NOVA TRADE AI
analysis/pipeline.py

PIPELINE PRINCIPAL D'ANALYSE

Architecture :

    Données
        ↓
    Nettoyage / réduction du bruit
        ↓
    H4 + H1 + M15
        ↓
    Alignement principal
        ↓
    Recherche MULTI-ZONES
        ↓
    Breakout
        ↓
    Momentum / vitesse du breakout
        ↓
    Retest
        ↓
    Rejection
        ↓
    Confirmation candle M15
        ↓
    Volatilité / ATR
        ↓
    Liquidité / M5
        ↓
    M5 = confirmation secondaire NON BLOQUANTE
        ↓
    SL / TP / RR
        ↓
    Score >= 60
        ↓
    News / marché
        ↓
    Signal final

RÈGLES :

    - H4 + H1 + M15 doivent être parfaitement alignés.
    - D1 n'est PAS utilisé.
    - M5 est secondaire et NON BLOQUANT.
    - Score minimum : 60.
    - RR minimum : 2.0.
    - Aucun signal forcé.
    - Plusieurs zones candidates sont testées.
    - Breakout absent = WAIT.
    - Retest absent = WAIT.
    - Rejection absente = WAIT.
    - Confirmation candle absente = WAIT.
    - Momentum insuffisant = WAIT.
    - Crypto indépendante de Twelve Data.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


logger = logging.getLogger(__name__)


# ============================================================================
# IMPORTS
# ============================================================================

try:
    from config import CONFIG
except Exception:
    CONFIG = None


try:
    from market_data import market_data
except Exception:
    market_data = None


try:
    from risk.risk_manager import calculate_rr
except Exception:

    def calculate_rr(
        entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:

        risk = abs(
            float(entry) - float(stop_loss)
        )

        reward = abs(
            float(take_profit) - float(entry)
        )

        if risk <= 0:
            return 0.0

        return reward / risk


try:
    from signals.signal_engine import build_signal
except Exception:
    build_signal = None


try:
    from scoring.scoring_engine import calculate_score
except Exception:

    try:
        from scoring import calculate_score
    except Exception:
        calculate_score = None


try:
    from economic_calendar import economic_filter
except Exception:
    economic_filter = None


# ============================================================================
# CONSTANTES
# ============================================================================

TIMEFRAMES: Tuple[str, ...] = (
    "H4",
    "H1",
    "M15",
    "M5",
)

PRIMARY_TIMEFRAMES: Tuple[str, ...] = (
    "H4",
    "H1",
    "M15",
)

CRYPTO_SYMBOLS = {
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "BNB/USD",
    "XRP/USD",
}

DIRECTIONS = {
    "BUY",
    "SELL",
    "NEUTRAL",
}

MINIMUM_CANDLES = 20

# Nombre maximum de zones à examiner
MAX_ZONE_CANDIDATES = 8

# Nombre de bougies M15 utilisées pour rechercher un breakout
BREAKOUT_LOOKBACK = 8

# Nombre de bougies maximum après breakout pour rechercher le retest
RETEST_LOOKBACK = 12

# Tolérance de regroupement des niveaux
LEVEL_CLUSTER_PERCENT = 0.0005


# ============================================================================
# HELPERS
# ============================================================================

def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:

        number = float(value)

        if not math.isfinite(number):
            return default

        return number

    except Exception:
        return default


def _normalize_direction(
    value: Any,
) -> str:

    if value is None:
        return "NEUTRAL"

    text = str(
        value
    ).strip().upper()

    aliases = {
        "LONG": "BUY",
        "SHORT": "SELL",
        "BULLISH": "BUY",
        "BEARISH": "SELL",
        "HAUSSIER": "BUY",
        "BAISSIER": "SELL",
        "FLAT": "NEUTRAL",
        "NONE": "NEUTRAL",
        "N/A": "NEUTRAL",
    }

    text = aliases.get(
        text,
        text,
    )

    if text not in DIRECTIONS:
        return "NEUTRAL"

    return text


def _is_crypto_symbol(
    symbol: str,
) -> bool:

    normalized = str(
        symbol or ""
    ).strip().upper()

    return normalized in CRYPTO_SYMBOLS


def _utc_now() -> datetime:

    return datetime.now(
        timezone.utc
    )


# ============================================================================
# TWELVE DATA
# ============================================================================

def _get_twelve_data_status() -> Dict[str, Any]:

    if market_data is None:

        return {
            "available": True,
            "cooldown": 0,
        }

    try:

        getter = getattr(
            market_data,
            "get_provider_status",
            None,
        )

        if callable(getter):

            status = getter()

            if isinstance(
                status,
                dict,
            ):

                twelve = status.get(
                    "twelve_data",
                    status,
                )

                if isinstance(
                    twelve,
                    dict,
                ):

                    available = twelve.get(
                        "available",
                        twelve.get(
                            "is_available",
                            True,
                        ),
                    )

                    cooldown = twelve.get(
                        "cooldown",
                        twelve.get(
                            "cooldown_seconds",
                            0,
                        ),
                    )

                    return {
                        "available": bool(
                            available
                        ),
                        "cooldown": max(
                            0,
                            int(
                                _safe_float(
                                    cooldown,
                                    0,
                                )
                            ),
                        ),
                    }

        available_fn = getattr(
            market_data,
            "twelve_data_available",
            None,
        )

        if callable(
            available_fn
        ):

            available = bool(
                available_fn()
            )

            cooldown = 0

            cooldown_fn = getattr(
                market_data,
                "get_twelve_data_cooldown",
                None,
            )

            if callable(
                cooldown_fn
            ):

                cooldown = max(
                    0,
                    int(
                        _safe_float(
                            cooldown_fn(),
                            0,
                        )
                    ),
                )

            return {
                "available": available,
                "cooldown": cooldown,
            }

    except Exception as exc:

        logger.debug(
            "Statut Twelve Data inaccessible : %s",
            exc,
        )

    return {
        "available": True,
        "cooldown": 0,
    }


def _twelve_data_ready(
    symbol: str,
) -> Tuple[bool, str]:

    # Crypto = Coinbase uniquement.
    if _is_crypto_symbol(
        symbol
    ):
        return True, ""

    status = _get_twelve_data_status()

    available = bool(
        status.get(
            "available",
            True,
        )
    )

    cooldown = max(
        0,
        int(
            _safe_float(
                status.get(
                    "cooldown",
                    0,
                ),
                0,
            )
        ),
    )

    if not available:

        if cooldown > 0:

            return (
                False,
                (
                    "Twelve Data temporairement limité "
                    f"— cooldown {cooldown}s"
                ),
            )

        return (
            False,
            "Twelve Data temporairement indisponible",
        )

    return True, ""


# ============================================================================
# DONNÉES
# ============================================================================

def _extract_candles(
    symbol: str,
    timeframe: str,
) -> List[Any]:

    if market_data is None:

        logger.error(
            "DATA %s %s : market_data indisponible",
            symbol,
            timeframe,
        )

        return []

    try:

        getter = getattr(
            market_data,
            "get_candles",
            None,
        )

        if not callable(
            getter
        ):

            logger.error(
                "DATA %s %s : get_candles indisponible",
                symbol,
                timeframe,
            )

            return []

        candles = None

        try:

            candles = getter(
                symbol,
                timeframe,
            )

        except TypeError:
            pass

        if candles is None:

            try:

                candles = getter(
                    symbol=symbol,
                    timeframe=timeframe,
                )

            except TypeError:
                pass

        if candles is None:

            try:

                candles = getter(
                    symbol=symbol,
                    interval=timeframe,
                )

            except TypeError:
                pass

        if candles is None:

            if not _is_crypto_symbol(
                symbol
            ):

                ready, reason = (
                    _twelve_data_ready(
                        symbol
                    )
                )

                if not ready:

                    logger.warning(
                        "%s",
                        reason,
                    )

                    return []

            logger.warning(
                "DATA %s %s : aucune donnée disponible.",
                symbol,
                timeframe,
            )

            return []

        if isinstance(
            candles,
            dict,
        ):

            found = False

            for key in (
                "candles",
                "data",
                "values",
                "results",
            ):

                value = candles.get(
                    key
                )

                if isinstance(
                    value,
                    list,
                ):

                    candles = value
                    found = True
                    break

            if not found:

                logger.warning(
                    (
                        "DATA %s %s : "
                        "réponse fournisseur sans chandeliers."
                    ),
                    symbol,
                    timeframe,
                )

                return []

        if not isinstance(
            candles,
            (list, tuple),
        ):

            logger.warning(
                (
                    "DATA %s %s : "
                    "format de données invalide."
                ),
                symbol,
                timeframe,
            )

            return []

        result = list(
            candles
        )

        if not result:

            if not _is_crypto_symbol(
                symbol
            ):

                ready, reason = (
                    _twelve_data_ready(
                        symbol
                    )
                )

                if not ready:

                    logger.warning(
                        "%s",
                        reason,
                    )

                    return []

            logger.warning(
                "DATA %s %s : aucune donnée disponible.",
                symbol,
                timeframe,
            )

            return []

        logger.info(
            "DATA %s %s : %s bougies reçues.",
            symbol,
            timeframe,
            len(result),
        )

        return result

    except Exception as exc:

        if not _is_crypto_symbol(
            symbol
        ):

            ready, reason = (
                _twelve_data_ready(
                    symbol
                )
            )

            if not ready:

                logger.warning(
                    "%s",
                    reason,
                )

                return []

        logger.error(
            "DATA %s %s erreur : %s",
            symbol,
            timeframe,
            exc,
        )

        return []


def _validate_candles(
    candles: Sequence[Any],
    minimum: int = MINIMUM_CANDLES,
) -> bool:

    if candles is None:
        return False

    try:
        return len(candles) >= minimum
    except Exception:
        return False


# ============================================================================
# OHLC
# ============================================================================

def _candle_value(
    candle: Any,
    key: str,
    default: float = 0.0,
) -> float:

    if candle is None:
        return default

    try:

        if isinstance(
            candle,
            dict,
        ):

            value = candle.get(
                key
            )

            if value is None:
                value = candle.get(
                    key.lower()
                )

            if value is None:
                value = candle.get(
                    key.upper()
                )

            return _safe_float(
                value,
                default,
            )

        value = getattr(
            candle,
            key,
            None,
        )

        return _safe_float(
            value,
            default,
        )

    except Exception:
        return default


def _open(candle: Any) -> float:

    return _candle_value(
        candle,
        "open",
    )


def _close(candle: Any) -> float:

    return _candle_value(
        candle,
        "close",
    )


def _high(candle: Any) -> float:

    return _candle_value(
        candle,
        "high",
    )


def _low(candle: Any) -> float:

    return _candle_value(
        candle,
        "low",
    )


# ============================================================================
# ATR
# ============================================================================

def _calculate_atr(
    candles: Sequence[Any],
    period: int = 14,
) -> float:

    if not candles or len(candles) < 2:
        return 0.0

    true_ranges: List[float] = []

    previous_close: Optional[float] = None

    for candle in candles:

        high = _high(candle)
        low = _low(candle)
        close = _close(candle)

        if high <= 0 or low <= 0:
            continue

        if previous_close is None:

            tr = high - low

        else:

            tr = max(
                high - low,
                abs(
                    high - previous_close
                ),
                abs(
                    low - previous_close
                ),
            )

        if tr >= 0:
            true_ranges.append(
                tr
            )

        previous_close = close

    if not true_ranges:
        return 0.0

    values = true_ranges[-period:]

    return sum(values) / len(values)


# ============================================================================
# SWINGS
# ============================================================================

def _swing_highs(
    candles: Sequence[Any],
    lookback: int = 2,
) -> List[float]:

    highs: List[float] = []

    if len(candles) < (
        lookback * 2 + 1
    ):
        return highs

    for i in range(
        lookback,
        len(candles) - lookback,
    ):

        current = _high(
            candles[i]
        )

        if current <= 0:
            continue

        valid = True

        for j in range(
            i - lookback,
            i + lookback + 1,
        ):

            if j == i:
                continue

            if _high(
                candles[j]
            ) >= current:

                valid = False
                break

        if valid:
            highs.append(
                current
            )

    return highs


def _swing_lows(
    candles: Sequence[Any],
    lookback: int = 2,
) -> List[float]:

    lows: List[float] = []

    if len(candles) < (
        lookback * 2 + 1
    ):
        return lows

    for i in range(
        lookback,
        len(candles) - lookback,
    ):

        current = _low(
            candles[i]
        )

        if current <= 0:
            continue

        valid = True

        for j in range(
            i - lookback,
            i + lookback + 1,
        ):

            if j == i:
                continue

            if _low(
                candles[j]
            ) <= current:

                valid = False
                break

        if valid:
            lows.append(
                current
            )

    return lows


# ============================================================================
# STRUCTURE
# ============================================================================

def _structure_direction(
    candles: Sequence[Any],
) -> str:

    if not candles or len(candles) < 10:
        return "NEUTRAL"

    highs = _swing_highs(
        candles,
        lookback=2,
    )

    lows = _swing_lows(
        candles,
        lookback=2,
    )

    if len(highs) < 2 or len(lows) < 2:
        return "NEUTRAL"

    last_high = highs[-1]
    previous_high = highs[-2]

    last_low = lows[-1]
    previous_low = lows[-2]

    if (
        last_high > previous_high
        and last_low > previous_low
    ):
        return "BUY"

    if (
        last_high < previous_high
        and last_low < previous_low
    ):
        return "SELL"

    return "NEUTRAL"


# ============================================================================
# ALIGNEMENT
# ============================================================================

def _primary_alignment(
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
) -> str:

    h4 = _normalize_direction(
        h4_direction
    )

    h1 = _normalize_direction(
        h1_direction
    )

    m15 = _normalize_direction(
        m15_direction
    )

    if (
        h4 == "NEUTRAL"
        or h1 == "NEUTRAL"
        or m15 == "NEUTRAL"
    ):
        return "NEUTRAL"

    if h4 == h1 == m15:
        return h4

    return "NEUTRAL"


# ============================================================================
# ZONES CANDIDATES
# ============================================================================

def _build_zone_candidates(
    candles: Sequence[Any],
    direction: str,
    max_zones: int = MAX_ZONE_CANDIDATES,
) -> List[Tuple[float, float]]:

    direction = _normalize_direction(
        direction
    )

    if not candles:
        return []

    recent = list(
        candles
    )[-80:]

    candidates: List[float] = []

    if direction == "BUY":

        # BUY = recherche de résistances à casser.
        candidates.extend(
            _swing_highs(
                recent,
                lookback=2,
            )
        )

        candidates.extend(
            _high(c)
            for c in recent[-25:]
            if _high(c) > 0
        )

    elif direction == "SELL":

        # SELL = recherche de supports à casser.
        candidates.extend(
            _swing_lows(
                recent,
                lookback=2,
            )
        )

        candidates.extend(
            _low(c)
            for c in recent[-25:]
            if _low(c) > 0
        )

    clean: List[float] = []

    for value in candidates:

        value = _safe_float(
            value
        )

        if value <= 0:
            continue

        tolerance = max(
            abs(value)
            * LEVEL_CLUSTER_PERCENT,
            1e-8,
        )

        if not any(
            abs(
                value - existing
            ) <= tolerance
            for existing in clean
        ):

            clean.append(
                value
            )

    current_price = _close(
        recent[-1]
    )

    if current_price > 0:

        clean.sort(
            key=lambda x: abs(
                x - current_price
            )
        )

    else:

        clean.reverse()

    clean = clean[
        :max_zones
    ]

    zones: List[
        Tuple[float, float]
    ] = []

    for level in clean:

        width = max(
            abs(level) * 0.0005,
            1e-8,
        )

        zones.append(
            (
                level - width,
                level + width,
            )
        )

    return zones


# ============================================================================
# BREAKOUT DÉTAILLÉ
# ============================================================================

def _find_breakout(
    candles: Sequence[Any],
    direction: str,
    level_low: float,
    level_high: float,
) -> Optional[int]:

    direction = _normalize_direction(
        direction
    )

    if not candles:
        return None

    if (
        level_low <= 0
        or level_high <= 0
    ):
        return None

    start = max(
        0,
        len(candles)
        - BREAKOUT_LOOKBACK,
    )

    for index in range(
        start,
        len(candles),
    ):

        candle = candles[index]

        close_price = _close(
            candle
        )

        open_price = _open(
            candle
        )

        if (
            close_price <= 0
            or open_price <= 0
        ):
            continue

        if direction == "BUY":

            if (
                close_price
                > level_high
            ):

                return index

        elif direction == "SELL":

            if (
                close_price
                < level_low
            ):

                return index

    return None


def _breakout_confirmed(
    candles: Sequence[Any],
    direction: str,
    level_low: float,
    level_high: float,
) -> bool:

    return (
        _find_breakout(
            candles,
            direction,
            level_low,
            level_high,
        )
        is not None
    )


# ============================================================================
# MOMENTUM / VITESSE DU BREAKOUT
# ============================================================================

def _analyze_breakout_momentum(
    candles: Sequence[Any],
    direction: str,
    breakout_index: Optional[int],
    atr: float = 0.0,
) -> Dict[str, Any]:

    direction = _normalize_direction(
        direction
    )

    if (
        not candles
        or breakout_index is None
        or breakout_index < 0
        or breakout_index >= len(candles)
    ):

        return {
            "valid": False,
            "speed": 0.0,
            "body_ratio": 0.0,
            "range_ratio": 0.0,
            "expansion": False,
            "breakout_index": None,
        }

    candle = candles[
        breakout_index
    ]

    open_price = _open(
        candle
    )

    close_price = _close(
        candle
    )

    high = _high(
        candle
    )

    low = _low(
        candle
    )

    candle_range = (
        high - low
    )

    body = abs(
        close_price - open_price
    )

    if candle_range <= 0:

        return {
            "valid": False,
            "speed": 0.0,
            "body_ratio": 0.0,
            "range_ratio": 0.0,
            "expansion": False,
            "breakout_index": breakout_index,
        }

    body_ratio = (
        body / candle_range
    )

    # ATR
    range_ratio = 0.0

    if atr > 0:

        range_ratio = (
            candle_range / atr
        )

    # Vitesse = déplacement sur les 3 dernières
    # bougies avant le breakout.
    speed = 0.0

    start_index = max(
        0,
        breakout_index - 3,
    )

    previous_close = _close(
        candles[start_index]
    )

    if previous_close > 0:

        speed = abs(
            close_price
            - previous_close
        ) / previous_close

    candle_direction = "NEUTRAL"

    if close_price > open_price:
        candle_direction = "BUY"

    elif close_price < open_price:
        candle_direction = "SELL"

    directional = (
        candle_direction == direction
    )

    # Expansion :
    # le breakout doit au minimum présenter
    # une bougie suffisamment active.
    expansion = (
        range_ratio >= 0.50
    )

    # Validation raisonnable :
    # direction + corps correct + amplitude minimale.
    valid = (
        directional
        and body_ratio >= 0.40
        and expansion
    )

    return {
        "valid": bool(valid),
        "speed": round(
            speed,
            8,
        ),
        "body_ratio": round(
            body_ratio,
            4,
        ),
        "range_ratio": round(
            range_ratio,
            4,
        ),
        "expansion": bool(
            expansion
        ),
        "direction": candle_direction,
        "breakout_index": breakout_index,
    }


# ============================================================================
# RETEST APRÈS BREAKOUT
# ============================================================================

def _find_retest(
    candles: Sequence[Any],
    direction: str,
    level_low: float,
    level_high: float,
    breakout_index: Optional[int],
) -> Optional[int]:

    direction = _normalize_direction(
        direction
    )

    if (
        not candles
        or breakout_index is None
    ):
        return None

    if (
        breakout_index < 0
        or breakout_index >= len(candles)
    ):
        return None

    zone_width = abs(
        level_high - level_low
    )

    tolerance = max(
        zone_width * 1.5,
        1e-8,
    )

    start = (
        breakout_index + 1
    )

    end = min(
        len(candles),
        start + RETEST_LOOKBACK,
    )

    if start >= end:
        return None

    for index in range(
        start,
        end,
    ):

        candle = candles[index]

        high = _high(candle)
        low = _low(candle)

        if (
            high <= 0
            or low <= 0
        ):
            continue

        # Le prix doit revenir dans / proche
        # de la zone après le breakout.
        overlaps = (
            high
            >= level_low - tolerance
            and low
            <= level_high + tolerance
        )

        if not overlaps:
            continue

        close_price = _close(
            candle
        )

        if direction == "BUY":

            # Le retest doit tester la zone
            # et conserver une clôture acceptable.
            if (
                low
                <= level_high + tolerance
                and close_price > 0
            ):
                return index

        elif direction == "SELL":

            if (
                high
                >= level_low - tolerance
                and close_price > 0
            ):
                return index

    return None


def _retest_confirmed(
    candles: Sequence[Any],
    direction: str,
    level_low: float,
    level_high: float,
    breakout_index: Optional[int] = None,
) -> bool:

    if breakout_index is None:

        breakout_index = _find_breakout(
            candles,
            direction,
            level_low,
            level_high,
        )

    return (
        _find_retest(
            candles,
            direction,
            level_low,
            level_high,
            breakout_index,
        )
        is not None
    )


# ============================================================================
# REJECTION APRÈS RETEST
# ============================================================================

def _find_rejection(
    candles: Sequence[Any],
    direction: str,
    retest_index: Optional[int],
) -> Optional[int]:

    direction = _normalize_direction(
        direction
    )

    if (
        not candles
        or retest_index is None
    ):
        return None

    # On analyse les bougies qui suivent le retest.
    start = max(
        retest_index,
        0,
    )

    end = min(
        len(candles),
        retest_index + 4,
    )

    for index in range(
        start,
        end,
    ):

        candle = candles[index]

        open_price = _open(
            candle
        )

        close_price = _close(
            candle
        )

        high = _high(
            candle
        )

        low = _low(
            candle
        )

        if (
            open_price <= 0
            or close_price <= 0
            or high <= 0
            or low <= 0
        ):
            continue

        body = abs(
            close_price - open_price
        )

        upper_wick = max(
            0.0,
            high
            - max(
                open_price,
                close_price,
            ),
        )

        lower_wick = max(
            0.0,
            min(
                open_price,
                close_price,
            )
            - low,
        )

        if direction == "BUY":

            if (
                close_price >= open_price
                and lower_wick >= body
            ):
                return index

        elif direction == "SELL":

            if (
                close_price <= open_price
                and upper_wick >= body
            ):
                return index

    return None


def _rejection_confirmed(
    candles: Sequence[Any],
    direction: str,
) -> bool:

    if not candles:
        return False

    index = len(candles) - 1

    return (
        _find_rejection(
            candles,
            direction,
            index,
        )
        is not None
    )


# ============================================================================
# CANDLE CONFIRMATION
# ============================================================================

def _candle_confirmation_at(
    candles: Sequence[Any],
    direction: str,
    index: Optional[int],
) -> bool:

    direction = _normalize_direction(
        direction
    )

    if (
        not candles
        or index is None
        or index < 0
        or index >= len(candles)
    ):
        return False

    candle = candles[
        index
    ]

    open_price = _open(
        candle
    )

    close_price = _close(
        candle
    )

    high = _high(
        candle
    )

    low = _low(
        candle
    )

    candle_range = (
        high - low
    )

    if candle_range <= 0:
        return False

    body = abs(
        close_price - open_price
    )

    body_ratio = (
        body / candle_range
    )

    if direction == "BUY":

        return (
            close_price > open_price
            and body_ratio >= 0.50
        )

    if direction == "SELL":

        return (
            close_price < open_price
            and body_ratio >= 0.50
        )

    return False


def _candle_confirmation(
    candles: Sequence[Any],
    direction: str,
) -> bool:

    if not candles:
        return False

    return _candle_confirmation_at(
        candles,
        direction,
        len(candles) - 1,
    )


# ============================================================================
# VALIDATION COMPLÈTE D'UNE ZONE
# ============================================================================

def _evaluate_zone(
    candles: Sequence[Any],
    direction: str,
    level_low: float,
    level_high: float,
    atr: float,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "low": level_low,
        "high": level_high,
        "key_level": (
            level_low + level_high
        ) / 2,
        "breakout_confirmed": False,
        "breakout_index": None,
        "momentum_valid": False,
        "momentum": {},
        "retest_confirmed": False,
        "retest_index": None,
        "rejection_confirmed": False,
        "rejection_index": None,
        "candle_confirmation": False,
        "complete": False,
        "stage": "ZONE",
    }

    # ------------------------------------------------------------------
    # 1. BREAKOUT
    # ------------------------------------------------------------------

    breakout_index = _find_breakout(
        candles,
        direction,
        level_low,
        level_high,
    )

    if breakout_index is None:

        result["stage"] = (
            "WAIT_BREAKOUT"
        )

        return result

    result[
        "breakout_confirmed"
    ] = True

    result[
        "breakout_index"
    ] = breakout_index

    # ------------------------------------------------------------------
    # 2. MOMENTUM
    # ------------------------------------------------------------------

    momentum = _analyze_breakout_momentum(
        candles,
        direction,
        breakout_index,
        atr,
    )

    result[
        "momentum"
    ] = momentum

    result[
        "momentum_valid"
    ] = bool(
        momentum.get(
            "valid",
            False,
        )
    )

    if not result[
        "momentum_valid"
    ]:

        result["stage"] = (
            "WAIT_MOMENTUM"
        )

        return result

    # ------------------------------------------------------------------
    # 3. RETEST
    # ------------------------------------------------------------------

    retest_index = _find_retest(
        candles,
        direction,
        level_low,
        level_high,
        breakout_index,
    )

    if retest_index is None:

        result["stage"] = (
            "WAIT_RETEST"
        )

        return result

    result[
        "retest_confirmed"
    ] = True

    result[
        "retest_index"
    ] = retest_index

    # ------------------------------------------------------------------
    # 4. REJECTION
    # ------------------------------------------------------------------

    rejection_index = _find_rejection(
        candles,
        direction,
        retest_index,
    )

    if rejection_index is None:

        result["stage"] = (
            "WAIT_REJECTION"
        )

        return result

    result[
        "rejection_confirmed"
    ] = True

    result[
        "rejection_index"
    ] = rejection_index

    # ------------------------------------------------------------------
    # 5. CANDLE CONFIRMATION
    # ------------------------------------------------------------------

    # La confirmation doit arriver après le retest.
    confirmation_index = (
        len(candles) - 1
    )

    if confirmation_index < retest_index:

        result["stage"] = (
            "WAIT_CANDLE"
        )

        return result

    candle_confirmation = (
        _candle_confirmation_at(
            candles,
            direction,
            confirmation_index,
        )
    )

    if not candle_confirmation:

        result["stage"] = (
            "WAIT_CANDLE"
        )

        return result

    result[
        "candle_confirmation"
    ] = True

    result["confirmation_index"] = (
        confirmation_index
    )

    result["complete"] = True

    result["stage"] = (
        "COMPLETE"
    )

    return result


# ============================================================================
# M5
# ============================================================================

def _m5_confirmation(
    candles: Sequence[Any],
    direction: str,
) -> Dict[str, Any]:

    direction = _normalize_direction(
        direction
    )

    if not candles:

        return {
            "valid": False,
            "direction": "NEUTRAL",
            "micro_bos": False,
            "liquidity_sweep": False,
            "retest": False,
            "rejection": False,
            "candle_confirmation": False,
        }

    m5_direction = _structure_direction(
        candles
    )

    candle_confirmation = (
        _candle_confirmation(
            candles,
            direction,
        )
    )

    rejection = (
        _rejection_confirmed(
            candles,
            direction,
        )
    )

    recent = list(
        candles
    )[-5:]

    micro_bos = (
        m5_direction == direction
    )

    liquidity_sweep = False

    if len(recent) >= 3:

        previous_lows = [
            _low(c)
            for c in recent[:-1]
            if _low(c) > 0
        ]

        previous_highs = [
            _high(c)
            for c in recent[:-1]
            if _high(c) > 0
        ]

        current = recent[-1]

        if (
            direction == "BUY"
            and previous_lows
        ):

            liquidity_sweep = (
                _low(current)
                < min(previous_lows)
                and _close(current)
                > min(previous_lows)
            )

        elif (
            direction == "SELL"
            and previous_highs
        ):

            liquidity_sweep = (
                _high(current)
                > max(previous_highs)
                and _close(current)
                < max(previous_highs)
            )

    retest = (
        rejection
        or liquidity_sweep
    )

    valid = (
        candle_confirmation
        and (
            micro_bos
            or liquidity_sweep
        )
    )

    return {
        "valid": bool(valid),
        "direction": m5_direction,
        "micro_bos": bool(
            micro_bos
        ),
        "liquidity_sweep": bool(
            liquidity_sweep
        ),
        "retest": bool(
            retest
        ),
        "rejection": bool(
            rejection
        ),
        "candle_confirmation": bool(
            candle_confirmation
        ),
    }


# ============================================================================
# SL / TP
# ============================================================================

def _build_sl_tp(
    candles: Sequence[Any],
    direction: str,
    entry: float,
    atr: float,
) -> Tuple[float, float]:

    direction = _normalize_direction(
        direction
    )

    entry = _safe_float(
        entry
    )

    atr = _safe_float(
        atr
    )

    if entry <= 0:
        return 0.0, 0.0

    if atr <= 0:
        atr = entry * 0.001

    recent = list(
        candles
    )[-20:]

    if direction == "BUY":

        lows = [
            _low(c)
            for c in recent
            if _low(c) > 0
        ]

        if lows:

            structural_sl = min(
                lows
            )

            sl = min(
                structural_sl,
                entry - atr * 0.5,
            )

        else:

            sl = entry - atr

        risk = (
            entry - sl
        )

        if risk <= 0:

            risk = atr
            sl = entry - risk

        tp = (
            entry
            + risk * 2.5
        )

        return sl, tp

    if direction == "SELL":

        highs = [
            _high(c)
            for c in recent
            if _high(c) > 0
        ]

        if highs:

            structural_sl = max(
                highs
            )

            sl = max(
                structural_sl,
                entry + atr * 0.5,
            )

        else:

            sl = entry + atr

        risk = (
            sl - entry
        )

        if risk <= 0:

            risk = atr
            sl = entry + risk

        tp = (
            entry
            - risk * 2.5
        )

        return sl, tp

    return 0.0, 0.0


# ============================================================================
# GEOMETRIE
# ============================================================================

def _validate_geometry(
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> bool:

    direction = _normalize_direction(
        direction
    )

    if direction == "BUY":

        return (
            stop_loss
            < entry
            < take_profit
        )

    if direction == "SELL":

        return (
            stop_loss
            > entry
            > take_profit
        )

    return False


# ============================================================================
# SCORE FALLBACK
# ============================================================================

def _fallback_score(
    direction: str,
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
    m5: Dict[str, Any],
    rr: float,
    momentum: Dict[str, Any],
    zone: Dict[str, Any],
) -> float:

    direction = _normalize_direction(
        direction
    )

    score = 0.0

    # H4
    if _normalize_direction(
        h4_direction
    ) == direction:
        score += 20

    # H1
    if _normalize_direction(
        h1_direction
    ) == direction:
        score += 20

    # M15
    if _normalize_direction(
        m15_direction
    ) == direction:
        score += 20

    # Zone complète
    if zone.get(
        "breakout_confirmed"
    ):
        score += 2

    if zone.get(
        "retest_confirmed"
    ):
        score += 2

    if zone.get(
        "rejection_confirmed"
    ):
        score += 2

    if zone.get(
        "candle_confirmation"
    ):
        score += 2

    if zone.get(
        "structure_confirmed"
    ):
        score += 2

    # Momentum
    if momentum.get(
        "valid"
    ):
        score += 5

    if momentum.get(
        "expansion"
    ):
        score += 5

    # M5 secondaire
    if m5.get(
        "retest"
    ):
        score += 3

    if m5.get(
        "candle_confirmation"
    ):
        score += 3

    if m5.get(
        "liquidity_sweep"
    ):
        score += 4

    # RR
    if rr >= 2.0:
        score += 5

    return min(
        100.0,
        round(
            score,
            2,
        ),
    )


def _calculate_final_score(
    *,
    symbol: str,
    direction: str,
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
    m5: Dict[str, Any],
    rr: float,
    zone: Dict[str, Any],
    momentum: Dict[str, Any],
) -> float:

    if calculate_score is not None:

        try:

            result = calculate_score(
                symbol=symbol,
                direction=direction,
                h4_direction=h4_direction,
                h1_direction=h1_direction,
                m15_direction=m15_direction,
                m5_confirmation=m5,
                rr=rr,
                zone=zone,
            )

            if isinstance(
                result,
                dict,
            ):

                value = result.get(
                    "score",
                    result.get(
                        "total",
                        0,
                    ),
                )

                return max(
                    0.0,
                    min(
                        100.0,
                        _safe_float(
                            value,
                            0,
                        ),
                    ),
                )

            return max(
                0.0,
                min(
                    100.0,
                    _safe_float(
                        result,
                        0,
                    ),
                ),
            )

        except TypeError:
            pass

        except Exception as exc:

            logger.debug(
                "Scoring engine indisponible %s : %s",
                symbol,
                exc,
            )

    return _fallback_score(
        direction=direction,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
        m5=m5,
        rr=rr,
        momentum=momentum,
        zone=zone,
    )


# ============================================================================
# NEWS
# ============================================================================

def _check_news(
    symbol: str,
) -> Tuple[bool, Optional[str]]:

    if economic_filter is None:
        return False, None

    try:

        result = economic_filter(
            symbol
        )

        if isinstance(
            result,
            tuple,
        ):

            blocked = bool(
                result[0]
            )

            reason = (
                result[1]
                if len(result) > 1
                else None
            )

            return blocked, reason

        return bool(result), None

    except Exception as exc:

        logger.warning(
            "NEWS %s : filtre indisponible : %s",
            symbol,
            exc,
        )

        return False, None


# ============================================================================
# MARCHÉ
# ============================================================================

def _market_open(
    symbol: str,
) -> bool:

    if market_data is None:
        return True

    for name in (
        "is_market_open",
        "market_is_open",
    ):

        checker = getattr(
            market_data,
            name,
            None,
        )

        if callable(checker):

            try:

                return bool(
                    checker(symbol)
                )

            except TypeError:

                try:

                    return bool(
                        checker()
                    )

                except Exception:
                    pass

            except Exception:
                pass

    return True


# ============================================================================
# RÉSULTATS
# ============================================================================

def _base_result(
    symbol: str,
    direction: str = "NEUTRAL",
    h4_direction: str = "NEUTRAL",
    h1_direction: str = "NEUTRAL",
    m15_direction: str = "NEUTRAL",
    m5_direction: str = "NEUTRAL",
) -> Dict[str, Any]:

    return {
        "symbol": symbol,
        "direction": _normalize_direction(
            direction
        ),
        "h4_direction": _normalize_direction(
            h4_direction
        ),
        "h1_direction": _normalize_direction(
            h1_direction
        ),
        "m15_direction": _normalize_direction(
            m15_direction
        ),
        "m5_direction": _normalize_direction(
            m5_direction
        ),
        "score": 0.0,
        "rr": 0.0,
        "entry": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "signal": None,
        "signal_id": None,
        "timestamp": _utc_now().isoformat(),
    }


def _wait_result(
    symbol: str,
    reason: str,
    *,
    direction: str = "NEUTRAL",
    h4_direction: str = "NEUTRAL",
    h1_direction: str = "NEUTRAL",
    m15_direction: str = "NEUTRAL",
    m5_direction: str = "NEUTRAL",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    result = _base_result(
        symbol=symbol,
        direction=direction,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
        m5_direction=m5_direction,
    )

    result.update(
        {
            "status": "WAIT",
            "reason": reason,
        }
    )

    if extra:
        result.update(
            extra
        )

    return result


def _reject_result(
    symbol: str,
    reason: str,
    *,
    direction: str = "NEUTRAL",
    h4_direction: str = "NEUTRAL",
    h1_direction: str = "NEUTRAL",
    m15_direction: str = "NEUTRAL",
    m5_direction: str = "NEUTRAL",
    score: float = 0.0,
    rr: float = 0.0,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    result = _base_result(
        symbol=symbol,
        direction=direction,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
        m5_direction=m5_direction,
    )

    result.update(
        {
            "status": "REJECT",
            "reason": reason,
            "score": round(
                _safe_float(
                    score
                ),
                2,
            ),
            "rr": round(
                _safe_float(
                    rr
                ),
                4,
            ),
        }
    )

    if extra:
        result.update(
            extra
        )

    return result


# ============================================================================
# ANALYSE PRINCIPALE
# ============================================================================

def analyze_market(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:

    symbol = str(
        symbol or "XAU/USD"
    ).strip().upper()

    logger.info(
        "========== ANALYSE %s ==========",
        symbol,
    )

    # ======================================================================
    # 1. PROVIDER
    # ======================================================================

    if not _is_crypto_symbol(
        symbol
    ):

        provider_ready, provider_reason = (
            _twelve_data_ready(
                symbol
            )
        )

        if not provider_ready:

            logger.warning(
                "%s",
                provider_reason,
            )

            return _wait_result(
                symbol,
                provider_reason,
            )

    # ======================================================================
    # 2. MARCHÉ
    # ======================================================================

    if not _market_open(
        symbol
    ):

        return _wait_result(
            symbol,
            "Marché actuellement fermé.",
        )

    # ======================================================================
    # 3. DONNÉES
    # ======================================================================

    candles: Dict[
        str,
        List[Any],
    ] = {}

    for timeframe in TIMEFRAMES:

        # Crypto ne dépend jamais du cooldown Twelve Data.
        if not _is_crypto_symbol(
            symbol
        ):

            ready, reason = (
                _twelve_data_ready(
                    symbol
                )
            )

            if not ready:

                return _wait_result(
                    symbol,
                    reason,
                )

        data = _extract_candles(
            symbol,
            timeframe,
        )

        if not data:

            if not _is_crypto_symbol(
                symbol
            ):

                ready, reason = (
                    _twelve_data_ready(
                        symbol
                    )
                )

                if not ready:

                    return _wait_result(
                        symbol,
                        reason,
                    )

            return _wait_result(
                symbol,
                (
                    f"Données indisponibles "
                    f"{timeframe} pour {symbol}."
                ),
            )

        if not _validate_candles(
            data
        ):

            return _wait_result(
                symbol,
                (
                    f"Données insuffisantes "
                    f"{timeframe} pour {symbol}."
                ),
            )

        candles[
            timeframe
        ] = data

    # ======================================================================
    # 4. DIRECTIONS
    # ======================================================================

    h4_direction = _structure_direction(
        candles["H4"]
    )

    h1_direction = _structure_direction(
        candles["H1"]
    )

    m15_direction = _structure_direction(
        candles["M15"]
    )

    logger.info(
        (
            "%s directions : "
            "H4=%s | H1=%s | M15=%s"
        ),
        symbol,
        h4_direction,
        h1_direction,
        m15_direction,
    )

    # ======================================================================
    # 5. ALIGNEMENT PRINCIPAL
    # ======================================================================

    direction = _primary_alignment(
        h4_direction,
        h1_direction,
        m15_direction,
    )

    if direction == "NEUTRAL":

        logger.info(
            "%s : H4/H1/M15 non alignés.",
            symbol,
        )

        return _reject_result(
            symbol,
            (
                "H4 + H1 + M15 "
                "ne sont pas parfaitement alignés."
            ),
            direction="NEUTRAL",
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

    logger.info(
        (
            "%s ALIGNEMENT PRINCIPAL VALIDÉ : "
            "H4=%s | H1=%s | M15=%s | direction=%s"
        ),
        symbol,
        h4_direction,
        h1_direction,
        m15_direction,
        direction,
    )

    # ======================================================================
    # 6. ATR M15
    # ======================================================================

    atr = _calculate_atr(
        candles["M15"],
        period=14,
    )

    if atr <= 0:

        return _wait_result(
            symbol,
            (
                "Alignement H4/H1/M15 valide, "
                "mais ATR M15 indisponible."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

    # ======================================================================
    # 7. RECHERCHE MULTI-ZONES
    # ======================================================================

    zone_candidates = _build_zone_candidates(
        candles["M15"],
        direction,
        max_zones=MAX_ZONE_CANDIDATES,
    )

    logger.info(
        "%s : %s zones candidates à tester.",
        symbol,
        len(zone_candidates),
    )

    if not zone_candidates:

        return _wait_result(
            symbol,
            (
                "Alignement H4/H1/M15 validé, "
                "mais aucune zone clé exploitable "
                "n'est actuellement disponible."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

    # ======================================================================
    # 8. ÉVALUATION DE TOUTES LES ZONES
    # ======================================================================

    zone_results: List[
        Dict[str, Any]
    ] = []

    for zone_number, (
        zone_low,
        zone_high,
    ) in enumerate(
        zone_candidates,
        start=1,
    ):

        evaluation = _evaluate_zone(
            candles["M15"],
            direction,
            zone_low,
            zone_high,
            atr,
        )

        evaluation[
            "zone_number"
        ] = zone_number

        zone_results.append(
            evaluation
        )

        logger.info(
            (
                "%s ZONE #%s %.5f-%.5f | "
                "stage=%s | breakout=%s | "
                "momentum=%s | retest=%s | "
                "rejection=%s | candle=%s"
            ),
            symbol,
            zone_number,
            zone_low,
            zone_high,
            evaluation.get(
                "stage"
            ),
            evaluation.get(
                "breakout_confirmed"
            ),
            evaluation.get(
                "momentum_valid"
            ),
            evaluation.get(
                "retest_confirmed"
            ),
            evaluation.get(
                "rejection_confirmed"
            ),
            evaluation.get(
                "candle_confirmation"
            ),
        )

    # ======================================================================
    # 9. RECHERCHE DE LA MEILLEURE ZONE
    # ======================================================================

    # Priorité :
    #
    # COMPLETE
    # WAIT_CANDLE
    # WAIT_REJECTION
    # WAIT_RETEST
    # WAIT_MOMENTUM
    # WAIT_BREAKOUT
    #
    # Cela permet au bot de conserver la zone
    # la plus avancée dans son cycle.

    stage_priority = {
        "COMPLETE": 6,
        "WAIT_CANDLE": 5,
        "WAIT_REJECTION": 4,
        "WAIT_RETEST": 3,
        "WAIT_MOMENTUM": 2,
        "WAIT_BREAKOUT": 1,
        "ZONE": 0,
    }

    best_zone = max(
        zone_results,
        key=lambda item: (
            stage_priority.get(
                item.get(
                    "stage",
                    "ZONE",
                ),
                0,
            ),
            -abs(
                _close(
                    candles["M15"][-1]
                )
                - item.get(
                    "key_level",
                    0.0,
                )
            ),
        ),
    )

    stage = best_zone.get(
        "stage",
        "ZONE",
    )

    logger.info(
        (
            "%s meilleure zone = #%s | "
            "stage=%s"
        ),
        symbol,
        best_zone.get(
            "zone_number"
        ),
        stage,
    )

    # ======================================================================
    # 10. SI AUCUN BREAKOUT
    # ======================================================================

    if stage == "WAIT_BREAKOUT":

        return _wait_result(
            symbol,
            (
                "H4 + H1 + M15 alignés, "
                "zones clés analysées, "
                "mais aucun breakout valide "
                "n'est encore confirmé. "
                "Surveillance en attente."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "zones_tested": len(
                    zone_results
                ),
                "zone": best_zone,
                "breakout_confirmed": False,
                "retest_confirmed": False,
                "rejection_confirmed": False,
                "candle_confirmation": False,
            },
        )

    # ======================================================================
    # 11. BREAKOUT MAIS MOMENTUM INSUFFISANT
    # ======================================================================

    if stage == "WAIT_MOMENTUM":

        return _wait_result(
            symbol,
            (
                "Breakout détecté sur une zone clé, "
                "mais la vitesse/momentum du mouvement "
                "est insuffisante. "
                "Le bot attend une impulsion plus propre."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "zones_tested": len(
                    zone_results
                ),
                "zone": best_zone,
                "breakout_confirmed": True,
                "retest_confirmed": False,
                "rejection_confirmed": False,
                "candle_confirmation": False,
                "momentum": best_zone.get(
                    "momentum",
                    {},
                ),
            },
        )

    # ======================================================================
    # 12. BREAKOUT + MOMENTUM MAIS PAS RETEST
    # ======================================================================

    if stage == "WAIT_RETEST":

        return _wait_result(
            symbol,
            (
                "Breakout + momentum confirmés. "
                "Le bot attend maintenant le retest "
                "de la zone cassée."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "zones_tested": len(
                    zone_results
                ),
                "zone": best_zone,
                "breakout_confirmed": True,
                "retest_confirmed": False,
                "rejection_confirmed": False,
                "candle_confirmation": False,
                "momentum": best_zone.get(
                    "momentum",
                    {},
                ),
            },
        )

    # ======================================================================
    # 13. RETEST MAIS PAS REJECTION
    # ======================================================================

    if stage == "WAIT_REJECTION":

        return _wait_result(
            symbol,
            (
                "Breakout + momentum + retest "
                "confirmés. "
                "Le bot attend maintenant le rejet "
                "de la zone."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "zones_tested": len(
                    zone_results
                ),
                "zone": best_zone,
                "breakout_confirmed": True,
                "retest_confirmed": True,
                "rejection_confirmed": False,
                "candle_confirmation": False,
                "momentum": best_zone.get(
                    "momentum",
                    {},
                ),
            },
        )

    # ======================================================================
    # 14. REJECTION MAIS PAS BOUGIE DE CONFIRMATION
    # ======================================================================

    if stage == "WAIT_CANDLE":

        return _wait_result(
            symbol,
            (
                "Rejet de zone confirmé. "
                "Le bot attend maintenant une bougie "
                "de confirmation M15 valide avant "
                "de calculer l'entrée."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "zones_tested": len(
                    zone_results
                ),
                "zone": best_zone,
                "breakout_confirmed": True,
                "retest_confirmed": True,
                "rejection_confirmed": True,
                "candle_confirmation": False,
                "momentum": best_zone.get(
                    "momentum",
                    {},
                ),
            },
        )

    # ======================================================================
    # 15. ZONE COMPLÈTE
    # ======================================================================

    zone_low = _safe_float(
        best_zone.get(
            "low"
        )
    )

    zone_high = _safe_float(
        best_zone.get(
            "high"
        )
    )

    momentum = best_zone.get(
        "momentum",
        {},
    )

    # ======================================================================
    # 16. ENTRY
    # ======================================================================

    current_candle = (
        candles["M5"][-1]
    )

    entry = _close(
        current_candle
    )

    if entry <= 0:

        entry = _close(
            candles["M15"][-1]
        )

    if entry <= 0:

        return _reject_result(
            symbol,
            "Prix d'entrée invalide.",
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

    # ======================================================================
    # 17. SL / TP
    # ======================================================================

    stop_loss, take_profit = (
        _build_sl_tp(
            candles["M15"],
            direction,
            entry,
            atr,
        )
    )

    if not _validate_geometry(
        direction,
        entry,
        stop_loss,
        take_profit,
    ):

        return _reject_result(
            symbol,
            "Géométrie Entry/SL/TP invalide.",
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "zone": best_zone,
            },
        )

    # ======================================================================
    # 18. RR
    # ======================================================================

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    minimum_rr = 2.0

    try:

        if CONFIG is not None:

            minimum_rr = float(
                getattr(
                    CONFIG,
                    "MINIMUM_RR",
                    2.0,
                )
            )

    except Exception:

        minimum_rr = 2.0

    if rr < minimum_rr:

        return _reject_result(
            symbol,
            (
                f"RR insuffisant : "
                f"{rr:.2f} < "
                f"{minimum_rr:.2f}"
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            rr=rr,
            extra={
                "zone": best_zone,
                "momentum": momentum,
            },
        )

    # ======================================================================
    # 19. M5 SECONDAIRE
    # ======================================================================

    m5 = _m5_confirmation(
        candles["M5"],
        direction,
    )

    logger.info(
        (
            "%s M5 SECONDARY : valid=%s | "
            "direction=%s | BOS=%s | "
            "sweep=%s | retest=%s | candle=%s"
        ),
        symbol,
        m5.get(
            "valid"
        ),
        m5.get(
            "direction"
        ),
        m5.get(
            "micro_bos"
        ),
        m5.get(
            "liquidity_sweep"
        ),
        m5.get(
            "retest"
        ),
        m5.get(
            "candle_confirmation"
        ),
    )

    # IMPORTANT :
    #
    # M5 n'est JAMAIS utilisé pour rejeter
    # un setup H4/H1/M15 déjà validé.
    #
    # Il sert uniquement à améliorer le score
    # et la qualité d'entrée.

    # ======================================================================
    # 20. ZONE FINALE
    # ======================================================================

    zone = {
        "low": zone_low,
        "high": zone_high,
        "direction": direction,
        "level_type": (
            "RESISTANCE"
            if direction == "BUY"
            else "SUPPORT"
        ),
        "key_level": (
            zone_low
            + zone_high
        ) / 2,
        "breakout_confirmed": True,
        "breakout_index": best_zone.get(
            "breakout_index"
        ),
        "retest_confirmed": True,
        "retest_index": best_zone.get(
            "retest_index"
        ),
        "rejection_confirmed": True,
        "rejection_index": best_zone.get(
            "rejection_index"
        ),
        "candle_confirmation": True,
        "entry_valid": True,
        "structure_confirmed": True,
        "momentum_valid": bool(
            momentum.get(
                "valid"
            )
        ),
        "breakout_momentum": momentum,
        "liquidity": bool(
            m5.get(
                "liquidity_sweep"
            )
        ),
    }

    # ======================================================================
    # 21. SCORE
    # ======================================================================

    score = _calculate_final_score(
        symbol=symbol,
        direction=direction,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
        m5=m5,
        rr=rr,
        zone=zone,
        momentum=momentum,
    )

    threshold = 60.0

    try:

        if CONFIG is not None:

            threshold = float(
                getattr(
                    CONFIG,
                    "SIGNAL_THRESHOLD",
                    60.0,
                )
            )

    except Exception:

        threshold = 60.0

    logger.info(
        (
            "%s SCORE FINAL = %.2f/100 | "
            "RR=%.2f | seuil=%.2f"
        ),
        symbol,
        score,
        rr,
        threshold,
    )

    if score < threshold:

        return _reject_result(
            symbol,
            (
                f"Score insuffisant : "
                f"{score:.2f} < "
                f"{threshold:.2f}"
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            m5_direction=m5.get(
                "direction",
                "NEUTRAL",
            ),
            score=score,
            rr=rr,
            extra={
                "zone": zone,
                "momentum": momentum,
                "m5_confirmation": m5,
            },
        )

    # ======================================================================
    # 22. NEWS
    # ======================================================================

    news_blocked, news_reason = (
        _check_news(
            symbol
        )
    )

    if news_blocked:

        return _wait_result(
            symbol,
            (
                news_reason
                or
                "Annonce économique importante bloquante."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            m5_direction=m5.get(
                "direction",
                "NEUTRAL",
            ),
            extra={
                "score": score,
                "rr": rr,
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "zone": zone,
                "momentum": momentum,
                "m5_confirmation": m5,
            },
        )

    # ======================================================================
    # 23. CONSTRUCTION DU SIGNAL
    # ======================================================================

    signal = None

    if build_signal is not None:

        try:

            signal = build_signal(
                symbol=symbol,
                trend={
                    "direction": direction,
                    "h4": h4_direction,
                    "h4_direction": h4_direction,
                    "h4_strength": 1.0,
                },
                zone=zone,
                confirmation=m5,
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                spread_ok=True,
                session_ok=True,
                h4_direction=h4_direction,
                h1_direction=h1_direction,
                m15_direction=m15_direction,
            )

        except TypeError:

            try:

                signal = build_signal(
                    symbol,
                    {
                        "direction": direction,
                        "h4": h4_direction,
                    },
                    zone,
                    m5,
                    entry,
                    stop_loss,
                    take_profit,
                )

            except Exception as exc:

                logger.error(
                    (
                        "SIGNAL %s : "
                        "construction impossible : %s"
                    ),
                    symbol,
                    exc,
                )

        except Exception as exc:

            logger.error(
                (
                    "SIGNAL %s : "
                    "construction impossible : %s"
                ),
                symbol,
                exc,
            )

    # ======================================================================
    # 24. SIGNAL ID
    # ======================================================================

    signal_id = None

    if signal is not None:

        if isinstance(
            signal,
            dict,
        ):

            signal_id = signal.get(
                "signal_id"
            )

        else:

            signal_id = getattr(
                signal,
                "signal_id",
                None,
            )

    # ======================================================================
    # 25. ÉCHEC CONSTRUCTION
    # ======================================================================

    if (
        build_signal is not None
        and signal is None
    ):

        return _reject_result(
            symbol,
            (
                "Setup analytique valide, "
                "mais construction du signal impossible."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            m5_direction=m5.get(
                "direction",
                "NEUTRAL",
            ),
            score=score,
            rr=rr,
            extra={
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "zone": zone,
                "momentum": momentum,
                "m5_confirmation": m5,
            },
        )

    # ======================================================================
    # 26. SIGNAL FINAL
    # ======================================================================

    result = {
        "symbol": symbol,
        "status": "ACTIVE",
        "reason": (
            "Signal validé : "
            "H4 + H1 + M15 parfaitement alignés, "
            "zone clé identifiée, breakout confirmé, "
            "momentum/vitesse validé, retest confirmé, "
            "rejection confirmée, bougie M15 confirmée, "
            "RR et score validés."
        ),
        "direction": direction,
        "score": round(
            score,
            2,
        ),
        "rr": round(
            rr,
            4,
        ),
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "sl": stop_loss,
        "tp": take_profit,
        "signal": signal,
        "signal_id": signal_id,
        "h4_direction": h4_direction,
        "h1_direction": h1_direction,
        "m15_direction": m15_direction,
        "m5_direction": m5.get(
            "direction",
            "NEUTRAL",
        ),
        "m5_confirmation": m5,
        "zone": zone,
        "momentum": momentum,
        "atr": atr,
        "zones_tested": len(
            zone_results
        ),
        "breakout_confirmed": True,
        "retest_confirmed": True,
        "rejection_confirmed": True,
        "candle_confirmation": True,
        "timestamp": _utc_now().isoformat(),
    }

    logger.info(
        (
            "=================================================="
        ),
    )

    logger.info(
        (
            "SIGNAL VALIDE %s | %s | "
            "H4=%s | H1=%s | M15=%s | "
            "score=%.2f | RR=%.2f | "
            "zones=%s | entry=%s | SL=%s | TP=%s"
        ),
        symbol,
        direction,
        h4_direction,
        h1_direction,
        m15_direction,
        score,
        rr,
        len(zone_results),
        entry,
        stop_loss,
        take_profit,
    )

    logger.info(
        (
            "=================================================="
        ),
    )

    return result


# ============================================================================
# ALIASES
# ============================================================================

def analyser_marche(
    symbol: str = "XAU/USD",
    timeframe: str = "M15",
) -> Dict[str, Any]:

    return analyze_market(
        symbol
    )


def analyser_marche_complet(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:

    return analyze_market(
        symbol
    )


def run_analysis(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:

    return analyze_market(
        symbol
    )


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "analyze_market",
    "analyser_marche",
    "analyser_marche_complet",
    "run_analysis",
]