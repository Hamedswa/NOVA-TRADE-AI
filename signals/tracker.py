"""
NOVA TRADE AI
signals/tracker.py

TRACKER DES SIGNAUX PUBLIÉS - MOTEUR 2

Rôle :
    - conserver l'état des signaux déjà publiés ;
    - suivre le prix ;
    - calculer la progression en R ;
    - suivre TP1 / TP2 / TP3 ;
    - détecter SL ;
    - produire une recommandation de Break-Even.

IMPORTANT
---------
Ce module est STRICTEMENT observationnel.

Il ne doit JAMAIS :
    - créer un signal de trading ;
    - détecter un setup ;
    - valider un setup ;
    - rejeter un setup ;
    - produire READY_FOR_SIGNAL ;
    - modifier Entry ;
    - modifier SL ;
    - modifier TP ;
    - modifier le RR ;
    - modifier le score ;
    - exécuter un ordre ;
    - activer réellement le Break-Even.

La validation appartient exclusivement à :
    moteur2_validation.py

Le monitor observe le tracker et envoie éventuellement
des notifications Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from config import CONFIG


# ============================================================
# CONSTANTES
# ============================================================

SUPPORTED_SYMBOLS = {
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
}

ACTIVE_STATUSES = {
    "ACTIVE",
    "BE_RECOMMENDED",
}

TERMINAL_STATUSES = {
    "TP1_HIT",
    "TP2_HIT",
    "TP3_HIT",
    "TP_HIT",
    "SL_HIT",
}


# ============================================================
# UTILITAIRES
# ============================================================

def _normalize_symbol(
    symbol: Any,
) -> str:
    """
    Normalise un symbole de marché.
    """

    value = str(
        symbol or ""
    ).upper().strip()

    value = (
        value
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    return value


def _get_value(
    obj: Any,
    *names: str,
    default: Any = None,
) -> Any:
    """
    Récupère une valeur depuis un objet ou un dictionnaire.
    """

    for name in names:

        if isinstance(
            obj,
            dict,
        ):

            if name in obj:
                return obj[name]

        elif hasattr(
            obj,
            name,
        ):

            return getattr(
                obj,
                name,
            )

    return default


def _direction(
    signal: Any,
) -> str:
    """
    Retourne BUY ou SELL.
    """

    value = _get_value(
        signal,
        "direction",
        default="",
    )

    if hasattr(
        value,
        "value",
    ):

        value = value.value

    value = str(
        value or ""
    ).upper().strip()

    if value in {
        "LONG",
        "BUY",
    }:
        return "BUY"

    if value in {
        "SHORT",
        "SELL",
    }:
        return "SELL"

    return value


def _float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:
    """
    Conversion sûre vers float.
    """

    if value is None:
        return default

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return default


def _now() -> datetime:
    """
    Timestamp UTC.
    """

    return datetime.now(
        timezone.utc
    )


# ============================================================
# ETAT DU SIGNAL
# ============================================================

@dataclass
class TrackerState:
    """
    État observationnel d'un signal publié.

    Les données Entry / SL / TP proviennent du signal publié
    et ne sont jamais modifiées par le tracker.
    """

    signal: Any

    current_price: float

    status: str = "ACTIVE"

    current_r: float = 0.0
    best_r: float = 0.0
    worst_r: float = 0.0

    progress_to_tp_percent: float = 0.0

    distance_to_sl: float = 0.0
    distance_to_tp: float = 0.0

    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    sl_hit: bool = False

    be_recommended: bool = False
    be_recommended_at: Optional[
        datetime
    ] = None

    last_update: datetime = field(
        default_factory=_now
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# TRACKER
# ============================================================

class SignalTracker:
    """
    Gestionnaire observationnel des signaux publiés.
    """

    def __init__(
        self,
    ) -> None:

        self._states: dict[
            str,
            TrackerState,
        ] = {}

    # ========================================================
    # SIGNAL ID
    # ========================================================

    @staticmethod
    def _signal_id(
        signal: Any,
    ) -> str:
        """
        Récupère l'identifiant du signal.
        """

        value = _get_value(
            signal,
            "signal_id",
            "id",
            "setup_id",
            default="",
        )

        return str(
            value or ""
        )

    # ========================================================
    # PRIX
    # ========================================================

    @staticmethod
    def _entry(
        signal: Any,
    ) -> Optional[float]:

        return _float(
            _get_value(
                signal,
                "entry",
                "entry_price",
            )
        )

    @staticmethod
    def _stop_loss(
        signal: Any,
    ) -> Optional[float]:

        return _float(
            _get_value(
                signal,
                "stop_loss",
                "sl",
                "stop",
            )
        )

    @staticmethod
    def _tp1(
        signal: Any,
    ) -> Optional[float]:

        return _float(
            _get_value(
                signal,
                "take_profit",
                "tp1",
                "tp_1",
                "take_profit_1",
            )
        )

    @staticmethod
    def _tp2(
        signal: Any,
    ) -> Optional[float]:

        return _float(
            _get_value(
                signal,
                "tp2",
                "tp_2",
                "take_profit_2",
            )
        )

    @staticmethod
    def _tp3(
        signal: Any,
    ) -> Optional[float]:

        return _float(
            _get_value(
                signal,
                "tp3",
                "tp_3",
                "take_profit_3",
            )
        )

    # ========================================================
    # REGISTER
    # ========================================================

    def register(
        self,
        signal: Any,
    ) -> TrackerState:
        """
        Enregistre un signal déjà publié.

        Le tracker ne vérifie pas si le setup est valide :
        cette responsabilité appartient à moteur2_validation.py.
        """

        signal_id = self._signal_id(
            signal
        )

        if not signal_id:

            raise ValueError(
                "Signal sans signal_id/setup_id."
            )

        symbol = _normalize_symbol(
            _get_value(
                signal,
                "symbol",
                default="",
            )
        )

        if symbol not in SUPPORTED_SYMBOLS:

            raise ValueError(
                f"Symbole non supporté : {symbol}"
            )

        entry = self._entry(
            signal
        )

        if entry is None or entry <= 0:

            raise ValueError(
                f"Entry invalide pour {signal_id}."
            )

        state = TrackerState(
            signal=signal,
            current_price=entry,
        )

        state.metadata.update(
            {
                "symbol": symbol,
                "direction": _direction(
                    signal
                ),
                "observation_only": True,
                "signal_mutation_allowed": False,
                "execution_allowed": False,
            }
        )

        self._states[
            signal_id
        ] = state

        return state

    # ========================================================
    # GET
    # ========================================================

    def get(
        self,
        signal_id: str,
    ) -> Optional[TrackerState]:

        return self._states.get(
            str(signal_id)
        )

    # ========================================================
    # FIND ACTIVE BY SYMBOL
    # ========================================================

    def find_active_by_symbol(
        self,
        symbol: str,
    ) -> Optional[TrackerState]:

        normalized = _normalize_symbol(
            symbol
        )

        for state in self._states.values():

            state_symbol = _normalize_symbol(
                _get_value(
                    state.signal,
                    "symbol",
                    default="",
                )
            )

            if (
                state_symbol == normalized
                and state.status
                in ACTIVE_STATUSES
            ):

                return state

        return None

    # ========================================================
    # ACTIVE SIGNALS
    # ========================================================

    def active_signals(
        self,
    ) -> list[TrackerState]:

        return [
            state
            for state in self._states.values()
            if state.status
            in ACTIVE_STATUSES
        ]

    # ========================================================
    # ALL STATES
    # ========================================================

    def all_states(
        self,
    ) -> list[TrackerState]:

        return list(
            self._states.values()
        )

    # ========================================================
    # R CALCULATION
    # ========================================================

    @staticmethod
    def calculate_r(
        signal: Any,
        price: float,
    ) -> float:
        """
        Calcule le résultat en R.

        R = distance parcourue / distance Entry-SL.

        BUY :
            (Price - Entry) / Risk

        SELL :
            (Entry - Price) / Risk
        """

        entry = _float(
            _get_value(
                signal,
                "entry",
                "entry_price",
            )
        )

        stop_loss = _float(
            _get_value(
                signal,
                "stop_loss",
                "sl",
                "stop",
            )
        )

        if (
            entry is None
            or stop_loss is None
        ):

            return 0.0

        risk = abs(
            entry - stop_loss
        )

        if risk <= 0:
            return 0.0

        direction = _direction(
            signal
        )

        if direction == "BUY":

            return (
                float(price) - entry
            ) / risk

        if direction == "SELL":

            return (
                entry - float(price)
            ) / risk

        return 0.0

    # ========================================================
    # TP HIT
    # ========================================================

    @staticmethod
    def _target_hit(
        direction: str,
        price: float,
        target: Optional[float],
    ) -> bool:

        if target is None:
            return False

        if direction == "BUY":

            return price >= target

        if direction == "SELL":

            return price <= target

        return False

    # ========================================================
    # SL HIT
    # ========================================================

    @staticmethod
    def _stop_hit(
        direction: str,
        price: float,
        stop_loss: Optional[float],
    ) -> bool:

        if stop_loss is None:
            return False

        if direction == "BUY":

            return price <= stop_loss

        if direction == "SELL":

            return price >= stop_loss

        return False

    # ========================================================
    # PROGRESSION TP1
    # ========================================================

    @staticmethod
    def _progress_to_tp1(
        signal: Any,
        price: float,
    ) -> float:

        entry = _float(
            _get_value(
                signal,
                "entry",
                "entry_price",
            )
        )

        tp1 = _float(
            _get_value(
                signal,
                "take_profit",
                "tp1",
                "tp_1",
                "take_profit_1",
            )
        )

        if (
            entry is None
            or tp1 is None
        ):

            return 0.0

        distance = abs(
            tp1 - entry
        )

        if distance <= 0:
            return 0.0

        direction = _direction(
            signal
        )

        if direction == "BUY":

            progress = (
                price - entry
            ) / distance

        elif direction == "SELL":

            progress = (
                entry - price
            ) / distance

        else:

            return 0.0

        return round(
            max(
                0.0,
                min(
                    100.0,
                    progress * 100.0,
                ),
            ),
            2,
        )

    # ========================================================
    # UPDATE
    # ========================================================

    def update(
        self,
        signal_id: str,
        current_price: float,
    ) -> TrackerState:
        """
        Met à jour uniquement les données d'observation.

        Entry / SL / TP du signal ne sont jamais modifiés.
        """

        signal_id = str(
            signal_id
        )

        state = self._states.get(
            signal_id
        )

        if state is None:

            raise KeyError(
                f"Signal inconnu : {signal_id}"
            )

        try:

            price = float(
                current_price
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                f"Prix invalide : {current_price}"
            )

        if price <= 0:

            raise ValueError(
                f"Prix invalide : {price}"
            )

        signal = state.signal

        direction = _direction(
            signal
        )

        # ----------------------------------------------------
        # Prix actuel
        # ----------------------------------------------------

        state.current_price = price

        # ----------------------------------------------------
        # R
        # ----------------------------------------------------

        state.current_r = round(
            self.calculate_r(
                signal,
                price,
            ),
            4,
        )

        state.best_r = max(
            state.best_r,
            state.current_r,
        )

        state.worst_r = min(
            state.worst_r,
            state.current_r,
        )

        # ----------------------------------------------------
        # TP1 / TP2 / TP3
        # ----------------------------------------------------

        tp1 = self._tp1(
            signal
        )

        tp2 = self._tp2(
            signal
        )

        tp3 = self._tp3(
            signal
        )

        state.tp1_hit = (
            state.tp1_hit
            or self._target_hit(
                direction,
                price,
                tp1,
            )
        )

        state.tp2_hit = (
            state.tp2_hit
            or self._target_hit(
                direction,
                price,
                tp2,
            )
        )

        state.tp3_hit = (
            state.tp3_hit
            or self._target_hit(
                direction,
                price,
                tp3,
            )
        )

        # ----------------------------------------------------
        # SL
        # ----------------------------------------------------

        stop_loss = self._stop_loss(
            signal
        )

        state.sl_hit = (
            state.sl_hit
            or self._stop_hit(
                direction,
                price,
                stop_loss,
            )
        )

        # ----------------------------------------------------
        # Progression vers TP1
        # ----------------------------------------------------

        state.progress_to_tp_percent = (
            self._progress_to_tp1(
                signal,
                price,
            )
        )

        # ----------------------------------------------------
        # Distances
        # ----------------------------------------------------

        if stop_loss is not None:

            state.distance_to_sl = abs(
                price - stop_loss
            )

        tp1 = self._tp1(
            signal
        )

        if tp1 is not None:

            state.distance_to_tp = abs(
                tp1 - price
            )

        # ----------------------------------------------------
        # Statut terminal
        #
        # Priorité :
        #   TP3 > TP2 > TP1 > SL
        #
        # Une fois terminal, le tracker ne revient
        # pas automatiquement à ACTIVE.
        # ----------------------------------------------------

        if state.tp3_hit:

            state.status = "TP3_HIT"

        elif state.tp2_hit:

            state.status = "TP2_HIT"

        elif state.tp1_hit:

            state.status = "TP1_HIT"

        elif state.sl_hit:

            state.status = "SL_HIT"

        # ----------------------------------------------------
        # Break-Even recommandé
        # ----------------------------------------------------

        elif (
            not state.be_recommended
            and state.current_r
            >= float(
                getattr(
                    CONFIG,
                    "BE_TRIGGER_R",
                    1.0,
                )
            )
        ):

            state.be_recommended = True

            state.be_recommended_at = _now()

            state.status = (
                "BE_RECOMMENDED"
            )

        # ----------------------------------------------------
        # Mise à jour temporelle
        # ----------------------------------------------------

        state.last_update = _now()

        return state

    # ========================================================
    # BREAK-EVEN
    # ========================================================

    def recommend_be(
        self,
        signal_id: str,
    ) -> TrackerState:
        """
        Enregistre uniquement une recommandation BE.

        IMPORTANT :
            Cette fonction ne modifie PAS le SL.

        Elle ne calcule aucun nouveau prix de SL.
        """

        state = self._states.get(
            str(signal_id)
        )

        if state is None:

            raise KeyError(
                f"Signal inconnu : {signal_id}"
            )

        if state.status in TERMINAL_STATUSES:

            return state

        if not state.be_recommended:

            state.be_recommended = True

            state.be_recommended_at = _now()

            state.status = (
                "BE_RECOMMENDED"
            )

            state.last_update = _now()

        return state

    # ========================================================
    # COMPATIBILITE
    # ========================================================

    def activate_be(
        self,
        signal_id: str,
    ) -> TrackerState:
        """
        Compatibilité volontaire avec l'ancien code.

        Cette méthode N'ACTIVE PAS le Break-Even.

        Elle transforme uniquement l'appel ancien
        en recommandation BE afin d'empêcher toute
        modification automatique du Stop Loss.
        """

        return self.recommend_be(
            signal_id
        )

    # ========================================================
    # DESACTIVER / CLOTURER
    # ========================================================

    def close_signal(
        self,
        signal_id: str,
        reason: str = "MANUAL",
    ) -> Optional[TrackerState]:
        """
        Clôture observationnelle d'un état.

        Cette fonction ne passe pas d'ordre et ne modifie
        aucune donnée Entry / SL / TP.
        """

        state = self._states.get(
            str(signal_id)
        )

        if state is None:
            return None

        state.status = str(
            reason or "CLOSED"
        ).upper()

        state.last_update = _now()

        return state

    # ========================================================
    # REMOVE
    # ========================================================

    def remove(
        self,
        signal_id: str,
    ) -> bool:
        """
        Supprime uniquement l'état local du tracker.

        Ne modifie pas le signal publié.
        """

        signal_id = str(
            signal_id
        )

        if signal_id not in self._states:
            return False

        del self._states[
            signal_id
        ]

        return True

    # ========================================================
    # STATUS
    # ========================================================

    def get_status(self) -> dict[str, Any]:
        """
        Statut général du tracker.
        """

        active = len(
            self.active_signals()
        )

        terminal = sum(
            1
            for state
            in self._states.values()
            if state.status
            in TERMINAL_STATUSES
        )

        return {
            "total_signals": len(
                self._states
            ),
            "active_signals": active,
            "terminal_signals": terminal,
            "observation_only": True,
            "can_generate_signal": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "can_modify_entry": False,
            "can_modify_stop_loss": False,
            "can_modify_take_profit": False,
            "can_modify_rr": False,
            "can_execute_order": False,
            "can_activate_break_even": False,
            "be_mode": "RECOMMENDATION_ONLY",
            "validation_owner": (
                "moteur2_validation.py"
            ),
        }


# ============================================================
# TEST LOCAL
# ============================================================

def test_signal_tracker() -> dict[str, Any]:
    """
    Test structurel sans signal réel.
    """

    return {
        "success": True,
        "observation_only": True,
        "tp1_supported": True,
        "tp2_supported": True,
        "tp3_supported": True,
        "sl_supported": True,
        "r_tracking": True,
        "be_mode": "RECOMMENDATION_ONLY",
        "can_generate_signal": False,
        "can_validate_signal": False,
        "can_reject_signal": False,
        "can_modify_signal": False,
        "can_execute_order": False,
        "can_activate_break_even": False,
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    result = (
        test_signal_tracker()
    )

    print()
    print(
        "=============================================="
    )
    print(
        " NOVA TRADE AI - SIGNAL TRACKER"
    )
    print(
        "=============================================="
    )
    print(
        f"Test : {result['success']}"
    )
    print(
        f"Observation only : "
        f"{result['observation_only']}"
    )
    print(
        f"TP1 : {result['tp1_supported']}"
    )
    print(
        f"TP2 : {result['tp2_supported']}"
    )
    print(
        f"TP3 : {result['tp3_supported']}"
    )
    print(
        f"SL : {result['sl_supported']}"
    )
    print(
        f"Suivi R : {result['r_tracking']}"
    )
    print(
        f"BE : {result['be_mode']}"
    )
    print(
        f"Validation : "
        f"{result['can_validate_signal']}"
    )
    print(
        f"Exécution : "
        f"{result['can_execute_order']}"
    )
    print(
        "=============================================="
    )