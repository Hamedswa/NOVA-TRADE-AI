"""
NOVA TRADE AI
signals/signal_engine.py

MOTEUR DE VALIDATION DES ENTRÉES.

Un alignement de timeframe ne suffit PAS.

Validation obligatoire :

    H4/H1/M15
        ↓
    Tendance
        ↓
    Zone clé
        ↓
    Cassure
        ↓
    Retest
        ↓
    Réaction
        ↓
    Bougie de confirmation
        ↓
    Entrée précise
        ↓
    SL / TP
        ↓
    RR
        ↓
    SCORE
        ↓
    SIGNAL

IMPORTANT :

M5 est une confirmation secondaire.
M5 ne bloque jamais un setup principal
H4 + H1 + M15 parfaitement aligné.
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

from scoring.score_engine import (
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
# ALIGNEMENT PRINCIPAL
# ============================================================

def is_primary_alignment_valid(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> bool:
    """
    H4 + H1 + M15 doivent être parfaitement alignés.

    Une direction NEUTRAL invalide l'alignement principal.
    """

    directions = (
        h4_direction,
        h1_direction,
        m15_direction,
    )

    if any(
        direction == Direction.NEUTRAL
        for direction in directions
    ):
        return False

    return (
        h4_direction
        == h1_direction
        == m15_direction
    )


# ============================================================
# DIRECTION PRINCIPALE
# ============================================================

def get_primary_direction(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> Direction:
    """
    Retourne la direction principale uniquement
    lorsque H4/H1/M15 sont parfaitement alignés.
    """

    if not is_primary_alignment_valid(
        h4_direction,
        h1_direction,
        m15_direction,
    ):
        return Direction.NEUTRAL

    return h4_direction


# ============================================================
# CONFIRMATION M5
# ============================================================

def is_confirmation_valid(
    confirmation: Confirmation,
) -> bool:
    """
    Vérifie la confirmation M5.

    IMPORTANT :
    Cette fonction ne doit jamais être utilisée
    comme condition obligatoire pour autoriser
    un setup principal valide.
    """

    if confirmation is None:
        return False

    if (
        confirmation.direction
        == Direction.NEUTRAL
    ):
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
    Validation CRITIQUE du price action setup.

    Conditions obligatoires :

    1. Direction valide
    2. Zone correspondant à la direction
    3. Zone clé réelle
    4. Cassure confirmée
    5. Retest confirmé
    6. Rejet confirmé
    7. Bougie de confirmation
    8. Entrée proche de la zone
    9. Direction de cassure correcte
    """

    if zone is None:
        return False

    if direction == Direction.NEUTRAL:
        return False

    if zone.direction != direction:
        return False

    # --------------------------------------------------------
    # Validation principale fournie par Zone
    # --------------------------------------------------------

    if not getattr(
        zone,
        "is_valid_setup",
        False,
    ):
        return False

    # --------------------------------------------------------
    # Sécurité supplémentaire
    # --------------------------------------------------------

    if not getattr(
        zone,
        "breakout_confirmed",
        False,
    ):
        return False

    if not getattr(
        zone,
        "retest_confirmed",
        False,
    ):
        return False

    if not getattr(
        zone,
        "rejection_confirmed",
        False,
    ):
        return False

    if not getattr(
        zone,
        "candle_confirmation",
        False,
    ):
        return False

    if not getattr(
        zone,
        "entry_valid",
        False,
    ):
        return False

    # --------------------------------------------------------
    # Direction de la cassure
    # --------------------------------------------------------

    breakout_direction = getattr(
        zone,
        "breakout_direction",
        Direction.NEUTRAL,
    )

    if breakout_direction != direction:
        return False

    return True


# ============================================================
# VALIDATION ENTRY
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
) -> Signal | None:
    """
    Construit un Signal uniquement lorsque toutes
    les conditions critiques sont satisfaites.
    """

    # ========================================================
    # 1. DIRECTION PRINCIPALE
    # ========================================================

    primary_direction = Direction.NEUTRAL

    # --------------------------------------------------------
    # Cas 1 : directions explicites disponibles
    # --------------------------------------------------------

    if all(
        direction is not None
        for direction in (
            h4_direction,
            h1_direction,
            m15_direction,
        )
    ):

        primary_direction = (
            get_primary_direction(
                h4_direction,
                h1_direction,
                m15_direction,
            )
        )

    # --------------------------------------------------------
    # Cas 2 : TrendContext disponible
    # --------------------------------------------------------

    else:

        if trend is not None:

            primary_direction = (
                trend.direction
            )

    # --------------------------------------------------------
    # Direction invalide
    # --------------------------------------------------------

    if (
        primary_direction
        == Direction.NEUTRAL
    ):
        return None

    # ========================================================
    # 2. ALIGNEMENT EXPLICITE
    # ========================================================

    if all(
        direction is not None
        for direction in (
            h4_direction,
            h1_direction,
            m15_direction,
        )
    ):

        if not is_primary_alignment_valid(
            h4_direction,
            h1_direction,
            m15_direction,
        ):
            return None

    # ========================================================
    # 3. PRICE ACTION SETUP
    # ========================================================

    if not is_setup_valid(
        zone,
        primary_direction,
    ):
        return None

    # ========================================================
    # 4. ENTRY / SL / TP
    # ========================================================

    if not validate_entry_geometry(
        primary_direction,
        entry,
        stop_loss,
        take_profit,
    ):
        return None

    # ========================================================
    # 5. RR
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

    # --------------------------------------------------------
    # RR minimum
    # --------------------------------------------------------

    if rr < CONFIG.MINIMUM_RR:
        return None

    # ========================================================
    # 6. M5
    #
    # IMPORTANT :
    # M5 est secondaire.
    # Il ne bloque jamais le signal.
    # ========================================================

    m5_confirmed = False

    if confirmation is not None:

        m5_confirmed = (
            confirmation.direction
            == primary_direction
            and is_confirmation_valid(
                confirmation
            )
        )

    # Variable volontairement conservée pour
    # permettre au score d'utiliser M5.
    _ = m5_confirmed

    # ========================================================
    # 7. SCORE
    # ========================================================

    if trend is None:
        return None

    if zone is None:
        return None

    if confirmation is None:
        return None

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
    # 8. SCORE MINIMUM
    # ========================================================

    if not should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    ):
        return None

    # ========================================================
    # 9. ID UNIQUE
    # ========================================================

    signal_id = (
        f"{str(symbol).replace('/', '')}-"
        f"{uuid4().hex[:8].upper()}"
    )

    # ========================================================
    # 10. CRÉATION SIGNAL
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
    Interface objet utilisée par analysis/pipeline.py.

    Les fonctions originales restent disponibles
    afin de préserver la compatibilité avec les autres
    modules du projet.
    """

    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        """
        Initialisation volontairement légère.

        Le moteur utilise CONFIG pour les paramètres
        globaux du système.
        """

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
    # ALIGNEMENT
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
        )