"""
NOVA TRADE AI
risk/risk_manager.py
MOTEUR DE GESTION DU RISQUE.
Responsabilités :
    Entry
      ↓
    Stop Loss
      ↓
    Take Profit
      ↓
    RR
      ↓
    Risque monétaire
      ↓
    Taille de position
      ↓
    Break Even
Principes :
- Aucun calcul ne doit inventer une valeur.
- Un trade BUY doit avoir :
      SL < Entry < TP
- Un trade SELL doit avoir :
      TP < Entry < SL
- Le RR minimum de validation est géré par le moteur
  de signal via CONFIG.MINIMUM_RR.
- Ce module fournit les calculs mathématiques du risque.
"""
from __future__ import annotations
from dataclasses import dataclass
# ============================================================
# PARAMÈTRES DE RISQUE
# ============================================================
@dataclass(frozen=True)
class RiskParameters:
    """
    Paramètres principaux d'un trade.
    """
    entry: float
    stop_loss: float
    take_profit: float
    risk_percent: float
# ============================================================
# OUTILS
# ============================================================
def _safe_float(
    value,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default
def _normalize_direction(
    direction,
) -> str:
    """
    Normalise BUY / SELL.
    """
    if direction is None:
        return ""
    value = str(
        getattr(
            direction,
            "value",
            direction,
        )
    ).upper().strip()
    if value in {
        "BUY",
        "LONG",
        "BULLISH",
    }:
        return "BUY"
    if value in {
        "SELL",
        "SHORT",
        "BEARISH",
    }:
        return "SELL"
    return ""
# ============================================================
# VALIDATION GÉOMÉTRIQUE
# ============================================================
def validate_trade_geometry(
    direction,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> bool:
    """
    Vérifie la géométrie complète du trade.
    BUY :
        SL < ENTRY < TP
    SELL :
        TP < ENTRY < SL
    """
    direction = _normalize_direction(
        direction
    )
    entry = _safe_float(entry)
    stop_loss = _safe_float(stop_loss)
    take_profit = _safe_float(take_profit)
    if (
        entry <= 0
        or stop_loss <= 0
        or take_profit <= 0
    ):
        return False
    if direction == "BUY":
        return (
            stop_loss < entry
            and take_profit > entry
        )
    if direction == "SELL":
        return (
            stop_loss > entry
            and take_profit < entry
        )
    return False
# ============================================================
# CALCUL RR
# ============================================================
def calculate_rr(
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> float:
    """
    Calcule le Risk/Reward.
    RR = Reward / Risk
    Exemple :
        Entry = 100
        SL    = 98
        TP    = 104
        Risk   = 2
        Reward = 4
        RR = 2.0
    """
    entry = _safe_float(entry)
    stop_loss = _safe_float(stop_loss)
    take_profit = _safe_float(take_profit)
    risk = abs(
        entry - stop_loss
    )
    reward = abs(
        take_profit - entry
    )
    if risk <= 0:
        return 0.0
    if reward <= 0:
        return 0.0
    return round(
        reward / risk,
        4,
    )
# ============================================================
# VALIDATION RR
# ============================================================
def is_rr_valid(
    entry: float,
    stop_loss: float,
    take_profit: float,
    minimum_rr: float = 2.0,
) -> bool:
    """
    Vérifie que le RR respecte le minimum demandé.
    """
    minimum_rr = _safe_float(
        minimum_rr
    )
    if minimum_rr <= 0:
        return False
    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )
    return rr >= minimum_rr
# ============================================================
# RISQUE MONÉTAIRE
# ============================================================
def calculate_risk_money(
    equity: float,
    risk_percent: float,
) -> float:
    """
    Calcule le montant monétaire risqué.
    Exemple :
        Equity = 1000
        Risk   = 1%
        Risque = 10
    """
    equity = _safe_float(
        equity
    )
    risk_percent = _safe_float(
        risk_percent
    )
    if equity <= 0:
        return 0.0
    if risk_percent <= 0:
        return 0.0
    return round(
        equity
        * risk_percent
        / 100.0,
        8,
    )
# ============================================================
# DISTANCE DU STOP
# ============================================================
def calculate_stop_distance(
    entry: float,
    stop_loss: float,
) -> float:
    """
    Distance absolue entre Entry et SL.
    """
    entry = _safe_float(entry)
    stop_loss = _safe_float(stop_loss)
    return abs(
        entry - stop_loss
    )
# ============================================================
# TAILLE DE POSITION
# ============================================================
def calculate_position_size(
    equity: float,
    risk_percent: float,
    entry: float,
    stop_loss: float,
    value_per_price_unit: float = 1.0,
) -> float:
    """
    Calcule la taille théorique de position.
    Formule :
        Position =
            Risk Money
            /
            (SL Distance × Value Per Price Unit)
    IMPORTANT :
    value_per_price_unit dépend de l'instrument
    et du broker/exchange.
    Cette fonction ne suppose donc pas une valeur
    universelle pour XAU/USD, BTC/USD ou Forex.
    """
    risk_money = calculate_risk_money(
        equity,
        risk_percent,
    )
    if risk_money <= 0:
        return 0.0
    distance = calculate_stop_distance(
        entry,
        stop_loss,
    )
    if distance <= 0:
        return 0.0
    value_per_price_unit = _safe_float(
        value_per_price_unit
    )
    if value_per_price_unit <= 0:
        return 0.0
    position_size = (
        risk_money
        / (
            distance
            * value_per_price_unit
        )
    )
    return max(
        0.0,
        position_size,
    )
# ============================================================
# BREAK EVEN
# ============================================================
def calculate_be_price(
    entry: float,
    direction,
    buffer: float = 0.0,
) -> float:
    """
    Calcule le prix de Break Even.
    BUY :
        BE = Entry + Buffer
    SELL :
        BE = Entry - Buffer
    """
    entry = _safe_float(
        entry
    )
    buffer = abs(
        _safe_float(buffer)
    )
    normalized = _normalize_direction(
        direction
    )
    if normalized == "BUY":
        return round(
            entry + buffer,
            8,
        )
    if normalized == "SELL":
        return round(
            entry - buffer,
            8,
        )
    return round(
        entry,
        8,
    )
# ============================================================
# RISK PARAMETERS VALIDATION
# ============================================================
def validate_risk_parameters(
    parameters: RiskParameters,
    direction=None,
    minimum_rr: float = 2.0,
) -> bool:
    """
    Validation complète des paramètres de risque.
    """
    if parameters is None:
        return False
    entry = _safe_float(
        parameters.entry
    )
    stop_loss = _safe_float(
        parameters.stop_loss
    )
    take_profit = _safe_float(
        parameters.take_profit
    )
    risk_percent = _safe_float(
        parameters.risk_percent
    )
    if risk_percent <= 0:
        return False
    # --------------------------------------------------------
    # Si une direction est fournie,
    # on valide la géométrie directionnelle.
    # --------------------------------------------------------
    if direction is not None:
        if not validate_trade_geometry(
            direction,
            entry,
            stop_loss,
            take_profit,
        ):
            return False
    # --------------------------------------------------------
    # RR
    # --------------------------------------------------------
    return is_rr_valid(
        entry,
        stop_loss,
        take_profit,
        minimum_rr,
    )
# ============================================================
# RAPPORT DE RISQUE
# ============================================================
def build_risk_report(
    equity: float,
    risk_percent: float,
    entry: float,
    stop_loss: float,
    take_profit: float,
    value_per_price_unit: float = 1.0,
    minimum_rr: float = 2.0,
    direction=None,
) -> dict:
    """
    Produit un rapport complet du trade.
    Utile pour le pipeline, le tracker ou Telegram.
    Aucun ordre n'est exécuté ici.
    """
    entry = _safe_float(entry)
    stop_loss = _safe_float(stop_loss)
    take_profit = _safe_float(take_profit)
    risk_percent = _safe_float(
        risk_percent
    )
    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )
    risk_money = calculate_risk_money(
        equity,
        risk_percent,
    )
    stop_distance = calculate_stop_distance(
        entry,
        stop_loss,
    )
    position_size = calculate_position_size(
        equity=equity,
        risk_percent=risk_percent,
        entry=entry,
        stop_loss=stop_loss,
        value_per_price_unit=value_per_price_unit,
    )
    geometry_valid = True
    if direction is not None:
        geometry_valid = validate_trade_geometry(
            direction,
            entry,
            stop_loss,
            take_profit,
        )
    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr": rr,
        "minimum_rr": minimum_rr,
        "rr_valid": rr >= minimum_rr,
        "risk_percent": risk_percent,
        "risk_money": risk_money,
        "stop_distance": stop_distance,
        "position_size": position_size,
        "geometry_valid": geometry_valid,
        "valid": (
            geometry_valid
            and rr >= minimum_rr
            and risk_percent > 0
        ),
    }