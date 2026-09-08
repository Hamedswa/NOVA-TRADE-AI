"""
NOVA TRADE AI
analysis/pipeline.py

PIPELINE PRINCIPAL D'ANALYSE

Architecture :
    Données
        ↓
    H4 + H1 + M15
        ↓
    Alignement directionnel principal
        ↓
    Zone clé
        ↓
    Breakout
        ↓
    Retest
        ↓
    Rejection
        ↓
    Confirmation candle
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

RÈGLES PRINCIPALES :
    - H4 + H1 + M15 doivent être parfaitement alignés.
    - D1 n'est PAS utilisé.
    - M5 est secondaire et NON BLOQUANT.
    - Score minimum : 60.
    - RR minimum : 2.0.
    - Aucun signal ne doit être forcé.
    - Si Twelve Data est en cooldown, l'analyse Forex/XAU
      est simplement reportée.
    - Les cryptos utilisent leur fournisseur crypto
      indépendamment de Twelve Data.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IMPORTS PROJET
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------------------------

TIMEFRAMES: Tuple[str, ...] = (
    "H4",
    "H1",
    "M15",
    "M5",
)

# IMPORTANT :
# D1 est volontairement absent.
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


# ---------------------------------------------------------------------------
# HELPERS GÉNÉRAUX
# ---------------------------------------------------------------------------

def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Conversion sécurisée en float.
    """

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
    """
    Normalise BUY / SELL / NEUTRAL.
    """

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
    """
    Retourne True si le symbole est une crypto.

    Les cryptos utilisent leur fournisseur crypto
    et ne doivent jamais être bloquées par
    le cooldown Twelve Data.
    """

    normalized = str(
        symbol or ""
    ).strip().upper()

    return normalized in CRYPTO_SYMBOLS


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


# ---------------------------------------------------------------------------
# CONTRÔLE TWELVE DATA
# ---------------------------------------------------------------------------

def _get_twelve_data_status() -> Dict[str, Any]:
    """
    Récupère l'état de Twelve Data de façon tolérante.

    Formats supportés :

        {
            "twelve_data": {
                "available": False,
                "cooldown": 60
            }
        }

    ou :

        {
            "available": False,
            "cooldown": 60
        }

    ou API séparée :

        twelve_data_available()
        get_twelve_data_cooldown()
    """

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

        # ---------------------------------------------------------------
        # API ALTERNATIVE
        # ---------------------------------------------------------------

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
            "Impossible de lire le statut Twelve Data : %s",
            exc,
        )

    # Si le statut ne peut pas être lu,
    # on ne bloque pas artificiellement.
    return {
        "available": True,
        "cooldown": 0,
    }


def _twelve_data_ready(
    symbol: str,
) -> Tuple[bool, str]:
    """
    Vérifie si Twelve Data est utilisable.

    Crypto :
        toujours True ici.

    Forex / XAU :
        respecte le cooldown Twelve Data.
    """

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

            reason = (
                "Twelve Data temporairement limité "
                f"— cooldown {cooldown}s"
            )

        else:

            reason = (
                "Twelve Data temporairement indisponible"
            )

        return False, reason

    return True, ""


# ---------------------------------------------------------------------------
# EXTRACTION DES CHANDELIERS
# ---------------------------------------------------------------------------

def _extract_candles(
    symbol: str,
    timeframe: str,
) -> List[Any]:
    """
    Récupère les chandeliers via market_data.

    IMPORTANT :

    Si Twelve Data vient de déclencher un HTTP 429,
    cette fonction vérifie immédiatement le cooldown.

    Elle ne doit donc PAS produire :

        ERROR | DATA EUR/USD H4 : 0 chandelier

    lorsqu'il s'agit simplement d'un rate-limit.

    Les erreurs réelles restent journalisées.
    """

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

        # ---------------------------------------------------------------
        # FORMAT PRINCIPAL
        # ---------------------------------------------------------------

        try:

            candles = getter(
                symbol,
                timeframe,
            )

        except TypeError:
            pass

        # ---------------------------------------------------------------
        # FORMAT KEYWORD
        # ---------------------------------------------------------------

        if candles is None:

            try:

                candles = getter(
                    symbol=symbol,
                    timeframe=timeframe,
                )

            except TypeError:
                pass

        # ---------------------------------------------------------------
        # FORMAT INTERVAL
        # ---------------------------------------------------------------

        if candles is None:

            try:

                candles = getter(
                    symbol=symbol,
                    interval=timeframe,
                )

            except TypeError:
                pass

        # ---------------------------------------------------------------
        # AUCUNE DONNÉE
        # ---------------------------------------------------------------

        if candles is None:

            # IMPORTANT :
            # Recheck après l'appel.
            #
            # Un HTTP 429 peut avoir déclenché
            # le cooldown pendant get_candles().

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

        # ---------------------------------------------------------------
        # FORMAT DICT
        # ---------------------------------------------------------------

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

            # Si aucun format connu n'a été trouvé,
            # ne pas considérer arbitrairement le dict
            # comme une liste de chandeliers.
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

        # ---------------------------------------------------------------
        # FORMAT INVALIDE
        # ---------------------------------------------------------------

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

        # ---------------------------------------------------------------
        # LISTE VIDE
        # ---------------------------------------------------------------

        if not result:

            # Recheck du provider AVANT de journaliser.
            #
            # Si le provider vient de passer en cooldown,
            # ce n'est pas une erreur de données.

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

        # ---------------------------------------------------------------
        # DONNÉES OK
        # ---------------------------------------------------------------

        return result

    except Exception as exc:

        # ---------------------------------------------------------------
        # CAS IMPORTANT : HTTP 429 / COOLDOWN
        # ---------------------------------------------------------------

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

        # ---------------------------------------------------------------
        # VRAIE ERREUR
        # ---------------------------------------------------------------

        logger.error(
            "DATA %s %s erreur : %s",
            symbol,
            timeframe,
            exc,
        )

        return []


def _validate_candles(
    candles: Sequence[Any],
    minimum: int = 20,
) -> bool:
    """
    Vérifie qu'un historique est exploitable.
    """

    if candles is None:
        return False

    try:
        count = len(
            candles
        )

    except Exception:
        return False

    return count >= minimum


# ---------------------------------------------------------------------------
# ACCÈS OHLC
# ---------------------------------------------------------------------------

def _candle_value(
    candle: Any,
    key: str,
    default: float = 0.0,
) -> float:
    """
    Extrait une valeur OHLC depuis un dict ou un objet.
    """

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


def _close(
    candle: Any,
) -> float:
    return _candle_value(
        candle,
        "close",
    )


def _open(
    candle: Any,
) -> float:
    return _candle_value(
        candle,
        "open",
    )


def _high(
    candle: Any,
) -> float:
    return _candle_value(
        candle,
        "high",
    )


def _low(
    candle: Any,
) -> float:
    return _candle_value(
        candle,
        "low",
    )


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def _calculate_atr(
    candles: Sequence[Any],
    period: int = 14,
) -> float:
    """
    ATR robuste.
    """

    if not candles:
        return 0.0

    if len(candles) < 2:
        return 0.0

    true_ranges: List[float] = []

    previous_close = None

    for candle in candles:

        high = _high(
            candle
        )

        low = _low(
            candle
        )

        close = _close(
            candle
        )

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

    values = true_ranges[
        -period:
    ]

    return (
        sum(values)
        / len(values)
    )


# ---------------------------------------------------------------------------
# SWINGS
# ---------------------------------------------------------------------------

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

        is_high = True

        for j in range(
            i - lookback,
            i + lookback + 1,
        ):

            if j == i:
                continue

            if _high(
                candles[j]
            ) >= current:

                is_high = False
                break

        if is_high:
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

        is_low = True

        for j in range(
            i - lookback,
            i + lookback + 1,
        ):

            if j == i:
                continue

            if _low(
                candles[j]
            ) <= current:

                is_low = False
                break

        if is_low:
            lows.append(
                current
            )

    return lows


# ---------------------------------------------------------------------------
# STRUCTURE / DIRECTION
# ---------------------------------------------------------------------------

def _structure_direction(
    candles: Sequence[Any],
) -> str:
    """
    Détermine une direction structurelle.

    BUY :
        HH + HL

    SELL :
        LH + LL

    Sinon :
        NEUTRAL
    """

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

    if len(highs) < 2:
        return "NEUTRAL"

    if len(lows) < 2:
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


# ---------------------------------------------------------------------------
# ALIGNEMENT PRINCIPAL
# ---------------------------------------------------------------------------

def _primary_alignment(
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
) -> str:
    """
    RÈGLE PRINCIPALE NOVA TRADE AI :

        H4 + H1 + M15
        doivent être parfaitement alignés.

    D1 n'est pas utilisé.

    M5 n'intervient jamais dans cette validation.
    """

    h4 = _normalize_direction(
        h4_direction
    )

    h1 = _normalize_direction(
        h1_direction
    )

    m15 = _normalize_direction(
        m15_direction
    )

    if h4 == "NEUTRAL":
        return "NEUTRAL"

    if h1 == "NEUTRAL":
        return "NEUTRAL"

    if m15 == "NEUTRAL":
        return "NEUTRAL"

    if h4 == h1 == m15:
        return h4

    return "NEUTRAL"


# ---------------------------------------------------------------------------
# NIVEAU CLÉ
# ---------------------------------------------------------------------------

def _find_key_level(
    candles: Sequence[Any],
    direction: str,
) -> Tuple[float, float]:
    """
    Détermine une zone clé à partir des swings récents.

    Retour :
        (low, high)
    """

    direction = _normalize_direction(
        direction
    )

    if not candles:
        return 0.0, 0.0

    recent = list(
        candles
    )[-50:]

    highs = [
        _high(c)
        for c in recent
        if _high(c) > 0
    ]

    lows = [
        _low(c)
        for c in recent
        if _low(c) > 0
    ]

    if not highs or not lows:
        return 0.0, 0.0

    if direction == "BUY":

        swing_highs = _swing_highs(
            recent,
            lookback=2,
        )

        candidates = (
            swing_highs
            or highs[-5:]
        )

        level = max(
            candidates
        )

        return (
            level * 0.9995,
            level * 1.0005,
        )

    if direction == "SELL":

        swing_lows = _swing_lows(
            recent,
            lookback=2,
        )

        candidates = (
            swing_lows
            or lows[-5:]
        )

        level = min(
            candidates
        )

        return (
            level * 0.9995,
            level * 1.0005,
        )

    return 0.0, 0.0


# ---------------------------------------------------------------------------
# BREAKOUT
# ---------------------------------------------------------------------------

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

    if level_low <= 0 or level_high <= 0:
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


# ---------------------------------------------------------------------------
# RETEST
# ---------------------------------------------------------------------------

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

    if level_low <= 0 or level_high <= 0:
        return False

    recent = list(
        candles
    )[-8:]

    tolerance = max(
        abs(
            level_high - level_low
        ) * 1.5,
        1e-8,
    )

    for candle in recent:

        high = _high(
            candle
        )

        low = _low(
            candle
        )

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


# ---------------------------------------------------------------------------
# REJECTION
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CONFIRMATION CANDLE
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# M5 CONFIRMATION
# ---------------------------------------------------------------------------

def _m5_confirmation(
    candles: Sequence[Any],
    direction: str,
) -> Dict[str, Any]:
    """
    M5 est NON BLOQUANT.

    Il peut améliorer le score,
    mais ne peut jamais annuler un setup
    H4 + H1 + M15 parfaitement aligné.
    """

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
        "valid": bool(
            valid
        ),
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


# ---------------------------------------------------------------------------
# SL / TP
# ---------------------------------------------------------------------------

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

            sl = (
                entry - atr
            )

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

            sl = (
                entry + atr
            )

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


# ---------------------------------------------------------------------------
# GEOMETRIE
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SCORE FALLBACK
# ---------------------------------------------------------------------------

def _fallback_score(
    direction: str,
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
    m5: Dict[str, Any],
    rr: float,
) -> float:
    """
    Score déterministe de secours.

    Poids :
        H4               20
        H1               20
        M15              20
        Zone qualité     10
        M5 retest        10
        M5 candle         5
        Liquidity         5
        RR                5
        Market            5
        --------------------
        TOTAL            100
    """

    direction = _normalize_direction(
        direction
    )

    score = 0.0

    if (
        _normalize_direction(
            h4_direction
        )
        == direction
    ):
        score += 20

    if (
        _normalize_direction(
            h1_direction
        )
        == direction
    ):
        score += 20

    if (
        _normalize_direction(
            m15_direction
        )
        == direction
    ):
        score += 20

    # Zone structurelle validée
    score += 10

    # M5 secondaire
    if m5.get(
        "retest"
    ):
        score += 10

    if m5.get(
        "candle_confirmation"
    ):
        score += 5

    if m5.get(
        "liquidity_sweep"
    ):
        score += 5

    if rr >= 2.0:
        score += 5

    elif rr >= 1.5:
        score += 3

    # Conditions de marché
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
) -> float:
    """
    Utilise le scoring engine s'il est disponible.

    Sinon fallback déterministe.
    """

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

            # Signature incompatible :
            # fallback déterministe.
            pass

        except Exception as exc:

            logger.debug(
                (
                    "Scoring engine indisponible "
                    "pour %s : %s"
                ),
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
    )


# ---------------------------------------------------------------------------
# NEWS
# ---------------------------------------------------------------------------

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

        return bool(
            result
        ), None

    except Exception as exc:

        logger.warning(
            (
                "NEWS %s : "
                "filtre indisponible : %s"
            ),
            symbol,
            exc,
        )

        return False, None


# ---------------------------------------------------------------------------
# MARCHÉ
# ---------------------------------------------------------------------------

def _market_open(
    symbol: str,
) -> bool:
    """
    Vérification légère du marché.

    Si market_data possède une fonction dédiée,
    elle est utilisée.

    Sinon aucune fermeture artificielle
    n'est appliquée.
    """

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

        if callable(
            checker
        ):

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


# ---------------------------------------------------------------------------
# RESULTAT WAIT
# ---------------------------------------------------------------------------

def _wait_result(
    symbol: str,
    reason: str,
) -> Dict[str, Any]:

    return {
        "symbol": symbol,
        "status": "WAIT",
        "reason": reason,
        "direction": "NEUTRAL",
        "score": 0.0,
        "rr": 0.0,
        "entry": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "signal": None,
        "signal_id": None,
        "timestamp": _utc_now().isoformat(),
    }


# ---------------------------------------------------------------------------
# RESULTAT REJECT
# ---------------------------------------------------------------------------

def _reject_result(
    symbol: str,
    reason: str,
    direction: str = "NEUTRAL",
    score: float = 0.0,
    rr: float = 0.0,
) -> Dict[str, Any]:

    return {
        "symbol": symbol,
        "status": "REJECT",
        "reason": reason,
        "direction": _normalize_direction(
            direction
        ),
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
            2,
        ),
        "entry": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "signal": None,
        "signal_id": None,
        "timestamp": _utc_now().isoformat(),
    }


# ---------------------------------------------------------------------------
# ANALYSE PRINCIPALE
# ---------------------------------------------------------------------------

def analyze_market(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:
    """
    Analyse complète d'un marché.

    Forex / XAU :
        Twelve Data disponible -> analyse
        Twelve Data cooldown -> WAIT

    Crypto :
        fournisseur crypto -> analyse
        Twelve Data ignoré
    """

    symbol = str(
        symbol or "XAU/USD"
    ).strip().upper()

    logger.info(
        "========== ANALYSE %s ==========",
        symbol,
    )

    # ------------------------------------------------------------------
    # 1. PROVIDER
    # ------------------------------------------------------------------

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

            logger.info(
                "Analyse reportée : %s",
                symbol,
            )

            return _wait_result(
                symbol,
                provider_reason,
            )

    # ------------------------------------------------------------------
    # 2. MARCHÉ
    # ------------------------------------------------------------------

    if not _market_open(
        symbol
    ):

        return _wait_result(
            symbol,
            "Marché actuellement fermé.",
        )

    # ------------------------------------------------------------------
    # 3. RÉCUPÉRATION DES DONNÉES
    # ------------------------------------------------------------------

    candles: Dict[
        str,
        List[Any],
    ] = {}

    for timeframe in TIMEFRAMES:

        # --------------------------------------------------------------
        # Vérification provider avant chaque appel
        # --------------------------------------------------------------

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

                logger.info(
                    "Analyse reportée : %s",
                    symbol,
                )

                return _wait_result(
                    symbol,
                    reason,
                )

        # --------------------------------------------------------------
        # Récupération
        # --------------------------------------------------------------

        data = _extract_candles(
            symbol,
            timeframe,
        )

        # --------------------------------------------------------------
        # IMPORTANT :
        # si get_candles() vient de déclencher
        # un cooldown, on retourne la vraie raison
        # au lieu de "Données insuffisantes H4".
        # --------------------------------------------------------------

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

                    logger.warning(
                        "%s",
                        reason,
                    )

                    logger.info(
                        "Analyse reportée : %s",
                        symbol,
                    )

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

        # --------------------------------------------------------------
        # Validation historique
        # --------------------------------------------------------------

        if not _validate_candles(
            data,
            minimum=20,
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

    # ------------------------------------------------------------------
    # 4. DIRECTIONS H4 / H1 / M15
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 5. ALIGNEMENT PRINCIPAL
    # ------------------------------------------------------------------

    direction = _primary_alignment(
        h4_direction,
        h1_direction,
        m15_direction,
    )

    if direction == "NEUTRAL":

        logger.info(
            (
                "%s : "
                "H4/H1/M15 non alignés."
            ),
            symbol,
        )

        return _reject_result(
            symbol,
            (
                "H4 + H1 + M15 "
                "ne sont pas parfaitement alignés."
            ),
            direction="NEUTRAL",
        )

    logger.info(
        "%s direction principale : %s",
        symbol,
        direction,
    )

    # ------------------------------------------------------------------
    # 6. ZONE CLÉ
    # ------------------------------------------------------------------

    zone_low, zone_high = (
        _find_key_level(
            candles["M15"],
            direction,
        )
    )

    if (
        zone_low <= 0
        or zone_high <= 0
    ):

        return _reject_result(
            symbol,
            "Aucune zone clé exploitable.",
            direction=direction,
        )

    # ------------------------------------------------------------------
    # 7. BREAKOUT
    # ------------------------------------------------------------------

    breakout = _breakout_confirmed(
        candles["M15"],
        direction,
        zone_low,
        zone_high,
    )

    if not breakout:

        return _reject_result(
            symbol,
            "Breakout de la zone clé non confirmé.",
            direction=direction,
        )

    # ------------------------------------------------------------------
    # 8. RETEST
    # ------------------------------------------------------------------

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
                "Breakout confirmé "
                "mais retest non confirmé."
            ),
        )

    # ------------------------------------------------------------------
    # 9. REJECTION
    # ------------------------------------------------------------------

    rejection = _rejection_confirmed(
        candles["M15"],
        direction,
    )

    if not rejection:

        return _wait_result(
            symbol,
            (
                "Retest détecté "
                "mais rejection non confirmée."
            ),
        )

    # ------------------------------------------------------------------
    # 10. CONFIRMATION CANDLE M15
    # ------------------------------------------------------------------

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
                "Candle de confirmation "
                "M15 absente."
            ),
        )

    # ------------------------------------------------------------------
    # 11. ENTRY
    # ------------------------------------------------------------------

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
        )

    # ------------------------------------------------------------------
    # 12. ATR
    # ------------------------------------------------------------------

    atr = _calculate_atr(
        candles["M15"],
        period=14,
    )

    if atr <= 0:

        return _reject_result(
            symbol,
            "ATR invalide.",
            direction=direction,
        )

    # ------------------------------------------------------------------
    # 13. SL / TP
    # ------------------------------------------------------------------

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
        )

    # ------------------------------------------------------------------
    # 14. RR
    # ------------------------------------------------------------------

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
            rr=rr,
        )

    # ------------------------------------------------------------------
    # 15. M5 SECONDARY
    # ------------------------------------------------------------------

    m5 = _m5_confirmation(
        candles["M5"],
        direction,
    )

    logger.info(
        (
            "%s M5 : valid=%s | "
            "BOS=%s | sweep=%s | "
            "retest=%s | candle=%s"
        ),
        symbol,
        m5.get("valid"),
        m5.get("micro_bos"),
        m5.get("liquidity_sweep"),
        m5.get("retest"),
        m5.get("candle_confirmation"),
    )

    # IMPORTANT :
    # aucune condition ici ne rejette le setup
    # uniquement parce que M5 n'est pas confirmé.

    # ------------------------------------------------------------------
    # 16. SCORE
    # ------------------------------------------------------------------

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
    }

    score = _calculate_final_score(
        symbol=symbol,
        direction=direction,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
        m5=m5,
        rr=rr,
        zone=zone,
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
            score=score,
            rr=rr,
        )

    # ------------------------------------------------------------------
    # 17. NEWS
    # ------------------------------------------------------------------

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
        )

    # ------------------------------------------------------------------
    # 18. CONSTRUCTION SIGNAL
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 19. RESULTAT FINAL
    # ------------------------------------------------------------------

    signal_id = None

    if signal is not None:

        signal_id = getattr(
            signal,
            "signal_id",
            None,
        )

        if isinstance(
            signal,
            dict,
        ):

            signal_id = signal.get(
                "signal_id"
            )

    # ------------------------------------------------------------------
    # IMPORTANT :
    # Le pipeline ne doit pas prétendre qu'un objet Signal
    # a été construit si build_signal a échoué.
    #
    # Les conditions analytiques restent valides, mais
    # si le moteur de signal est disponible et échoue,
    # on ne force jamais ACTIVE.
    # ------------------------------------------------------------------

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
            score=score,
            rr=rr,
        )

    result = {
        "symbol": symbol,
        "status": "ACTIVE",
        "reason": (
            "Signal validé : "
            "H4 + H1 + M15 alignés, "
            "zone + breakout + retest + "
            "rejection + confirmation validés."
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
        "m5_confirmation": m5,
        "zone": zone,
        "atr": atr,
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


# ---------------------------------------------------------------------------
# ALIASES DE COMPATIBILITÉ
# ---------------------------------------------------------------------------

def analyser_marche(
    symbol: str = "XAU/USD",
    timeframe: str = "M15",
) -> Dict[str, Any]:
    """
    Alias français conservé pour compatibilité.

    Le paramètre timeframe est conservé pour éviter
    de casser les appels existants, mais l'analyse
    reste obligatoirement multi-timeframe.
    """

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


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

__all__ = [
    "analyze_market",
    "analyser_marche",
    "analyser_marche_complet",
    "run_analysis",
]