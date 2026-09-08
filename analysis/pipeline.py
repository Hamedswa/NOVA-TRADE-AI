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
    Recherche multi-zones
        ↓
    Breakout
        ↓
    Retest
        ↓
    Rejection
        ↓
    Confirmation candle
        ↓
    Momentum / vitesse
        ↓
    Volatilité / ATR
        ↓
    Liquidité
        ↓
    M5 = confirmation secondaire
        ↓
    SL / TP / RR
        ↓
    Score
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
    - Breakout absent = WAIT, pas faux REJECT.
    - Plusieurs zones candidates sont testées.
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
            true_ranges.append(tr)

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
            highs.append(current)

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
            lows.append(current)

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
    max_zones: int = 8,
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

        # Pour BUY, on recherche des résistances
        # dont la cassure peut confirmer l'impulsion.
        candidates.extend(
            _swing_highs(
                recent,
                lookback=2,
            )
        )

        candidates.extend(
            _high(c)
            for c in recent[-20:]
            if _high(c) > 0
        )

    elif direction == "SELL":

        # Pour SELL, on recherche des supports
        # dont la cassure peut confirmer l'impulsion.
        candidates.extend(
            _swing_lows(
                recent,
                lookback=2,
            )
        )

        candidates.extend(
            _low(c)
            for c in recent[-20:]
            if _low(c) > 0
        )

    # ------------------------------------------------------------------
    # Nettoyage
    # ------------------------------------------------------------------

    clean: List[float] = []

    for value in candidates:

        value = _safe_float(
            value
        )

        if value <= 0:
            continue

        if not any(
            abs(value - existing)
            <= max(
                abs(value) * 0.0005,
                1e-8,
            )
            for existing in clean
        ):
            clean.append(value)

    # ------------------------------------------------------------------
    # Trier selon proximité au prix actuel
    # ------------------------------------------------------------------

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

    clean = clean[:max_zones]

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
# BREAKOUT
# ============================================================================

def _breakout_confirmed(
    candles: Sequence[Any],
    direction: str,
    level_low: float,
    level_high: float,
) -> bool:

    direction = _normalize_direction(
        direction
    )

    if not candles:
        return False

    if (
        level_low <= 0
        or level_high <= 0
    ):
        return False

    recent = list(
        candles
    )[-5:]

    if direction == "BUY":

        return any(
            _close(candle)
            > level_high
            for candle in recent
        )

    if direction == "SELL":

        return any(
            _close(candle)
            < level_low
            for candle in recent
        )

    return False


# ============================================================================
# RETEST
# ============================================================================

def _retest_confirmed(
    candles: Sequence[Any],
    direction: str,
    level_low: float,
    level_high: float,
) -> bool:

    direction = _normalize_direction(
        direction
    )

    if not candles:
        return False

    tolerance = max(
        abs(
            level_high - level_low
        ) * 1.5,
        1e-8,
    )

    recent = list(
        candles
    )[-12:]

    for candle in recent:

        high = _high(candle)
        low = _low(candle)

        if direction == "BUY":

            if (
                low
                <= level_high + tolerance
                and high
                >= level_low - tolerance
            ):
                return True

        elif direction == "SELL":

            if (
                high
                >= level_low - tolerance
                and low
                <= level_high + tolerance
            ):
                return True

    return False


# ============================================================================
# REJECTION
# ============================================================================

def _rejection_confirmed(
    candles: Sequence[Any],
    direction: str,
) -> bool:

    direction = _normalize_direction(
        direction
    )

    if not candles:
        return False

    candle = list(
        candles
    )[-1]

    open_price = _open(candle)
    close_price = _close(candle)
    high = _high(candle)
    low = _low(candle)

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

        return (
            close_price >= open_price
            and lower_wick >= body
        )

    if direction == "SELL":

        return (
            close_price <= open_price
            and upper_wick >= body
        )

    return False


# ============================================================================
# CANDLE CONFIRMATION
# ============================================================================

def _candle_confirmation(
    candles: Sequence[Any],
    direction: str,
) -> bool:

    direction = _normalize_direction(
        direction
    )

    if not candles:
        return False

    candle = list(
        candles
    )[-1]

    open_price = _open(candle)
    close_price = _close(candle)
    high = _high(candle)
    low = _low(candle)

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


# ============================================================================
# MOMENTUM / VITESSE
# ============================================================================

def _momentum_analysis(
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
            "speed": 0.0,
            "body_ratio": 0.0,
            "expansion": False,
        }

    recent = list(
        candles
    )[-10:]

    if len(recent) < 5:

        return {
            "valid": False,
            "direction": "NEUTRAL",
            "speed": 0.0,
            "body_ratio": 0.0,
            "expansion": False,
        }

    last = recent[-1]

    last_open = _open(last)
    last_close = _close(last)
    last_high = _high(last)
    last_low = _low(last)

    current_range = (
        last_high - last_low
    )

    current_body = abs(
        last_close - last_open
    )

    body_ratio = 0.0

    if current_range > 0:

        body_ratio = (
            current_body
            / current_range
        )

    previous_ranges = []

    for candle in recent[:-1]:

        candle_range = (
            _high(candle)
            - _low(candle)
        )

        if candle_range > 0:
            previous_ranges.append(
                candle_range
            )

    average_range = 0.0

    if previous_ranges:

        average_range = (
            sum(previous_ranges)
            / len(previous_ranges)
        )

    expansion = (
        average_range > 0
        and current_range
        >= average_range * 1.10
    )

    speed = 0.0

    if len(recent) >= 4:

        old_close = _close(
            recent[-4]
        )

        if old_close > 0:

            speed = abs(
                last_close - old_close
            ) / old_close

    candle_direction = "NEUTRAL"

    if last_close > last_open:
        candle_direction = "BUY"

    elif last_close < last_open:
        candle_direction = "SELL"

    directional = (
        candle_direction == direction
    )

    valid = (
        directional
        and body_ratio >= 0.40
    )

    return {
        "valid": bool(valid),
        "direction": candle_direction,
        "speed": round(
            speed,
            8,
        ),
        "body_ratio": round(
            body_ratio,
            4,
        ),
        "expansion": bool(
            expansion
        ),
    }


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
        "micro_bos": bool(micro_bos),
        "liquidity_sweep": bool(
            liquidity_sweep
        ),
        "retest": bool(retest),
        "rejection": bool(rejection),
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
# SCORE
# ============================================================================

def _fallback_score(
    direction: str,
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
    m5: Dict[str, Any],
    rr: float,
    momentum: Dict[str, Any],
) -> float:

    direction = _normalize_direction(
        direction
    )

    score = 0.0

    if _normalize_direction(
        h4_direction
    ) == direction:
        score += 20

    if _normalize_direction(
        h1_direction
    ) == direction:
        score += 20

    if _normalize_direction(
        m15_direction
    ) == direction:
        score += 20

    # Setup zone
    score += 10

    # Momentum / vitesse
    if momentum.get("valid"):
        score += 5

    if momentum.get("expansion"):
        score += 5

    # M5 secondaire
    if m5.get("retest"):
        score += 5

    if m5.get("candle_confirmation"):
        score += 5

    if m5.get("liquidity_sweep"):
        score += 5

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
        result.update(extra)

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
                _safe_float(score),
                2,
            ),
            "rr": round(
                _safe_float(rr),
                4,
            ),
        }
    )

    if extra:
        result.update(extra)

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

    # ----------------------------------------------------------------------
    # 1. PROVIDER
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # 2. MARCHÉ
    # ----------------------------------------------------------------------

    if not _market_open(
        symbol
    ):

        return _wait_result(
            symbol,
            "Marché actuellement fermé.",
        )

    # ----------------------------------------------------------------------
    # 3. DONNÉES
    # ----------------------------------------------------------------------

    candles: Dict[
        str,
        List[Any],
    ] = {}

    for timeframe in TIMEFRAMES:

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

    # ----------------------------------------------------------------------
    # 4. DIRECTIONS
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # 5. ALIGNEMENT
    # ----------------------------------------------------------------------

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
        "%s direction principale : %s",
        symbol,
        direction,
    )

    # ----------------------------------------------------------------------
    # 6. RECHERCHE MULTI-ZONES
    # ----------------------------------------------------------------------

    zone_candidates = _build_zone_candidates(
        candles["M15"],
        direction,
        max_zones=8,
    )

    logger.info(
        "%s : %s zones candidates détectées.",
        symbol,
        len(zone_candidates),
    )

    if not zone_candidates:

        return _wait_result(
            symbol,
            (
                "Contexte H4/H1/M15 valide, "
                "mais aucune zone clé exploitable "
                "n'est actuellement disponible."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

    # ----------------------------------------------------------------------
    # 7. RECHERCHE BREAKOUT
    # ----------------------------------------------------------------------

    selected_zone = None

    for zone_low, zone_high in zone_candidates:

        breakout = _breakout_confirmed(
            candles["M15"],
            direction,
            zone_low,
            zone_high,
        )

        logger.info(
            (
                "%s zone %.5f-%.5f | "
                "breakout=%s"
            ),
            symbol,
            zone_low,
            zone_high,
            breakout,
        )

        if breakout:

            selected_zone = (
                zone_low,
                zone_high,
            )

            break

    # ----------------------------------------------------------------------
    # IMPORTANT :
    # aucun breakout = WAIT
    # et NON REJECT.
    # ----------------------------------------------------------------------

    if selected_zone is None:

        logger.info(
            (
                "%s : aucun breakout confirmé. "
                "Contexte directionnel conservé."
            ),
            symbol,
        )

        return _wait_result(
            symbol,
            (
                "H4 + H1 + M15 alignés, "
                "mais aucun breakout de zone clé "
                "n'est encore confirmé."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "zones_tested": len(
                    zone_candidates
                ),
                "breakout_confirmed": False,
            },
        )

    zone_low, zone_high = selected_zone

    logger.info(
        (
            "%s breakout confirmé | "
            "zone=%.5f-%.5f"
        ),
        symbol,
        zone_low,
        zone_high,
    )

    # ----------------------------------------------------------------------
    # 8. RETEST
    # ----------------------------------------------------------------------

    retest = _retest_confirmed(
        candles["M15"],
        direction,
        zone_low,
        zone_high,
    )

    if not retest:

        return _wait_result(
            symbol,
            (
                "Breakout confirmé, "
                "mais retest de la zone "
                "encore absent."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "breakout_confirmed": True,
                "retest_confirmed": False,
                "zone": {
                    "low": zone_low,
                    "high": zone_high,
                },
            },
        )

    logger.info(
        "%s retest confirmé.",
        symbol,
    )

    # ----------------------------------------------------------------------
    # 9. REJECTION
    # ----------------------------------------------------------------------

    rejection = _rejection_confirmed(
        candles["M15"],
        direction,
    )

    if not rejection:

        return _wait_result(
            symbol,
            (
                "Retest détecté, "
                "mais rejection de zone "
                "non confirmée."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "breakout_confirmed": True,
                "retest_confirmed": True,
                "rejection_confirmed": False,
                "zone": {
                    "low": zone_low,
                    "high": zone_high,
                },
            },
        )

    logger.info(
        "%s rejection confirmée.",
        symbol,
    )

    # ----------------------------------------------------------------------
    # 10. CONFIRMATION M15
    # ----------------------------------------------------------------------

    candle_confirmation = (
        _candle_confirmation(
            candles["M15"],
            direction,
        )
    )

    if not candle_confirmation:

        return _wait_result(
            symbol,
            (
                "Rejection détectée, "
                "mais la bougie de confirmation "
                "M15 n'est pas encore valide."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "breakout_confirmed": True,
                "retest_confirmed": True,
                "rejection_confirmed": True,
                "candle_confirmation": False,
                "zone": {
                    "low": zone_low,
                    "high": zone_high,
                },
            },
        )

    logger.info(
        "%s confirmation candle M15 valide.",
        symbol,
    )

    # ----------------------------------------------------------------------
    # 11. MOMENTUM / VITESSE
    # ----------------------------------------------------------------------

    momentum = _momentum_analysis(
        candles["M15"],
        direction,
    )

    logger.info(
        (
            "%s momentum : valid=%s | "
            "speed=%s | body_ratio=%s | "
            "expansion=%s"
        ),
        symbol,
        momentum.get("valid"),
        momentum.get("speed"),
        momentum.get("body_ratio"),
        momentum.get("expansion"),
    )

    # Momentum analysé mais ne force jamais un signal.
    # S'il est insuffisant, on attend simplement.

    if not momentum.get(
        "valid",
        False,
    ):

        return _wait_result(
            symbol,
            (
                "Structure et zone confirmées, "
                "mais vitesse/momentum insuffisant "
                "pour une entrée de qualité."
            ),
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            extra={
                "breakout_confirmed": True,
                "retest_confirmed": True,
                "rejection_confirmed": True,
                "candle_confirmation": True,
                "momentum": momentum,
                "zone": {
                    "low": zone_low,
                    "high": zone_high,
                },
            },
        )

    # ----------------------------------------------------------------------
    # 12. ENTRY
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # 13. ATR
    # ----------------------------------------------------------------------

    atr = _calculate_atr(
        candles["M15"],
        period=14,
    )

    if atr <= 0:

        return _reject_result(
            symbol,
            "ATR invalide.",
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

    # ----------------------------------------------------------------------
    # 14. SL / TP
    # ----------------------------------------------------------------------

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
        )

    # ----------------------------------------------------------------------
    # 15. RR
    # ----------------------------------------------------------------------

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
        )

    # ----------------------------------------------------------------------
    # 16. M5
    # ----------------------------------------------------------------------

    m5 = _m5_confirmation(
        candles["M5"],
        direction,
    )

    logger.info(
        (
            "%s M5 : valid=%s | "
            "direction=%s | BOS=%s | "
            "sweep=%s | retest=%s | candle=%s"
        ),
        symbol,
        m5.get("valid"),
        m5.get("direction"),
        m5.get("micro_bos"),
        m5.get("liquidity_sweep"),
        m5.get("retest"),
        m5.get("candle_confirmation"),
    )

    # ----------------------------------------------------------------------
    # IMPORTANT :
    # M5 ne peut PAS rejeter.
    # ----------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # 17. ZONE FINALE
    # ----------------------------------------------------------------------

    zone = {
        "low": zone_low,
        "high": zone_high,
        "direction": direction,
        "breakout_confirmed": True,
        "retest_confirmed": True,
        "rejection_confirmed": True,
        "candle_confirmation": True,
        "entry_valid": True,
        "structure_confirmed": True,
        "momentum_valid": bool(
            momentum.get("valid")
        ),
        "liquidity": bool(
            m5.get("liquidity_sweep")
        ),
        "key_level": (
            zone_low + zone_high
        ) / 2,
    }

    # ----------------------------------------------------------------------
    # 18. SCORE
    # ----------------------------------------------------------------------

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
            "%s score=%.2f/100 | "
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
                "momentum": momentum,
                "zone": zone,
            },
        )

    # ----------------------------------------------------------------------
    # 19. NEWS
    # ----------------------------------------------------------------------

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
            },
        )

    # ----------------------------------------------------------------------
    # 20. CONSTRUCTION SIGNAL
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # 21. SIGNAL ID
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # 22. ÉCHEC CONSTRUCTION
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # 23. RÉSULTAT FINAL
    # ----------------------------------------------------------------------

    result = {
        "symbol": symbol,
        "status": "ACTIVE",
        "reason": (
            "Signal validé : "
            "H4 + H1 + M15 alignés, "
            "zone + breakout + retest + "
            "rejection + confirmation + "
            "momentum validés."
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
        "breakout_confirmed": True,
        "retest_confirmed": True,
        "rejection_confirmed": True,
        "candle_confirmation": True,
        "timestamp": _utc_now().isoformat(),
    }

    logger.info(
        (
            "SIGNAL VALIDE %s | %s | "
            "score=%.2f | RR=%.2f | "
            "entry=%s | SL=%s | TP=%s"
        ),
        symbol,
        direction,
        score,
        rr,
        entry,
        stop_loss,
        take_profit,
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