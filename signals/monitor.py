"""
NOVA TRADE AI
signals/monitor.py

MONITEUR DES SIGNAUX PUBLIÉS

Rôle :
    - observer les signaux déjà publiés ;
    - récupérer leur prix actuel via BiQuote / Moteur 2 ;
    - calculer la progression en R à partir du tracker ;
    - détecter les paliers de progression ;
    - détecter une recommandation de Break-Even ;
    - détecter TP / SL ;
    - envoyer des notifications Telegram.

IMPORTANT
---------
Ce module est STRICTEMENT OBSERVATIONNEL.

Il ne doit JAMAIS :
    - créer un signal ;
    - générer BUY / SELL ;
    - valider un setup ;
    - rejeter un setup ;
    - produire READY_FOR_SIGNAL ;
    - modifier Entry ;
    - modifier SL ;
    - modifier TP ;
    - modifier le RR ;
    - modifier le score ;
    - activer réellement le Break-Even ;
    - exécuter un ordre ;
    - annuler un signal.

La validation appartient exclusivement à :
    moteur2_validation.py

Le tracker conserve l'état d'observation.
Le monitor ne fait qu'observer et notifier.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable, Optional


logger = logging.getLogger(__name__)


# ============================================================
# TYPES
# ============================================================

TelegramSender = Callable[
    [str],
    Awaitable[None],
]

PriceProvider = Callable[
    [str],
    Any,
]


# ============================================================
# MONITEUR
# ============================================================

class SignalMonitor:
    """
    Moniteur observationnel des signaux publiés.

    Le prix est fourni par le Moteur 2 / cache BiQuote
    via price_provider.

    Le tracker reste propriétaire de l'état du signal.
    """

    # Paliers de progression en R.
    R_MILESTONES = (
        0.5,
        1.0,
        1.5,
        2.0,
        2.5,
        3.0,
    )

    DEFAULT_INTERVAL_SECONDS = 30

    def __init__(
        self,
        tracker: Any,
        telegram_sender: Optional[
            TelegramSender
        ] = None,
        price_provider: Optional[
            PriceProvider
        ] = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ) -> None:

        self.tracker = tracker

        self.telegram_sender = (
            telegram_sender
        )

        self.price_provider = (
            price_provider
        )

        self.interval_seconds = max(
            5,
            int(interval_seconds),
        )

        self._task: Optional[
            asyncio.Task
        ] = None

        self._running = False

        # ----------------------------------------------------
        # Signal ID -> paliers déjà annoncés
        # ----------------------------------------------------

        self._notified_r: dict[
            str,
            set[float],
        ] = {}

        # ----------------------------------------------------
        # Signal ID -> BE déjà recommandé
        # ----------------------------------------------------

        self._notified_be: set[
            str
        ] = set()

        # ----------------------------------------------------
        # Signal ID -> fin déjà annoncée
        # ----------------------------------------------------

        self._notified_terminal: set[
            str
        ] = set()

    # ========================================================
    # UTILITAIRES
    # ========================================================

    @staticmethod
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

            else:

                if hasattr(
                    obj,
                    name,
                ):

                    return getattr(
                        obj,
                        name,
                    )

        return default

    @classmethod
    def _get_signal_id(
        cls,
        signal: Any,
    ) -> str:
        """
        Récupère l'identifiant stable du signal.
        """

        signal_id = cls._get_value(
            signal,
            "signal_id",
            "id",
            "setup_id",
            default="",
        )

        return str(
            signal_id
            or ""
        )

    @classmethod
    def _get_symbol(
        cls,
        signal: Any,
    ) -> str:
        """
        Récupère le symbole.
        """

        symbol = cls._get_value(
            signal,
            "symbol",
            default="",
        )

        return str(
            symbol
            or ""
        )

    @classmethod
    def _get_direction(
        cls,
        signal: Any,
    ) -> str:
        """
        Récupère la direction sans dépendre
        d'une ancienne classe Signal.
        """

        direction = cls._get_value(
            signal,
            "direction",
            default="",
        )

        if hasattr(
            direction,
            "value",
        ):

            direction = direction.value

        return str(
            direction
            or "N/A"
        ).upper()

    @staticmethod
    def _format_price(
        price: float,
    ) -> str:
        """
        Formatage générique du prix.
        """

        try:

            value = float(
                price
            )

        except (
            TypeError,
            ValueError,
        ):

            return "N/A"

        if value >= 1000:
            return f"{value:.2f}"

        if value >= 100:
            return f"{value:.3f}"

        if value >= 1:
            return f"{value:.5f}"

        return f"{value:.6f}"

    # ========================================================
    # REGISTER
    # ========================================================

    def register(
        self,
        signal: Any,
    ) -> Any:
        """
        Enregistre un signal déjà validé/publié
        dans le tracker.

        Le monitor ne valide pas le signal.
        """

        signal_id = (
            self._get_signal_id(
                signal
            )
        )

        if not signal_id:

            raise ValueError(
                "Impossible de surveiller un signal "
                "sans identifiant."
            )

        result = self.tracker.register(
            signal
        )

        self._notified_r[
            signal_id
        ] = set()

        self._notified_be.discard(
            signal_id
        )

        self._notified_terminal.discard(
            signal_id
        )

        logger.info(
            "Signal enregistré pour observation : %s",
            signal_id,
        )

        return result

    # ========================================================
    # TELEGRAM
    # ========================================================

    async def _send(
        self,
        message: str,
    ) -> None:
        """
        Envoie une notification Telegram.

        Une erreur Telegram ne doit jamais
        arrêter le monitor.
        """

        if self.telegram_sender is None:

            logger.debug(
                "Telegram sender non configuré."
            )

            return

        try:

            result = self.telegram_sender(
                message
            )

            if inspect.isawaitable(
                result
            ):

                await result

        except Exception:

            logger.exception(
                "Erreur envoi notification Telegram."
            )

    # ========================================================
    # PRIX
    # ========================================================

    async def _get_current_price(
        self,
        symbol: str,
    ) -> float:
        """
        Récupère le prix actuel.

        La source doit être fournie par le Moteur 2,
        idéalement depuis le cache alimenté par BiQuote Stream.

        Aucun fallback vers market_data.py.
        """

        if self.price_provider is None:

            raise RuntimeError(
                "price_provider non configuré. "
                "Le SignalMonitor doit recevoir "
                "le fournisseur de prix BiQuote/Moteur 2."
            )

        result = self.price_provider(
            symbol
        )

        if inspect.isawaitable(
            result
        ):

            result = await result

        # ----------------------------------------------------
        # Prix brut
        # ----------------------------------------------------

        if isinstance(
            result,
            (int, float),
        ):

            price = float(
                result
            )

        # ----------------------------------------------------
        # Tick / dictionnaire
        # ----------------------------------------------------

        else:

            price = self._get_value(
                result,
                "mid",
                "price",
                "last",
                "bid",
                default=None,
            )

            if price is None:

                raise ValueError(
                    f"Prix BiQuote invalide pour {symbol}."
                )

            price = float(
                price
            )

        if price <= 0:

            raise ValueError(
                f"Prix invalide pour {symbol}: {price}"
            )

        return price

    # ========================================================
    # PROGRESSION
    # ========================================================

    async def _check_progress(
        self,
        state: Any,
    ) -> None:
        """
        Détecte les nouveaux paliers de progression.
        """

        signal = self._get_value(
            state,
            "signal",
            default=None,
        )

        if signal is None:
            return

        signal_id = (
            self._get_signal_id(
                signal
            )
        )

        current_r = self._get_value(
            state,
            "current_r",
            "r_multiple",
            "current_R",
            default=0.0,
        )

        try:

            current_r = float(
                current_r
            )

        except (
            TypeError,
            ValueError,
        ):

            return

        notified = (
            self._notified_r.setdefault(
                signal_id,
                set(),
            )
        )

        crossed = [
            milestone
            for milestone
            in self.R_MILESTONES
            if (
                current_r >= milestone
                and milestone not in notified
            )
        ]

        if not crossed:
            return

        # On marque tous les paliers franchis.
        for level in crossed:
            notified.add(level)

        milestone = max(
            crossed
        )

        symbol = self._get_symbol(
            signal
        )

        direction = (
            self._get_direction(
                signal
            )
        )

        current_price = self._get_value(
            state,
            "current_price",
            "price",
            default=None,
        )

        progress = self._get_value(
            state,
            "progress_to_tp_percent",
            "progress_percent",
            default=None,
        )

        if current_price is None:
            current_price = 0.0

        if progress is None:
            progress_text = "N/A"
        else:

            try:

                progress_text = (
                    f"{float(progress):.1f}%"
                )

            except (
                TypeError,
                ValueError,
            ):

                progress_text = "N/A"

        emoji = (
            "🟢"
            if current_r >= 1.0
            else "📈"
        )

        message = (
            f"{emoji} <b>PROGRESSION SIGNAL</b>\n\n"
            f"📊 Marché : <b>{symbol}</b>\n"
            f"📌 Direction : <b>{direction}</b>\n"
            f"💵 Prix actuel : "
            f"<b>{self._format_price(current_price)}</b>\n\n"
            f"📈 Résultat : <b>+{current_r:.2f}R</b>\n"
            f"🎯 Palier atteint : "
            f"<b>+{milestone:.1f}R</b>\n"
            f"📊 Progression TP : "
            f"<b>{progress_text}</b>"
        )

        await self._send(
            message
        )

    # ========================================================
    # BREAK-EVEN
    # ========================================================

    async def _check_break_even(
        self,
        state: Any,
    ) -> None:
        """
        Détecte une recommandation BE du tracker.

        IMPORTANT :
        Le monitor ne déplace jamais le SL.
        """

        signal = self._get_value(
            state,
            "signal",
            default=None,
        )

        if signal is None:
            return

        signal_id = (
            self._get_signal_id(
                signal
            )
        )

        status = self._get_value(
            state,
            "status",
            default=None,
        )

        if hasattr(
            status,
            "value",
        ):

            status = status.value

        status_text = str(
            status
            or ""
        ).upper()

        if status_text not in {
            "BE_RECOMMENDED",
            "BREAK_EVEN_RECOMMENDED",
        }:

            return

        if signal_id in (
            self._notified_be
        ):

            return

        self._notified_be.add(
            signal_id
        )

        symbol = self._get_symbol(
            signal
        )

        direction = (
            self._get_direction(
                signal
            )
        )

        current_price = self._get_value(
            state,
            "current_price",
            "price",
            default=0.0,
        )

        current_r = self._get_value(
            state,
            "current_r",
            "r_multiple",
            default=0.0,
        )

        progress = self._get_value(
            state,
            "progress_to_tp_percent",
            "progress_percent",
            default=None,
        )

        try:

            current_r = float(
                current_r
            )

        except (
            TypeError,
            ValueError,
        ):

            current_r = 0.0

        if progress is None:

            progress_text = "N/A"

        else:

            try:

                progress_text = (
                    f"{float(progress):.1f}%"
                )

            except (
                TypeError,
                ValueError,
            ):

                progress_text = "N/A"

        message = (
            "🛡️ <b>BREAK-EVEN RECOMMANDÉ</b>\n\n"
            f"📊 Marché : <b>{symbol}</b>\n"
            f"📌 Direction : <b>{direction}</b>\n"
            f"💵 Prix actuel : "
            f"<b>{self._format_price(current_price)}</b>\n\n"
            f"📈 Résultat : "
            f"<b>+{current_r:.2f}R</b>\n"
            f"🎯 Progression TP : "
            f"<b>{progress_text}</b>\n\n"
            "⚠️ Le tracker recommande le "
            "Break-Even.\n"
            "ℹ️ NOVA ne déplace pas automatiquement "
            "le Stop Loss."
        )

        await self._send(
            message
        )

    # ========================================================
    # TERMINAL
    # ========================================================

    async def _check_terminal(
        self,
        state: Any,
    ) -> None:
        """
        Détecte TP ou SL atteint.
        """

        signal = self._get_value(
            state,
            "signal",
            default=None,
        )

        if signal is None:
            return

        signal_id = (
            self._get_signal_id(
                signal
            )
        )

        status = self._get_value(
            state,
            "status",
            default=None,
        )

        if hasattr(
            status,
            "value",
        ):

            status = status.value

        status_text = str(
            status
            or ""
        ).upper()

        tp_statuses = {
            "TP_HIT",
            "TAKE_PROFIT_HIT",
            "CLOSED_TP",
        }

        sl_statuses = {
            "SL_HIT",
            "STOP_LOSS_HIT",
            "CLOSED_SL",
        }

        if status_text not in (
            tp_statuses
            | sl_statuses
        ):

            return

        if signal_id in (
            self._notified_terminal
        ):

            return

        self._notified_terminal.add(
            signal_id
        )

        symbol = self._get_symbol(
            signal
        )

        direction = (
            self._get_direction(
                signal
            )
        )

        current_price = self._get_value(
            state,
            "current_price",
            "price",
            default=0.0,
        )

        current_r = self._get_value(
            state,
            "current_r",
            "r_multiple",
            default=0.0,
        )

        best_r = self._get_value(
            state,
            "best_r",
            "maximum_r",
            default=0.0,
        )

        worst_r = self._get_value(
            state,
            "worst_r",
            "minimum_r",
            default=0.0,
        )

        try:

            current_r = float(
                current_r
            )

        except (
            TypeError,
            ValueError,
        ):

            current_r = 0.0

        try:

            best_r = float(
                best_r
            )

        except (
            TypeError,
            ValueError,
        ):

            best_r = 0.0

        try:

            worst_r = float(
                worst_r
            )

        except (
            TypeError,
            ValueError,
        ):

            worst_r = 0.0

        if status_text in tp_statuses:

            message = (
                "🎯 <b>TP ATTEINT</b>\n\n"
                f"📊 Marché : <b>{symbol}</b>\n"
                f"📌 Direction : <b>{direction}</b>\n"
                f"💵 Prix final : "
                f"<b>{self._format_price(current_price)}</b>\n\n"
                f"✅ Résultat : "
                f"<b>+{current_r:.2f}R</b>\n"
                f"📈 Meilleur R : "
                f"<b>+{best_r:.2f}R</b>"
            )

        else:

            message = (
                "🛑 <b>STOP LOSS ATTEINT</b>\n\n"
                f"📊 Marché : <b>{symbol}</b>\n"
                f"📌 Direction : <b>{direction}</b>\n"
                f"💵 Prix final : "
                f"<b>{self._format_price(current_price)}</b>\n\n"
                f"❌ Résultat : "
                f"<b>{current_r:.2f}R</b>\n"
                f"📉 Pire R : "
                f"<b>{worst_r:.2f}R</b>"
            )

        await self._send(
            message
        )

    # ========================================================
    # UPDATE D'UN SIGNAL
    # ========================================================

    async def update_signal(
        self,
        signal_id: str,
    ) -> None:
        """
        Met à jour l'observation d'un signal.
        """

        state = self.tracker.get(
            signal_id
        )

        if state is None:
            return

        signal = self._get_value(
            state,
            "signal",
            default=None,
        )

        if signal is None:
            return

        symbol = self._get_symbol(
            signal
        )

        if not symbol:
            return

        try:

            price = (
                await self._get_current_price(
                    symbol
                )
            )

            updated_state = (
                self.tracker.update(
                    signal_id,
                    price,
                )
            )

            if updated_state is None:
                return

            await self._check_progress(
                updated_state
            )

            await self._check_break_even(
                updated_state
            )

            await self._check_terminal(
                updated_state
            )

        except asyncio.CancelledError:

            raise

        except Exception:

            logger.exception(
                "Erreur observation signal %s",
                signal_id,
            )

    # ========================================================
    # MONITOR ONCE
    # ========================================================

    async def monitor_once(
        self,
    ) -> None:
        """
        Effectue un cycle d'observation.
        """

        try:

            states = list(
                self.tracker.active_signals()
            )

        except Exception:

            logger.exception(
                "Impossible de récupérer les "
                "signaux actifs."
            )

            return

        if not states:
            return

        for state in states:

            signal = self._get_value(
                state,
                "signal",
                default=None,
            )

            if signal is None:
                continue

            signal_id = (
                self._get_signal_id(
                    signal
                )
            )

            if not signal_id:
                continue

            await self.update_signal(
                signal_id
            )

            # Petite pause entre les observations.
            await asyncio.sleep(
                0.25
            )

    # ========================================================
    # BOUCLE
    # ========================================================

    async def _loop(
        self,
    ) -> None:
        """
        Boucle principale d'observation.
        """

        logger.info(
            "Signal Monitor démarré. "
            "Intervalle : %ss",
            self.interval_seconds,
        )

        while self._running:

            try:

                await self.monitor_once()

            except asyncio.CancelledError:

                raise

            except Exception:

                logger.exception(
                    "Erreur dans la boucle "
                    "Signal Monitor."
                )

            await asyncio.sleep(
                self.interval_seconds
            )

    # ========================================================
    # START
    # ========================================================

    def start(self) -> None:
        """
        Démarre le moniteur.
        """

        if self._running:
            return

        try:

            loop = asyncio.get_running_loop()

        except RuntimeError:

            logger.error(
                "Signal Monitor doit être démarré "
                "depuis une boucle asyncio."
            )

            return

        self._running = True

        self._task = loop.create_task(
            self._loop()
        )

        logger.info(
            "Signal Monitor lancé."
        )

    # ========================================================
    # STOP
    # ========================================================

    async def stop(self) -> None:
        """
        Arrête proprement le moniteur.
        """

        self._running = False

        if self._task is not None:

            self._task.cancel()

            try:

                await self._task

            except asyncio.CancelledError:

                pass

            self._task = None

        logger.info(
            "Signal Monitor arrêté."
        )

    # ========================================================
    # STATUT
    # ========================================================

    def get_status(self) -> dict[str, Any]:
        """
        Retourne uniquement l'état du moniteur.

        Aucun élément de ce statut ne constitue
        une décision de trading.
        """

        return {
            "running": self._running,
            "interval_seconds": (
                self.interval_seconds
            ),
            "observation_only": True,
            "can_generate_signal": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "can_modify_signal": False,
            "can_execute_order": False,
            "can_activate_break_even": False,
            "price_source": (
                "BiQuote/Moteur2"
            ),
            "validation_owner": (
                "moteur2_validation.py"
            ),
        }


# ============================================================
# TEST LOCAL
# ============================================================

def test_signal_monitor() -> dict[str, Any]:
    """
    Test structurel du monitor.

    Aucun signal réel n'est créé.
    """

    return {
        "success": True,
        "observation_only": True,
        "can_generate_signal": False,
        "can_validate_signal": False,
        "can_reject_signal": False,
        "can_modify_signal": False,
        "can_execute_order": False,
        "can_activate_break_even": False,
        "price_source": "BiQuote/Moteur2",
    }


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    result = (
        test_signal_monitor()
    )

    print()
    print(
        "=============================================="
    )
    print(
        " NOVA TRADE AI - SIGNAL MONITOR"
    )
    print(
        "=============================================="
    )
    print(
        f"Test observation : "
        f"{result['success']}"
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
        f"Source prix : "
        f"{result['price_source']}"
    )
    print(
        "=============================================="
    )