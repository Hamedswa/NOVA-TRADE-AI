"""
NOVA TRADE AI - MOTEUR 2
Orchestrateur principal.

ENGINE 2 = XAU/USD uniquement
SOURCE = BiQuote uniquement

Pipeline :

BiQuote
   ↓
Cache
   ↓
Cartographie du marché
   ↓
Zones importantes
   ↓
Contexte
   ↓
Confluences
   ↓
Setup
   ↓
Risk
   ↓
Confirmation M5/M1
   ↓
Score
   ↓
Validation
   ↓
Anti-spam
   ↓
Signal final

IMPORTANT :
- Aucun BOS
- Aucun CHoCH
- Aucun Order Block
- Aucun FVG
- Aucun calcul Groq
- Aucun signal forcé
- RR minimum = 2
- M5/M1 servent au timing
- La validation reste déterministe
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, Optional

from biquote_client import BiQuoteClient
from biquote_stream import BiQuoteStream

from moteur2_cache import Moteur2Cache
from moteur2_marche import Moteur2Marche
from moteur2_zones import Moteur2Zones
from moteur2_contexte import Moteur2Contexte
from moteur2_confluences import Moteur2Confluences
from moteur2_setups import Moteur2Setups
from moteur2_risk import Moteur2Risk
from moteur2_confirmation import Moteur2Confirmation
from moteur2_score import Moteur2Score
from moteur2_validation import Moteur2Validation
from moteur2_antispam import Moteur2AntiSpam
from moteur2_signal import Moteur2Signal


# ============================================================
# CONFIGURATION
# ============================================================

SYMBOL = "XAUUSD"

TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)

ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger("NOVA_ENGINE_2")


# ============================================================
# MOTEUR PRINCIPAL
# ============================================================

class Moteur2:
    """
    Orchestrateur principal du moteur 2.

    Cette classe ne remplace pas les modules spécialisés.
    Elle coordonne leur exécution.
    """

    def __init__(
        self,
        symbol: str = SYMBOL,
    ):
        self.symbol = (
            symbol.strip().upper().replace("/", "")
        )

        if self.symbol != "XAUUSD":
            raise ValueError(
                "Engine 2 fonctionne uniquement sur XAUUSD."
            )

        # ----------------------------------------------------
        # SOURCE DE DONNÉES
        # ----------------------------------------------------

        self.biquote = BiQuoteClient()

        self.stream = BiQuoteStream(
            symbol=self.symbol,
            on_tick=self._on_tick,
        )

        # ----------------------------------------------------
        # MODULES
        # ----------------------------------------------------

        self.cache = Moteur2Cache(
            client=self.biquote,
            symbol=self.symbol,
        )

        self.marche = Moteur2Marche()
        self.zones = Moteur2Zones()
        self.contexte = Moteur2Contexte()
        self.confluences = Moteur2Confluences()
        self.setups = Moteur2Setups()
        self.risk = Moteur2Risk()
        self.confirmation = Moteur2Confirmation()
        self.score = Moteur2Score()
        self.validation = Moteur2Validation()
        self.antispam = Moteur2AntiSpam()
        self.signal = Moteur2Signal()

        # ----------------------------------------------------
        # ÉTAT
        # ----------------------------------------------------

        self.running = False
        self.initialized = False

        self.latest_tick: Optional[Any] = None
        self.last_analysis: Optional[Dict[str, Any]] = None

        self.analysis_lock = asyncio.Lock()

    # ========================================================
    # UTILITAIRES
    # ========================================================

    @staticmethod
    def _get(
        data: Any,
        key: str,
        default: Any = None,
    ) -> Any:

        if data is None:
            return default

        if isinstance(data, dict):
            return data.get(key, default)

        return getattr(
            data,
            key,
            default,
        )

    @staticmethod
    async def _call(
        function: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Permet d'utiliser aussi bien des fonctions normales
        que des fonctions async.
        """

        result = function(
            *args,
            **kwargs,
        )

        if inspect.isawaitable(result):
            return await result

        return result

    # ========================================================
    # TICK LIVE
    # ========================================================

    async def _on_tick(
        self,
        tick: Any,
    ) -> None:
        """
        Reçoit les ticks continus de BiQuote.

        Le tick live sert au prix actuel.

        IMPORTANT :
        un tick n'est jamais transformé artificiellement
        en bougie M1 clôturée.
        """

        self.latest_tick = tick

        try:
            result = self.cache.update_tick(
                tick
            )

            if inspect.isawaitable(result):
                await result

        except Exception as exc:
            logger.exception(
                "Erreur mise à jour tick : %s",
                exc,
            )

    # ========================================================
    # INITIALISATION
    # ========================================================

    async def initialiser(self) -> Dict[str, Any]:
        """
        Charge les données historiques nécessaires
        avant la première analyse.
        """

        logger.info(
            "Initialisation Engine 2 : %s",
            self.symbol,
        )

        try:

            await self._call(
                self.cache.refresh_all
            )

            self.initialized = True

            logger.info(
                "Engine 2 initialisé avec succès."
            )

            return {
                "success": True,
                "symbol": self.symbol,
                "timeframes": list(TIMEFRAMES),
                "source": "BiQuote",
            }

        except Exception as exc:

            logger.exception(
                "Échec initialisation Engine 2."
            )

            self.initialized = False

            return {
                "success": False,
                "symbol": self.symbol,
                "error": str(exc),
            }

    # ========================================================
    # RAFRAÎCHISSEMENT CACHE
    # ========================================================

    async def rafraichir_cache(self) -> Any:
        """
        Laisse le cache décider quelles unités de temps
        nécessitent un rafraîchissement selon leurs intervalles.
        """

        return await self._call(
            self.cache.refresh_all
        )

    # ========================================================
    # RÉCUPÉRATION DES DONNÉES
    # ========================================================

    def obtenir_donnees(self) -> Dict[str, Any]:
        """
        Récupère les bougies clôturées nécessaires.
        """

        donnees = {}

        for timeframe in TIMEFRAMES:

            try:

                candles = self.cache.get_closed_candles(
                    timeframe
                )

            except TypeError:

                candles = self.cache.get_closed_candles(
                    timeframe=timeframe
                )

            donnees[timeframe] = candles

        return donnees

    # ========================================================
    # CARTOGRAPHIE
    # ========================================================

    async def analyser_marche(
        self,
        donnees: Dict[str, Any],
    ) -> Any:

        try:
            return await self._call(
                self.marche.cartographier_marche,
                donnees,
            )

        except AttributeError:
            return await self._call(
                self.marche.analyser,
                donnees,
            )

    # ========================================================
    # ZONES
    # ========================================================

    async def analyser_zones(
        self,
        cartographie: Any,
        current_price: float,
    ) -> Any:

        try:
            return await self._call(
                self.zones.detecter_zones,
                cartographie,
                current_price,
            )

        except TypeError:

            return await self._call(
                self.zones.detecter_zones,
                cartographie=cartographie,
                current_price=current_price,
            )

    # ========================================================
    # CONTEXTE
    # ========================================================

    async def analyser_contexte(
        self,
        donnees: Dict[str, Any],
        cartographie: Any,
        zones: Any,
    ) -> Any:

        try:

            return await self._call(
                self.contexte.analyser,
                donnees,
                cartographie,
                zones,
            )

        except TypeError:

            try:

                return await self._call(
                    self.contexte.analyser_contexte,
                    donnees,
                    cartographie,
                    zones,
                )

            except AttributeError:

                return await self._call(
                    self.contexte.analyser,
                    donnees,
                )

    # ========================================================
    # CONFLUENCES
    # ========================================================

    async def analyser_confluences(
        self,
        cartographie: Any,
        zones: Any,
        contexte: Any,
        donnees: Dict[str, Any],
    ) -> Any:

        try:

            return await self._call(
                self.confluences.analyser,
                cartographie,
                zones,
                contexte,
                donnees,
            )

        except AttributeError:

            return await self._call(
                self.confluences.analyser_confluences,
                cartographie,
                zones,
                contexte,
                donnees,
            )

    # ========================================================
    # SETUPS
    # ========================================================

    async def analyser_setups(
        self,
        zones: Any,
        contexte: Any,
        confluences: Any,
        donnees: Dict[str, Any],
    ) -> Any:

        try:

            return await self._call(
                self.setups.analyser_setups,
                zones,
                contexte,
                confluences,
                donnees,
            )

        except AttributeError:

            return await self._call(
                self.setups.analyser,
                zones,
                contexte,
                confluences,
                donnees,
            )

    # ========================================================
    # RISQUE
    # ========================================================

    async def analyser_risque(
        self,
        setups: Any,
        zones: Any,
        donnees: Dict[str, Any],
        current_price: float,
    ) -> Any:

        try:

            return await self._call(
                self.risk.analyser_setups,
                setups,
                zones,
                donnees,
                current_price,
            )

        except AttributeError:

            return await self._call(
                self.risk.analyser,
                setups,
                zones,
                donnees,
                current_price,
            )

    # ========================================================
    # CONFIRMATION
    # ========================================================

    async def analyser_confirmation(
        self,
        setup: Any,
        risk_plan: Any,
        donnees: Dict[str, Any],
    ) -> Any:

        try:

            return await self._call(
                self.confirmation.analyser,
                setup,
                risk_plan,
                donnees,
            )

        except AttributeError:

            return await self._call(
                self.confirmation.confirmer,
                setup,
                risk_plan,
                donnees,
            )

    # ========================================================
    # SCORE
    # ========================================================

    async def calculer_score(
        self,
        setup: Any,
        contexte: Any,
        confluences: Any,
        confirmation: Any,
        risk_plan: Any,
    ) -> Any:

        try:

            return await self._call(
                self.score.calculer_score,
                setup,
                contexte,
                confluences,
                confirmation,
                risk_plan,
            )

        except TypeError:

            return await self._call(
                self.score.calculer_score,
                contexte,
                confluences,
                confirmation,
                risk_plan,
            )

    # ========================================================
    # VALIDATION
    # ========================================================

    async def valider(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        contexte: Any = None,
        confluences: Any = None,
    ) -> Any:

        """
        La validation finale reste déterministe.

        Le score n'est jamais le seul critère.
        """

        try:

            return await self._call(
                self.validation.valider,
                setup,
                risk_plan,
                confirmation,
                score_result,
                contexte,
                confluences,
            )

        except AttributeError:

            return await self._call(
                self.validation.verifier,
                setup,
                risk_plan,
                confirmation,
                score_result,
            )

    # ========================================================
    # ANALYSE D'UN SETUP
    # ========================================================

    async def traiter_setup(
        self,
        setup: Any,
        risk_plan: Any,
        contexte: Any,
        confluences: Any,
        donnees: Dict[str, Any],
    ) -> Optional[Any]:

        # ----------------------------------------------------
        # Confirmation M5/M1
        # ----------------------------------------------------

        confirmation = await self.analyser_confirmation(
            setup,
            risk_plan,
            donnees,
        )

        # ----------------------------------------------------
        # Score
        # ----------------------------------------------------

        score_result = await self.calculer_score(
            setup=setup,
            contexte=contexte,
            confluences=confluences,
            confirmation=confirmation,
            risk_plan=risk_plan,
        )

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------

        validation = await self.valider(
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            contexte=contexte,
            confluences=confluences,
        )

        validated = bool(
            self._get(
                validation,
                "validated",
                False,
            )
        )

        if not validated:

            return {
                "status": "REJECTED",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
            }

        # ----------------------------------------------------
        # Anti-spam
        # ----------------------------------------------------

        antispam = self.antispam.verifier(
            setup=setup,
            risk_plan=risk_plan,
            validation=validation,
        )

        if not antispam.allowed:

            return {
                "status": "ANTISPAM_BLOCKED",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "antispam": antispam,
            }

        # ----------------------------------------------------
        # Construction du signal
        # ----------------------------------------------------

        signal = self.signal.construire_signal(
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            validation=validation,
            antispam_result=antispam,
            setup_id=antispam.setup_id,
        )

        if signal is None:

            return {
                "status": "SIGNAL_NOT_BUILT",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "antispam": antispam,
            }

        # ----------------------------------------------------
        # Enregistrement anti-spam
        # ----------------------------------------------------

        self.antispam.enregistrer_signal(
            setup=setup,
            risk_plan=risk_plan,
            setup_id=antispam.setup_id,
        )

        return {
            "status": "SIGNAL_READY",
            "signal": signal,
            "setup": setup,
            "risk": risk_plan,
            "confirmation": confirmation,
            "score": score_result,
            "validation": validation,
            "antispam": antispam,
        }

    # ========================================================
    # ANALYSE COMPLÈTE
    # ========================================================

    async def analyser(
        self,
    ) -> Dict[str, Any]:

        async with self.analysis_lock:

            logger.info(
                "=========================================="
            )

            logger.info(
                "DÉMARRAGE ANALYSE ENGINE 2 — XAUUSD"
            )

            logger.info(
                "=========================================="
            )

            # ------------------------------------------------
            # 1. CACHE
            # ------------------------------------------------

            await self.rafraichir_cache()

            # ------------------------------------------------
            # 2. PRIX LIVE
            # ------------------------------------------------

            current_price = (
                self.cache.get_current_price()
            )

            if current_price is None:

                return {
                    "status": "NO_PRICE",
                    "reason": (
                        "Aucun prix live BiQuote disponible."
                    ),
                }

            # ------------------------------------------------
            # 3. DONNÉES
            # ------------------------------------------------

            donnees = self.obtenir_donnees()

            # Vérification minimale
            missing = []

            for timeframe in TIMEFRAMES:

                if not donnees.get(timeframe):

                    missing.append(timeframe)

            if missing:

                return {
                    "status": "INSUFFICIENT_DATA",
                    "missing_timeframes": missing,
                }

            # ------------------------------------------------
            # 4. CARTOGRAPHIE
            # ------------------------------------------------

            cartographie = await self.analyser_marche(
                donnees
            )

            # ------------------------------------------------
            # 5. ZONES
            # ------------------------------------------------

            zones = await self.analyser_zones(
                cartographie,
                current_price,
            )

            # ------------------------------------------------
            # 6. CONTEXTE
            # ------------------------------------------------

            contexte = await self.analyser_contexte(
                donnees,
                cartographie,
                zones,
            )

            # ------------------------------------------------
            # 7. CONFLUENCES
            # ------------------------------------------------

            confluences = await self.analyser_confluences(
                cartographie,
                zones,
                contexte,
                donnees,
            )

            # ------------------------------------------------
            # 8. SETUPS
            # ------------------------------------------------

            setups_result = await self.analyser_setups(
                zones,
                contexte,
                confluences,
                donnees,
            )

            # ------------------------------------------------
            # EXTRACTION SETUPS
            # ------------------------------------------------

            setups = setups_result

            if isinstance(
                setups_result,
                dict,
            ):

                setups = setups_result.get(
                    "setups",
                    [],
                )

            if setups is None:
                setups = []

            # ------------------------------------------------
            # AUCUN SETUP
            # ------------------------------------------------

            if not setups:

                result = {
                    "status": "NO_SETUP",
                    "symbol": self.symbol,
                    "current_price": current_price,
                    "cartographie": cartographie,
                    "zones": zones,
                    "contexte": contexte,
                    "confluences": confluences,
                    "setups": [],
                }

                self.last_analysis = result

                logger.info(
                    "Aucun setup intéressant."
                )

                return result

            # ------------------------------------------------
            # 9. RISQUE
            # ------------------------------------------------

            risk_result = await self.analyser_risque(
                setups,
                zones,
                donnees,
                current_price,
            )

            # ------------------------------------------------
            # EXTRACTION RISK PLANS
            # ------------------------------------------------

            risk_plans = risk_result

            if isinstance(
                risk_result,
                dict,
            ):

                risk_plans = risk_result.get(
                    "risk_plans",
                    risk_result.get(
                        "plans",
                        [],
                    ),
                )

            if risk_plans is None:
                risk_plans = []

            # ------------------------------------------------
            # MAPPING SETUP → RISK
            # ------------------------------------------------

            results = []

            for index, setup in enumerate(setups):

                risk_plan = None

                # --------------------------------------------
                # 1. Correspondance par setup_id
                # --------------------------------------------

                setup_id = self._get(
                    setup,
                    "setup_id",
                    None,
                )

                if setup_id:

                    for candidate in risk_plans:

                        candidate_id = self._get(
                            candidate,
                            "setup_id",
                            None,
                        )

                        if (
                            candidate_id
                            and candidate_id == setup_id
                        ):
                            risk_plan = candidate
                            break

                # --------------------------------------------
                # 2. Correspondance par index
                # --------------------------------------------

                if risk_plan is None:

                    if index < len(risk_plans):

                        risk_plan = risk_plans[index]

                # --------------------------------------------
                # Aucun risk plan
                # --------------------------------------------

                if risk_plan is None:

                    results.append({
                        "status": "NO_RISK_PLAN",
                        "setup": setup,
                    })

                    continue

                # --------------------------------------------
                # Traitement complet
                # --------------------------------------------

                result = await self.traiter_setup(
                    setup=setup,
                    risk_plan=risk_plan,
                    contexte=contexte,
                    confluences=confluences,
                    donnees=donnees,
                )

                if result is not None:
                    results.append(result)

            # ------------------------------------------------
            # RÉSULTAT FINAL
            # ------------------------------------------------

            ready_signals = [
                item
                for item in results
                if item.get("status")
                == "SIGNAL_READY"
            ]

            waiting = [
                item
                for item in results
                if item.get("signal") is not None
                and item["signal"].waiting_confirmation
            ]

            result = {
                "status": (
                    "SIGNAL_READY"
                    if ready_signals
                    else (
                        "WAITING_CONFIRMATION"
                        if waiting
                        else "ANALYZED"
                    )
                ),

                "symbol": self.symbol,
                "current_price": current_price,

                "cartographie": cartographie,
                "zones": zones,
                "contexte": contexte,
                "confluences": confluences,

                "setups": setups,
                "risk": risk_result,

                "results": results,

                "signals": [
                    item["signal"]
                    for item in ready_signals
                    if item.get("signal")
                ],
            }

            self.last_analysis = result

            logger.info(
                "Analyse Engine 2 terminée : %s",
                result["status"],
            )

            return result

    # ========================================================
    # START STREAM
    # ========================================================

    async def demarrer_stream(self) -> None:
        """
        Démarre le flux temps réel BiQuote.

        SignalR pousse les ticks en continu.
        """

        logger.info(
            "Connexion au flux BiQuote..."
        )

        await self._call(
            self.stream.start
        )

    # ========================================================
    # BOUCLE PRINCIPALE
    # ========================================================

    async def run(
        self,
        analyse_interval_seconds: int = 10,
    ) -> None:

        if not self.initialized:

            init = await self.initialiser()

            if not init["success"]:

                raise RuntimeError(
                    "Impossible d'initialiser Engine 2."
                )

        self.running = True

        logger.info(
            "Engine 2 démarré."
        )

        # Le flux temps réel tourne en parallèle.
        stream_task = asyncio.create_task(
            self.demarrer_stream()
        )

        try:

            while self.running:

                try:

                    await self.analyser()

                except Exception as exc:

                    logger.exception(
                        "Erreur analyse Engine 2 : %s",
                        exc,
                    )

                await asyncio.sleep(
                    max(
                        1,
                        int(
                            analyse_interval_seconds
                        ),
                    )
                )

        finally:

            self.running = False

            stream_task.cancel()

            try:
                await stream_task
            except asyncio.CancelledError:
                pass

    # ========================================================
    # ARRÊT
    # ========================================================

    async def stop(self) -> None:

        self.running = False

        try:

            result = self.stream.stop()

            if inspect.isawaitable(result):
                await result

        except Exception as exc:

            logger.warning(
                "Erreur arrêt stream : %s",
                exc,
            )

        logger.info(
            "Engine 2 arrêté."
        )

    # ========================================================
    # STATUT
    # ========================================================

    def get_status(self) -> Dict[str, Any]:

        cache_status = {}

        try:

            cache_status = (
                self.cache.get_status()
            )

        except Exception:
            pass

        return {
            "engine": ENGINE_NAME,
            "symbol": self.symbol,

            "source": "BiQuote",

            "running": self.running,
            "initialized": self.initialized,

            "current_price": (
                self.cache.get_current_price()
            ),

            "timeframes": list(
                TIMEFRAMES
            ),

            "cache": cache_status,

            "antispam": (
                self.antispam.get_status()
            ),
        }


# ============================================================
# FONCTION PUBLIQUE
# ============================================================

async def analyser_xauusd() -> Dict[str, Any]:
    """
    Analyse ponctuelle de XAU/USD avec Engine 2.
    """

    moteur = Moteur2()

    try:

        init = await moteur.initialiser()

        if not init["success"]:
            return init

        return await moteur.analyser()

    finally:

        await moteur.stop()


# ============================================================
# TEST LOCAL
# ============================================================

async def main() -> None:

    moteur = Moteur2()

    try:

        print()
        print(
            "=========================================="
        )
        print(
            " NOVA TRADE AI — ENGINE 2"
        )
        print(
            " XAU/USD — BIQUOTE"
        )
        print(
            "=========================================="
        )
        print()

        init = await moteur.initialiser()

        print(
            "Initialisation :",
            init,
        )

        if not init["success"]:
            return

        result = await moteur.analyser()

        print()
        print(
            "=========================================="
        )
        print(
            "RÉSULTAT"
        )
        print(
            "=========================================="
        )

        print(
            "Statut :",
            result.get("status"),
        )

        print(
            "Prix :",
            result.get("current_price"),
        )

        print(
            "Nombre de setups :",
            len(
                result.get(
                    "setups",
                    [],
                )
            ),
        )

        print(
            "Nombre de signaux :",
            len(
                result.get(
                    "signals",
                    [],
                )
            ),
        )

        for signal in result.get(
            "signals",
            [],
        ):

            print()
            print(
                signal.telegram_message
            )

    finally:

        await moteur.stop()


if __name__ == "__main__":

    asyncio.run(main())