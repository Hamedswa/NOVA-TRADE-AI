"""
NOVA TRADE AI
signals/signal_engine.py
MOTEUR DE VALIDATION DES SIGNAUX.
Architecture :
    H4
     ↓
    CONTEXTE / BIAIS
    H1
     ↓
    STRUCTURE
    M15
     ↓
    CONTEXTE / ZONES / LIQUIDITÉ
    M5
     ↓
    TIMING / CONFIRMATION SECONDAIRE
IMPORTANT :
H4 ne bloque PAS automatiquement un signal.
Le moteur accepte :
    CONTINUATION
    CORRECTION
    POTENTIAL_REVERSAL
    COUNTER_TREND
    SHORT_TERM_BULLISH
    SHORT_TERM_BEARISH
La direction finale doit avoir été déterminée
par le moteur d'analyse avant construction du signal.
M5 est une confirmation secondaire.
M5 ne bloque jamais à lui seul un setup valide.
Validation critique :
    Direction
        ↓
    Zone clé
        ↓
    Structure / scénario
        ↓
    Cassure
        ↓
    Retest
        ↓
    Réaction
        ↓
    Confirmation
        ↓
    Entry
        ↓
    SL / TP
        ↓
    RR
        ↓
    Score
        ↓
    SIGNAL
"""
from __future__ import annotations
from uuid import uuid4
from config import CONFIG
from core.models import (
    Confirmation,
    Direction,
    MarketType,
    Signal,
    TrendContext,
    Zone,
)
from risk.risk_manager import calculate_rr
from scoring.scoring_engine import (
    calculate_score,
    should_send_signal,
)
# ============================================================
# TYPE DE MARCHÉ
# ============================================================
def detect_market_type(
    symbol: str,
) -> MarketType:
    """
    Détermine le type de marché.
    """
    crypto_symbols = {
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
        "BNB/USD",
        "XRP/USD",
    }
    if str(symbol).upper() in crypto_symbols:
        return MarketType.CRYPTO
    return MarketType.FOREX
# ============================================================
# NORMALISATION DIRECTION
# ============================================================
def _normalize_direction(
    direction,
) -> Direction:
    """
    Convertit différentes représentations
    vers Direction.
    """
    if isinstance(direction, Direction):
        return direction
    if direction is None:
        return Direction.NEUTRAL
    value = str(direction).upper().strip()
    if value in {"BUY", "LONG", "BULLISH"}:
        return Direction.BUY
    if value in {"SELL", "SHORT", "BEARISH"}:
        return Direction.SELL
    return Direction.NEUTRAL
# ============================================================
# BIAIS H4
# ============================================================
def get_h4_bias(
    h4_direction: Direction,
) -> Direction:
    """
    H4 représente le biais de contexte.
    IMPORTANT :
    H4 n'est PAS un blocage absolu.
    """
    return _normalize_direction(h4_direction)
# ============================================================
# DIRECTION FINALE
# ============================================================
def resolve_trade_direction(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
    requested_direction: Direction | None = None,
) -> Direction:
    """
    Détermine la direction finale du setup.
    Règles :
    1. Si le pipeline fournit une direction explicite,
       elle est prioritaire.
    2. Sinon :
       - H1 + M15 alignés -> direction H1/M15
       - H4 + H1 alignés -> direction H4/H1
       - H4 seul -> biais H4
       - H1 seul -> H1
       - M15 seul -> M15
       - sinon NEUTRAL
    Cette fonction ne force jamais un trade.
    """
    requested = _normalize_direction(
        requested_direction
    )
    h4 = _normalize_direction(h4_direction)
    h1 = _normalize_direction(h1_direction)
    m15 = _normalize_direction(m15_direction)
    # --------------------------------------------------------
    # Direction explicitement validée par le pipeline
    # --------------------------------------------------------
    if requested != Direction.NEUTRAL:
        return requested
    # --------------------------------------------------------
    # H1 + M15 alignés
    # --------------------------------------------------------
    if (
        h1 != Direction.NEUTRAL
        and h1 == m15
    ):
        return h1
    # --------------------------------------------------------
    # H4 + H1 alignés
    # --------------------------------------------------------
    if (
        h4 != Direction.NEUTRAL
        and h4 == h1
    ):
        return h4
    # --------------------------------------------------------
    # H4 + M15 alignés
    # --------------------------------------------------------
    if (
        h4 != Direction.NEUTRAL
        and h4 == m15
    ):
        return h4
    # --------------------------------------------------------
    # H4 disponible
    # --------------------------------------------------------
    if h4 != Direction.NEUTRAL:
        return h4
    # --------------------------------------------------------
    # H1 disponible
    # --------------------------------------------------------
    if h1 != Direction.NEUTRAL:
        return h1
    # --------------------------------------------------------
    # M15 disponible
    # --------------------------------------------------------
    if m15 != Direction.NEUTRAL:
        return m15
    return Direction.NEUTRAL
# ============================================================
# COMPATIBILITÉ ANCIENNE API
# ============================================================
def is_primary_alignment_valid(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> bool:
    """
    Compatibilité avec l'ancienne API.
    IMPORTANT :
    Cette fonction ne signifie plus que H4/H1/M15
    doivent être parfaitement alignés.
    Elle indique simplement si les trois timeframes
    donnent une direction exploitable et cohérente.
    H4 peut être différent de M15 lors d'une correction
    ou d'un contre-trend.
    """
    h4 = _normalize_direction(h4_direction)
    h1 = _normalize_direction(h1_direction)
    m15 = _normalize_direction(m15_direction)
    directions = [
        direction
        for direction in (h4, h1, m15)
        if direction != Direction.NEUTRAL
    ]
    if not directions:
        return False
    # Au moins une direction exploitable existe.
    return True
# ============================================================
# DIRECTION PRINCIPALE
# ============================================================
def get_primary_direction(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> Direction:
    """
    Retourne la meilleure direction disponible.
    Contrairement à l'ancienne version :
        H4 = H1 = M15
    n'est plus obligatoire.
    """
    return resolve_trade_direction(
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
    )
# ============================================================
# CONFIRMATION M5
# ============================================================
def is_confirmation_valid(
    confirmation: Confirmation | None,
) -> bool:
    """
    Vérifie la qualité de la confirmation M5.
    Cette fonction est informative/secondaire.
    IMPORTANT :
    Son échec ne doit PAS bloquer automatiquement
    un setup principal valide.
    """
    if confirmation is None:
        return False
    direction = _normalize_direction(
        confirmation.direction
    )
    if direction == Direction.NEUTRAL:
        return False
    return bool(
        confirmation.valid
    )
# ============================================================
# VALIDATION SETUP PRINCIPAL
# ============================================================
def is_setup_valid(
    zone: Zone,
    direction: Direction,
) -> bool:
    """
    Validation du price action setup.
    Conditions critiques :
    1. Direction valide
    2. Zone correspondant à la direction
    3. Zone clé
    4. Cassure
    5. Retest
    6. Réaction / rejet
    7. Bougie de confirmation
    8. Entrée valide
    9. Direction de cassure correcte
    Cette validation est indépendante de l'alignement
    strict H4/H1/M15.
    """
    if zone is None:
        return False
    direction = _normalize_direction(direction)
    if direction == Direction.NEUTRAL:
        return False
    zone_direction = _normalize_direction(
        getattr(
            zone,
            "direction",
            Direction.NEUTRAL,
        )
    )
    if zone_direction != direction:
        return False
    # --------------------------------------------------------
    # Validation intrinsèque de Zone
    # --------------------------------------------------------
    if not getattr(
        zone,
        "is_valid_setup",
        False,
    ):
        return False
    # --------------------------------------------------------
    # Cassure
    # --------------------------------------------------------
    if not getattr(
        zone,
        "breakout_confirmed",
        False,
    ):
        return False
    # --------------------------------------------------------
    # Retest
    # --------------------------------------------------------
    if not getattr(
        zone,
        "retest_confirmed",
        False,
    ):
        return False
    # --------------------------------------------------------
    # Réaction
    # --------------------------------------------------------
    if not getattr(
        zone,
        "rejection_confirmed",
        False,
    ):
        return False
    # --------------------------------------------------------
    # Bougie
    # --------------------------------------------------------
    if not getattr(
        zone,
        "candle_confirmation",
        False,
    ):
        return False
    # --------------------------------------------------------
    # Entrée
    # --------------------------------------------------------
    if not getattr(
        zone,
        "entry_valid",
        False,
    ):
        return False
    # --------------------------------------------------------
    # Direction de cassure
    # --------------------------------------------------------
    breakout_direction = _normalize_direction(
        getattr(
            zone,
            "breakout_direction",
            Direction.NEUTRAL,
        )
    )
    if breakout_direction != direction:
        return False
    return True
# ============================================================
# GÉOMÉTRIE ENTRY / SL / TP
# ============================================================
def validate_entry_geometry(
    direction: Direction,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> bool:
    """
    Vérifie la géométrie du trade.
    """
    direction = _normalize_direction(direction)
    try:
        entry = float(entry)
        stop_loss = float(stop_loss)
        take_profit = float(take_profit)
    except (
        TypeError,
        ValueError,
    ):
        return False
    if entry <= 0:
        return False
    if stop_loss <= 0:
        return False
    if take_profit <= 0:
        return False
    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------
    if direction == Direction.BUY:
        return (
            stop_loss < entry
            and take_profit > entry
        )
    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------
    if direction == Direction.SELL:
        return (
            stop_loss > entry
            and take_profit < entry
        )
    return False
# ============================================================
# CONSTRUCTION SIGNAL
# ============================================================
def build_signal(
    symbol: str,
    trend: TrendContext,
    zone: Zone,
    confirmation: Confirmation,
    entry: float,
    stop_loss: float,
    take_profit: float,
    spread_ok: bool = True,
    session_ok: bool = True,
    h4_direction: Direction | None = None,
    h1_direction: Direction | None = None,
    m15_direction: Direction | None = None,
    requested_direction: Direction | None = None,
    scenario: str | None = None,
    **kwargs,
) -> Signal | None:
    """
    Construit un Signal validé.
    Le pipeline peut fournir des informations
    supplémentaires via **kwargs sans casser
    la compatibilité.
    Exemples :
        scenario="CONTINUATION"
        scenario="CORRECTION"
        scenario="POTENTIAL_REVERSAL"
        scenario="COUNTER_TREND"
    La direction explicite du pipeline est prioritaire.
    """
    # ========================================================
    # 1. DIRECTIONS
    # ========================================================
    h4 = _normalize_direction(
        h4_direction
    )
    h1 = _normalize_direction(
        h1_direction
    )
    m15 = _normalize_direction(
        m15_direction
    )
    requested = _normalize_direction(
        requested_direction
    )
    # ========================================================
    # 2. FALLBACK TREND CONTEXT
    # ========================================================
    if (
        h4_direction is None
        and trend is not None
    ):
        h4 = _normalize_direction(
            getattr(
                trend,
                "direction",
                Direction.NEUTRAL,
            )
        )
    # ========================================================
    # 3. DIRECTION FINALE
    # ========================================================
    primary_direction = resolve_trade_direction(
        h4_direction=h4,
        h1_direction=h1,
        m15_direction=m15,
        requested_direction=requested,
    )
    if primary_direction == Direction.NEUTRAL:
        return None
    # ========================================================
    # 4. COHÉRENCE TREND
    # ========================================================
    if trend is None:
        return None
    # ========================================================
    # 5. SETUP PRICE ACTION
    # ========================================================
    if not is_setup_valid(
        zone,
        primary_direction,
    ):
        return None
    # ========================================================
    # 6. ENTRY / SL / TP
    # ========================================================
    if not validate_entry_geometry(
        primary_direction,
        entry,
        stop_loss,
        take_profit,
    ):
        return None
    # ========================================================
    # 7. RR
    # ========================================================
    try:
        rr = calculate_rr(
            entry,
            stop_loss,
            take_profit,
        )
        rr = float(rr)
    except (
        TypeError,
        ValueError,
        ZeroDivisionError,
    ):
        return None
    if rr < float(CONFIG.MINIMUM_RR):
        return None
    # ========================================================
    # 8. M5
    # ========================================================
    #
    # M5 reste NON BLOQUANT.
    #
    # Il peut améliorer le score mais ne doit pas
    # empêcher la création d'un signal principal.
    # ========================================================
    m5_confirmed = False
    if confirmation is not None:
        confirmation_direction = _normalize_direction(
            getattr(
                confirmation,
                "direction",
                Direction.NEUTRAL,
            )
        )
        m5_confirmed = (
            confirmation_direction
            == primary_direction
            and is_confirmation_valid(
                confirmation
            )
        )
    # Variable conservée volontairement pour
    # compatibilité et debug.
    _ = m5_confirmed
    # ========================================================
    # 9. CONFIRMATION OBJECT
    # ========================================================
    #
    # Le moteur de score utilise Confirmation.
    #
    # Si aucune confirmation n'existe, nous refusons
    # proprement plutôt que d'inventer des données.
    # ========================================================
    if confirmation is None:
        return None
    # ========================================================
    # 10. SCORE
    # ========================================================
    try:
        score = calculate_score(
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            rr=rr,
            spread_ok=spread_ok,
            session_ok=session_ok,
            # Informations supplémentaires utiles
            # au moteur de scoring.
            h4_direction=h4,
            h1_direction=h1,
            m15_direction=m15,
            direction=primary_direction,
            scenario=scenario,
            # Transmet toutes les données additionnelles
            # éventuellement produites par le pipeline.
            **kwargs,
        )
        score = float(score)
    except (
        TypeError,
        ValueError,
        AttributeError,
    ):
        # ----------------------------------------------------
        # Certains anciens moteurs de score peuvent ne pas
        # accepter les paramètres supplémentaires.
        #
        # Deuxième tentative avec l'API minimale.
        # ----------------------------------------------------
        try:
            score = calculate_score(
                trend=trend,
                zone=zone,
                confirmation=confirmation,
                rr=rr,
                spread_ok=spread_ok,
                session_ok=session_ok,
            )
            score = float(score)
        except (
            TypeError,
            ValueError,
            AttributeError,
        ):
            return None
    # ========================================================
    # 11. SCORE MINIMUM
    # ========================================================
    if not should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    ):
        return None
    # ========================================================
    # 12. ID UNIQUE
    # ========================================================
    signal_id = (
        f"{str(symbol).replace('/', '')}-"
        f"{uuid4().hex[:8].upper()}"
    )
    # ========================================================
    # 13. CRÉATION SIGNAL
    # ========================================================
    return Signal(
        signal_id=signal_id,
        symbol=symbol,
        market_type=detect_market_type(
            symbol
        ),
        direction=primary_direction,
        score=round(
            score,
            2,
        ),
        entry=round(
            float(entry),
            6,
        ),
        stop_loss=round(
            float(stop_loss),
            6,
        ),
        take_profit=round(
            float(take_profit),
            6,
        ),
        rr=round(
            rr,
            2,
        ),
        risk_percent=(
            CONFIG.DEFAULT_RISK_PERCENT
        ),
        zone=zone,
        confirmation=confirmation,
    )
# ============================================================
# CLASSE SIGNAL ENGINE
# ============================================================
class SignalEngine:
    """
    Interface objet du moteur de signal.
    Les méthodes publiques sont conservées afin
    de préserver la compatibilité avec les autres
    modules de NOVA TRADE AI.
    """
    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        self.config = CONFIG
    # ========================================================
    # TYPE DE MARCHÉ
    # ========================================================
    def detect_market_type(
        self,
        symbol: str,
    ) -> MarketType:
        return detect_market_type(
            symbol
        )
    # ========================================================
    # ALIGNEMENT / COHÉRENCE
    # ========================================================
    def is_primary_alignment_valid(
        self,
        h4_direction: Direction,
        h1_direction: Direction,
        m15_direction: Direction,
    ) -> bool:
        return is_primary_alignment_valid(
            h4_direction,
            h1_direction,
            m15_direction,
        )
    # ========================================================
    # DIRECTION
    # ========================================================
    def get_primary_direction(
        self,
        h4_direction: Direction,
        h1_direction: Direction,
        m15_direction: Direction,
    ) -> Direction:
        return get_primary_direction(
            h4_direction,
            h1_direction,
            m15_direction,
        )
    # ========================================================
    # RÉSOLUTION DIRECTION
    # ========================================================
    def resolve_trade_direction(
        self,
        h4_direction: Direction,
        h1_direction: Direction,
        m15_direction: Direction,
        requested_direction: Direction | None = None,
    ) -> Direction:
        return resolve_trade_direction(
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            requested_direction=requested_direction,
        )
    # ========================================================
    # M5
    # ========================================================
    def is_confirmation_valid(
        self,
        confirmation: Confirmation,
    ) -> bool:
        return is_confirmation_valid(
            confirmation
        )
    # ========================================================
    # SETUP
    # ========================================================
    def is_setup_valid(
        self,
        zone: Zone,
        direction: Direction,
    ) -> bool:
        return is_setup_valid(
            zone,
            direction,
        )
    # ========================================================
    # ENTRY
    # ========================================================
    def validate_entry_geometry(
        self,
        direction: Direction,
        entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> bool:
        return validate_entry_geometry(
            direction,
            entry,
            stop_loss,
            take_profit,
        )
    # ========================================================
    # BUILD SIGNAL
    # ========================================================
    def build_signal(
        self,
        symbol: str,
        trend: TrendContext,
        zone: Zone,
        confirmation: Confirmation,
        entry: float,
        stop_loss: float,
        take_profit: float,
        spread_ok: bool = True,
        session_ok: bool = True,
        h4_direction: Direction | None = None,
        h1_direction: Direction | None = None,
        m15_direction: Direction | None = None,
        requested_direction: Direction | None = None,
        scenario: str | None = None,
        **kwargs,
    ) -> Signal | None:
        return build_signal(
            symbol=symbol,
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            spread_ok=spread_ok,
            session_ok=session_ok,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            requested_direction=requested_direction,
            scenario=scenario,
            **kwargs,
        )