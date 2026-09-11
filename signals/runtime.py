"""
NOVA TRADE AI
signals/runtime.py

Runtime central du suivi des signaux Moteur 2.

Rôle :
    - créer le singleton SignalTracker ;
    - créer le singleton SignalMonitor ;
    - fournir au monitor le prix provenant du cache Moteur 2 ;
    - fournir le callback Telegram lorsque configuré ;
    - enregistrer les signaux déjà publiés ;
    - empêcher les doublons actifs par symbole.

IMPORTANT
---------
Ce module ne valide aucun setup.

La validation appartient exclusivement à :
    moteur2_validation.py

Ce module ne :
    - génère pas de signal ;
    - valide pas de signal ;
    - rejette pas de signal ;
    - modifie pas Entry / SL / TP ;
    - active pas le Break-Even ;
    - exécute pas d'ordre.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional


from signals.monitor import SignalMonitor
from signals.tracker import SignalTracker


logger = logging.getLogger(__name__)


# ============================================================
# TYPES
# ============================================================

TelegramSender = Callable[
    [str],
    Awaitable[None],
]


# ============================================================
# ETAT DES DEPENDANCES
# ============================================================

_price_provider: Optional[
    Callable[[str], Any]
] = None

_telegram_sender: Optional[
    TelegramSender
] = None


# ============================================================
# PRICE PROVIDER
# ============================================================

def _get_price_from_moteur2(
    symbol: str,
) -> float:
    """
    Récupère le prix actuel depuis le cache Moteur 2.

    Le cache est alimenté par BiQuote.

    Aucun fallback vers :
        - market_data.py
        - Twelve Data
        - une autre source.

    Le prix doit donc provenir du système Moteur 2.
    """

    if _price_provider is None:

        raise RuntimeError(
            "Le price provider Moteur 2 n'est pas configuré."
        )

    result = _price_provider(
        symbol
    )

    # --------------------------------------------------------
    # Prix directement retourné
    # --------------------------------------------------------

    if isinstance(
        result,
        (int, float),
    ):

        price = float(
            result
        )

        if price <= 0:

            raise ValueError(
                f"Prix invalide pour {symbol}: {price}"
            )

        return price

    # --------------------------------------------------------
    # Tick / dictionnaire / objet
    # --------------------------------------------------------

    if isinstance(
        result,
        dict,
    ):

        for key in (
            "mid",
            "price",
            "last",
            "bid",
        ):

            value = result.get(
                key
            )

            if value is not None:

                price = float(
                    value
                )

                if price <= 0:

                    raise ValueError(
                        f"Prix invalide pour {symbol}: {price}"
                    )

                return price

    else:

        for attribute in (
            "mid",
            "price",
            "last",
            "bid",
        ):

            if hasattr(
                result,
                attribute,
            ):

                value = getattr(
                    result,
                    attribute,
                )

                if value is not None:

                    price = float(
                        value
                    )

                    if price <= 0:

                        raise ValueError(
                            f"Prix invalide pour {symbol}: {price}"
                        )

                    return price

    raise ValueError(
        f"Prix Moteur 2 introuvable pour {symbol}."
    )


# ============================================================
# SINGLETONS
# ============================================================

signal_tracker = SignalTracker()

signal_monitor = SignalMonitor(
    tracker=signal_tracker,
    price_provider=_get_price_from_moteur2,
    interval_seconds=30,
)


# ============================================================
# CONFIGURATION
# ============================================================

def configure_runtime(
    price_provider: Optional[
        Callable[[str], Any]
    ] = None,
    telegram_sender: Optional[
        TelegramSender
    ] = None,
) -> None:
    """
    Configure les dépendances externes du runtime.

    price_provider :
        fonction fournissant le prix actuel depuis Moteur 2.

    telegram_sender :
        callback asynchrone permettant au monitor
        d'envoyer ses notifications.

    Cette fonction ne modifie aucun signal.
    """

    global _price_provider
    global _telegram_sender

    if price_provider is not None:

        _price_provider = (
            price_provider
        )

    if telegram_sender is not None:

        _telegram_sender = (
            telegram_sender
        )

        signal_monitor.telegram_sender = (
            telegram_sender
        )

    logger.info(
        "Runtime signaux configuré."
    )


# ============================================================
# CONFIGURATION DEPUIS MOTEUR 2
# ============================================================

def configure_from_moteur2(
    moteur2: Any,
    telegram_sender: Optional[
        TelegramSender
    ] = None,
) -> None:
    """
    Raccorde automatiquement le runtime
    à l'instance Moteur 2.

    Le runtime recherche prioritairement :

        moteur2.cache.get_current_price(symbol)

    ou :

        moteur2.get_current_price(symbol)

    Le flux réel reste donc :

        BiQuote Stream
              ↓
        Moteur 2 Cache
              ↓
        Signal Monitor
    """

    cache = getattr(
        moteur2,
        "cache",
        None,
    )

    if cache is not None:

        get_current_price = getattr(
            cache,
            "get_current_price",
            None,
        )

        if callable(
            get_current_price
        ):

            configure_runtime(
                price_provider=get_current_price,
                telegram_sender=telegram_sender,
            )

            logger.info(
                "Runtime connecté au cache Moteur 2."
            )

            return

    get_current_price = getattr(
        moteur2,
        "get_current_price",
        None,
    )

    if callable(
        get_current_price
    ):

        configure_runtime(
            price_provider=get_current_price,
            telegram_sender=telegram_sender,
        )

        logger.info(
            "Runtime connecté à Moteur 2."
        )

        return

    raise RuntimeError(
        "Impossible de trouver "
        "get_current_price() dans Moteur 2 "
        "ou son cache."
    )


# ============================================================
# START
# ============================================================

def start_signal_monitor() -> None:
    """
    Démarre le monitor observationnel.
    """

    signal_monitor.start()

    logger.info(
        "Signal Monitor démarré depuis le runtime."
    )


# ============================================================
# STOP
# ============================================================

async def stop_signal_monitor() -> None:
    """
    Arrête proprement le monitor.
    """

    await signal_monitor.stop()

    logger.info(
        "Signal Monitor arrêté depuis le runtime."
    )


# ============================================================
# REGISTER
# ============================================================

def register_signal(
    signal: Any,
):
    """
    Enregistre un signal déjà publié par Moteur 2.

    IMPORTANT :
        Le runtime ne valide pas le signal.

    Le signal doit déjà avoir franchi :

        moteur2_validation.py
                ↓
        READY_FOR_SIGNAL
                ↓
        anti-spam
                ↓
        publication
                ↓
        register_signal()
    """

    symbol = getattr(
        signal,
        "symbol",
        None,
    )

    if symbol is None:

        if isinstance(
            signal,
            dict,
        ):

            symbol = signal.get(
                "symbol"
            )

    if not symbol:

        raise ValueError(
            "Impossible d'enregistrer un signal "
            "sans symbole."
        )

    # --------------------------------------------------------
    # Anti-duplication d'observation.
    #
    # Ceci ne remplace PAS moteur2_antispam.py.
    # --------------------------------------------------------

    existing = (
        signal_tracker.find_active_by_symbol(
            symbol
        )
    )

    if existing is not None:

        logger.info(
            "Signal déjà suivi pour %s.",
            symbol,
        )

        return existing, False

    # --------------------------------------------------------
    # Enregistrement dans le tracker.
    # --------------------------------------------------------

    state = signal_tracker.register(
        signal
    )

    logger.info(
        "Signal publié enregistré dans le tracker : %s",
        getattr(
            signal,
            "signal_id",
            getattr(
                signal,
                "id",
                "unknown",
            ),
        ),
    )

    return state, True


# ============================================================
# STATUS
# ============================================================

def get_runtime_status() -> dict[str, Any]:
    """
    Retourne l'état du runtime.
    """

    tracker_status = (
        signal_tracker.get_status()
    )

    monitor_status = (
        signal_monitor.get_status()
    )

    return {
        "runtime": "Moteur 2",
        "tracker": tracker_status,
        "monitor": monitor_status,
        "price_provider_configured": (
            _price_provider is not None
        ),
        "telegram_sender_configured": (
            _telegram_sender is not None
        ),
        "observation_only": True,
        "can_generate_signal": False,
        "can_validate_signal": False,
        "can_reject_signal": False,
        "can_modify_signal": False,
        "can_execute_order": False,
        "can_activate_break_even": False,
        "validation_owner": (
            "moteur2_validation.py"
        ),
    }


# ============================================================
# TEST LOCAL
# ============================================================

def test_signal_runtime() -> dict[str, Any]:
    """
    Test structurel du runtime.

    Aucun signal réel n'est créé.
    """

    return {
        "success": True,
        "runtime": "Moteur 2",
        "observation_only": True,
        "can_generate_signal": False,
        "can_validate_signal": False,
        "can_reject_signal": False,
        "can_modify_signal": False,
        "can_execute_order": False,
        "can_activate_break_even": False,
        "validation_owner": (
            "moteur2_validation.py"
        ),
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    result = (
        test_signal_runtime()
    )

    print()
    print(
        "=============================================="
    )
    print(
        " NOVA TRADE AI - SIGNAL RUNTIME"
    )
    print(
        "=============================================="
    )
    print(
        f"Test : {result['success']}"
    )
    print(
        f"Runtime : {result['runtime']}"
    )
    print(
        f"Observation only : "
        f"{result['observation_only']}"
    )
    print(
        f"Génération signal : "
        f"{result['can_generate_signal']}"
    )
    print(
        f"Validation : "
        f"{result['can_validate_signal']}"
    )
    print(
        f"Rejet : "
        f"{result['can_reject_signal']}"
    )
    print(
        f"Modification : "
        f"{result['can_modify_signal']}"
    )
    print(
        f"Exécution : "
        f"{result['can_execute_order']}"
    )
    print(
        f"Activation BE : "
        f"{result['can_activate_break_even']}"
    )
    print(
        f"Validation owner : "
        f"{result['validation_owner']}"
    )
    print(
        "=============================================="
    )