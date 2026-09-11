"""
NOVA TRADE AI — ENGINE 2
moteur2.py

ORCHESTRATEUR PRINCIPAL — ENGINE 2

Actif :
    XAUUSD uniquement

Source marché :
    BiQuote uniquement

Architecture :

    BiQuote
        ↓
    Stream / Cache
        ↓
    Cartographie marché
        ↓
    Zones importantes
        ↓
    Contexte
        ↓
    Confluences
        ↓
    Détection des setups
        ↓
    Risk Engine
        ↓
    Confirmation M5 / M1
        ↓
    Score informatif
        ↓
    Validation technique
        ↓
    DECISION ENGINE
        ↓
    BUY / SELL / WAIT
        ↓
    Anti-Spam
        ↓
    Signal
        ↓
    Telegram / couche supérieure

PHILOSOPHIE :

    Le moteur ne fonctionne PAS comme une checklist rigide.

    Le Decision Engine est l'autorité stratégique.

    Le score est informatif.
    Le RR est informatif.
    M5/M1 sont informatifs.
    Les zones sont informatives.
    Les confluences sont informatives.
    La validation technique protège contre les impossibilités.

    Aucun quota de signaux.
    Aucun signal forcé.
    Aucun minimum de signaux.
    Plusieurs signaux distincts sont autorisés.

    Le Risk Engine construit Entry / SL / TP.
    Le Decision Engine décide BUY / SELL / WAIT.
    L'Anti-Spam protège contre les doublons.
    Le moteur ne fait pas d'exécution automatique.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ============================================================================
# IMPORTS
# ============================================================================

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
from moteur2_decision import Moteur2Decision
from moteur2_antispam import Moteur2AntiSpam


# ============================================================================
# CONSTANTES
# ============================================================================

ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"

SYMBOL = "XAUUSD"

TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)

# Timeframes indispensables pour le raisonnement principal.
PRIMARY_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
)

# Timeframes secondaires.
SECONDARY_TIMEFRAMES = (
    "M5",
    "M1",
)

REFERENCE_SCORE = 60.0
REFERENCE_RR = 3.0

DECISION_BUY = "BUY"
DECISION_SELL = "SELL"
DECISION_WAIT = "WAIT"

logger = logging.getLogger("NOVA_ENGINE_2")


# ============================================================================
# CLASSE PRINCIPALE
# ============================================================================

class Moteur2:
    """
    Orchestrateur principal du moteur 2.

    Le moteur orchestre les modules mais ne prend pas lui-même
    la décision stratégique.

    La décision stratégique appartient exclusivement à :

        moteur2_decision.py
    """

    def __init__(
        self,
        symbol: str = SYMBOL,
    ) -> None:

        self.symbol = (
            str(symbol)
            .strip()
            .upper()
            .replace("/", "")
        )

        if self.symbol != SYMBOL:
            raise ValueError(
                "Engine 2 fonctionne uniquement sur XAUUSD."
            )

        # --------------------------------------------------------------------
        # SOURCE DE DONNÉES
        # --------------------------------------------------------------------

        self.biquote = BiQuoteClient()

        self.stream = BiQuoteStream(
            symbol=self.symbol,
            on_tick=self._on_tick,
        )

        self.cache = Moteur2Cache(
            client=self.biquote,
            symbol=self.symbol,
        )

        # --------------------------------------------------------------------
        # MOTEURS D'ANALYSE
        # --------------------------------------------------------------------

        self.marche = Moteur2Marche()

        self.zones = Moteur2Zones()

        self.contexte = Moteur2Contexte()

        self.confluences = Moteur2Confluences()

        self.setups = Moteur2Setups()

        # --------------------------------------------------------------------
        # PLAN DE RISQUE
        # --------------------------------------------------------------------

        self.risk = Moteur2Risk()

        # --------------------------------------------------------------------
        # CONFIRMATION
        # --------------------------------------------------------------------

        self.confirmation = Moteur2Confirmation()

        # --------------------------------------------------------------------
        # SCORE INFORMATIF
        # --------------------------------------------------------------------

        self.score = Moteur2Score()

        # --------------------------------------------------------------------
        # VALIDATION TECHNIQUE
        # --------------------------------------------------------------------

        self.validation = Moteur2Validation()

        # --------------------------------------------------------------------
        # CERVEAU STRATÉGIQUE
        # --------------------------------------------------------------------

        self.decision = Moteur2Decision(
            reference_score=REFERENCE_SCORE,
            reference_rr=REFERENCE_RR,
        )

        # --------------------------------------------------------------------
        # PROTECTION ANTI-SPAM
        # --------------------------------------------------------------------

        self.antispam = Moteur2AntiSpam()

        # --------------------------------------------------------------------
        # ÉTAT
        # --------------------------------------------------------------------

        self.running = False

        self.initialized = False

        self.latest_tick: Optional[Any] = None

        self.last_analysis: Optional[Dict[str, Any]] = None

        self.analysis_lock = asyncio.Lock()

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

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

        result = function(
            *args,
            **kwargs,
        )

        if inspect.isawaitable(result):
            return await result

        return result

    @staticmethod
    def _normalize_direction(
        direction: Any,
    ) -> Optional[str]:

        if direction is None:
            return None

        value = (
            str(direction)
            .strip()
            .upper()
        )

        aliases = {
            "LONG": "BUY",
            "HAUSSIER": "BUY",
            "HAUSSIERE": "BUY",
            "BULLISH": "BUY",
            "UP": "BUY",

            "SHORT": "SELL",
            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BEARISH": "SELL",
            "DOWN": "SELL",
        }

        value = aliases.get(
            value,
            value,
        )

        if value in {
            DECISION_BUY,
            DECISION_SELL,
        }:
            return value

        return None

    @staticmethod
    def _float(
        value: Any,
        default: Optional[float] = None,
    ) -> Optional[float]:

        try:
            if value is None:
                return default

            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return default

    # ========================================================================
    # TICK LIVE
    # ========================================================================

    async def _on_tick(
        self,
        tick: Any,
    ) -> None:

        self.latest_tick = tick

        try:

            await self._call(
                self.cache.update_tick,
                tick,
            )

        except Exception as exc:

            logger.exception(
                "Erreur mise à jour tick BiQuote : %s",
                exc,
            )

    # ========================================================================
    # INITIALISATION
    # ========================================================================

    async def initialiser(
        self,
    ) -> Dict[str, Any]:

        try:

            await self._call(
                self.cache.refresh_all
            )

            self.initialized = True

            return {
                "success": True,
                "engine": ENGINE_NAME,
                "symbol": self.symbol,
                "source": "BiQuote",
                "timeframes": list(
                    TIMEFRAMES
                ),
            }

        except Exception as exc:

            self.initialized = False

            logger.exception(
                "Échec initialisation Engine 2."
            )

            return {
                "success": False,
                "engine": ENGINE_NAME,
                "symbol": self.symbol,
                "error": str(exc),
            }

    async def rafraichir_cache(
        self,
    ) -> Any:

        return await self._call(
            self.cache.refresh_all
        )

    # ========================================================================
    # DONNÉES
    # ========================================================================

    def obtenir_donnees(
        self,
    ) -> Dict[str, Any]:

        donnees: Dict[str, Any] = {}

        for timeframe in TIMEFRAMES:

            try:

                donnees[timeframe] = (
                    self.cache.get_closed_candles(
                        timeframe
                    )
                )

            except TypeError:

                donnees[timeframe] = (
                    self.cache.get_closed_candles(
                        timeframe=timeframe
                    )
                )

            except Exception as exc:

                logger.warning(
                    "Données indisponibles %s : %s",
                    timeframe,
                    exc,
                )

                donnees[timeframe] = None

        return donnees

    def verifier_donnees_principales(
        self,
        donnees: Dict[str, Any],
    ) -> List[str]:

        return [
            timeframe
            for timeframe in PRIMARY_TIMEFRAMES
            if not donnees.get(timeframe)
        ]

    # ========================================================================
    # CARTOGRAPHIE
    # ========================================================================

    async def analyser_marche(
        self,
        donnees: Dict[str, Any],
    ) -> Any:

        return await self._call(
            self.marche.cartographier_marche,
            donnees,
        )

    # ========================================================================
    # ZONES
    # ========================================================================

    async def analyser_zones(
        self,
        cartographie: Any,
        current_price: float,
    ) -> Any:

        return await self._call(
            self.zones.analyser,
            cartographie,
            current_price,
        )

    # ========================================================================
    # CONTEXTE
    # ========================================================================

    async def analyser_contexte(
        self,
        donnees: Dict[str, Any],
        zones: Any,
    ) -> Any:

        return await self._call(
            self.contexte.analyser,
            donnees,
            zones,
        )

    # ========================================================================
    # CONFLUENCES
    # ========================================================================

    async def analyser_confluences(
        self,
        donnees: Dict[str, Any],
        zones: Any,
        contexte: Any,
        cartographie: Any,
    ) -> Any:

        return await self._call(
            self.confluences.analyser,
            donnees,
            zones,
            contexte,
            cartographie,
        )

    # ========================================================================
    # SETUPS
    # ========================================================================

    async def analyser_setups(
        self,
        zones: Any,
        confluences: Any,
        contexte: Any,
        donnees: Dict[str, Any],
    ) -> Any:

        return await self._call(
            self.setups.analyser,
            zones,
            confluences,
            contexte,
            donnees,
        )

    # ========================================================================
    # RISK
    # ========================================================================

    async def analyser_risque(
        self,
        setups: Any,
        zones: Any,
        donnees: Dict[str, Any],
        current_price: float,
    ) -> Any:

        return await self._call(
            self.risk.analyser_setups,
            setups,
            zones,
            donnees,
            current_price,
        )

    # ========================================================================
    # CONFIRMATION
    # ========================================================================

    async def analyser_confirmation(
        self,
        setup: Any,
        donnees: Dict[str, Any],
        risk_plan: Any,
    ) -> Any:

        return await self._call(
            self.confirmation.analyser,
            setup,
            donnees,
            risk_plan,
        )

    # ========================================================================
    # SCORE
    # ========================================================================

    async def calculer_score(
        self,
        setup: Any,
        zones: Any,
        contexte: Any,
        confluences: Any,
        confirmation: Any,
        risk_plan: Any,
    ) -> Any:

        return await self._call(
            self.score.analyser,
            setup=setup,
            zones=zones,
            context=contexte,
            confluences=confluences,
            confirmation=confirmation,
            risk_plan=risk_plan,
        )

    # ========================================================================
    # VALIDATION TECHNIQUE
    # ========================================================================

    async def valider(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        contexte: Any,
        confluences: Any,
    ) -> Any:

        return await self._call(
            self.validation.valider,
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            contexte=contexte,
            confluences=confluences,
        )

    # ========================================================================
    # EXTRACTION DES SETUPS
    # ========================================================================

    @staticmethod
    def _extraire_setups(
        setups_result: Any,
    ) -> List[Any]:

        if setups_result is None:
            return []

        if isinstance(
            setups_result,
            dict,
        ):

            setups = (
                setups_result.get("setups")
                or setups_result.get(
                    "detected_setups"
                )
                or setups_result.get(
                    "opportunities"
                )
                or []
            )

            if isinstance(
                setups,
                (list, tuple),
            ):
                return list(setups)

            if setups:
                return [setups]

            return []

        if isinstance(
            setups_result,
            (list, tuple),
        ):
            return list(setups_result)

        return [setups_result]

    # ========================================================================
    # EXTRACTION DES PLANS DE RISQUE
    # ========================================================================

    @staticmethod
    def _extraire_risk_plans(
        risk_result: Any,
    ) -> List[Any]:

        if risk_result is None:
            return []

        if isinstance(
            risk_result,
            dict,
        ):

            plans = (
                risk_result.get("plans")
                or risk_result.get(
                    "risk_plans"
                )
                or risk_result.get(
                    "valid_plans"
                )
                or risk_result.get(
                    "results"
                )
                or []
            )

            if isinstance(
                plans,
                (list, tuple),
            ):
                return list(plans)

            if plans:
                return [plans]

            return []

        if isinstance(
            risk_result,
            (list, tuple),
        ):
            return list(risk_result)

        return [risk_result]

    # ========================================================================
    # TROUVER LE PLAN DE RISQUE D'UN SETUP
    # ========================================================================

    def _trouver_risk_plan(
        self,
        setup: Any,
        index: int,
        risk_plans: List[Any],
    ) -> Any:

        setup_id = self._get(
            setup,
            "setup_id",
        )

        if setup_id is None:

            setup_id = self._get(
                setup,
                "id",
            )

        if setup_id is not None:

            setup_id = str(
                setup_id
            )

            for candidate in risk_plans:

                candidate_id = self._get(
                    candidate,
                    "setup_id",
                )

                if candidate_id is None:
                    candidate_id = self._get(
                        candidate,
                        "id",
                    )

                if (
                    candidate_id is not None
                    and str(candidate_id)
                    == setup_id
                ):
                    return candidate

        if index < len(risk_plans):

            return risk_plans[index]

        return None

    # ========================================================================
    # CONSTRUCTION DU SIGNAL
    # ========================================================================

    def _construire_signal(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        validation: Any,
        decision_result: Any,
        antispam: Any,
    ) -> Dict[str, Any]:

        setup_id = (
            self._get(
                setup,
                "setup_id",
            )
            or self._get(
                setup,
                "id",
            )
            or self._get(
                antispam,
                "setup_id",
            )
            or "SETUP"
        )

        direction = (
            self._get(
                decision_result,
                "decision",
            )
            or self._get(
                setup,
                "direction",
            )
        )

        direction = self._normalize_direction(
            direction
        )

        entry = self._float(
            self._get(
                risk_plan,
                "entry",
            )
        )

        sl = self._float(
            self._get(
                risk_plan,
                "sl",
            )
        )

        tp1 = self._float(
            self._get(
                risk_plan,
                "tp1",
            )
        )

        tp2 = self._float(
            self._get(
                risk_plan,
                "tp2",
            )
        )

        tp3 = self._float(
            self._get(
                risk_plan,
                "tp3",
            )
        )

        rr = self._float(
            self._get(
                risk_plan,
                "primary_rr",
            )
        )

        if rr is None:

            rr = self._float(
                self._get(
                    risk_plan,
                    "rr",
                )
            )

        if rr is None:

            rr = self._float(
                self._get(
                    risk_plan,
                    "rr_tp1",
                )
            )

        score = self._float(
            self._get(
                score_result,
                "score",
            )
        )

        confidence = self._float(
            self._get(
                decision_result,
                "confidence",
            ),
            0.0,
        )

        quality = self._get(
            decision_result,
            "quality",
            "NEUTRAL",
        )

        priority = self._get(
            decision_result,
            "priority",
            "NORMAL",
        )

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        signal_id = (
            f"{setup_id}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        )

        return {
            "signal_id": signal_id,

            "engine": ENGINE_NAME,

            "symbol": self.symbol,

            "direction": direction,

            "decision": direction,

            "confidence": confidence,

            "priority": priority,

            "quality": quality,

            "setup_id": str(
                setup_id
            ),

            "setup_type": self._get(
                setup,
                "setup_type",
                "UNKNOWN",
            ),

            "entry": entry,

            "sl": sl,

            "tp1": tp1,

            "tp2": tp2,

            "tp3": tp3,

            "rr": rr,

            "score": score,

            "timestamp": timestamp,

            "risk_plan": risk_plan,

            "confirmation": confirmation,

            "validation": validation,

            "decision_result": (
                decision_result.to_dict()
                if hasattr(
                    decision_result,
                    "to_dict",
                )
                else decision_result
            ),

            "antispam": antispam,

            "metadata": {
                "decision_owner":
                    "moteur2_decision.py",

                "risk_engine_decides_trade":
                    False,

                "score_is_blocking":
                    False,

                "rr_is_blocking":
                    False,

                "m5_is_blocking":
                    False,

                "m1_is_blocking":
                    False,

                "forced_signal":
                    False,

                "signal_quota":
                    None,

                "auto_execution":
                    False,

                "entry_source":
                    "moteur2_risk.py",

                "sl_source":
                    "moteur2_risk.py",

                "tp_source":
                    "moteur2_risk.py",

                "decision_source":
                    "moteur2_decision.py",

                "signal_builder":
                    "moteur2.py",
            },
        }

    # ========================================================================
    # TRAITEMENT D'UN SETUP
    # ========================================================================

    async def traiter_setup(
        self,
        setup: Any,
        risk_plan: Any,
        zones: Any,
        contexte: Any,
        confluences: Any,
        donnees: Dict[str, Any],
        market_intelligence: Any = None,
    ) -> Dict[str, Any]:

        # --------------------------------------------------------------------
        # 1. CONFIRMATION
        # --------------------------------------------------------------------

        try:

            confirmation = (
                await self.analyser_confirmation(
                    setup,
                    donnees,
                    risk_plan,
                )
            )

        except Exception as exc:

            logger.exception(
                "Erreur confirmation setup : %s",
                exc,
            )

            confirmation = {
                "status": "UNAVAILABLE",
                "confirmed": False,
                "error": str(exc),
            }

        # --------------------------------------------------------------------
        # 2. SCORE INFORMATIF
        # --------------------------------------------------------------------

        try:

            score_result = (
                await self.calculer_score(
                    setup=setup,
                    zones=zones,
                    contexte=contexte,
                    confluences=confluences,
                    confirmation=confirmation,
                    risk_plan=risk_plan,
                )
            )

        except Exception as exc:

            logger.exception(
                "Erreur score setup : %s",
                exc,
            )

            score_result = {
                "score": None,
                "quality": "UNAVAILABLE",
                "error": str(exc),
            }

        # --------------------------------------------------------------------
        # 3. VALIDATION TECHNIQUE
        # --------------------------------------------------------------------

        try:

            validation = await self.valider(
                setup=setup,
                risk_plan=risk_plan,
                confirmation=confirmation,
                score_result=score_result,
                contexte=contexte,
                confluences=confluences,
            )

        except Exception as exc:

            logger.exception(
                "Erreur validation setup : %s",
                exc,
            )

            validation = {
                "validated": False,
                "valid": False,
                "status": "TECHNICAL_ERROR",
                "reason": str(exc),
                "blockers": [
                    str(exc)
                ],
                "warnings": [],
            }

        # --------------------------------------------------------------------
        # 4. DECISION ENGINE
        #
        # C'est ici que le cerveau stratégique reçoit toutes les informations.
        # --------------------------------------------------------------------

        try:

            decision_result = (
                self.decision.analyser(
                    setup=setup,
                    contexte=contexte,
                    zones=zones,
                    structure=self._get(
                        contexte,
                        "structure",
                    ),
                    confluences=confluences,
                    risk_plan=risk_plan,
                    score_result=score_result,
                    validation_result=validation,
                    confirmation_result=confirmation,
                    market_intelligence=(
                        market_intelligence
                        if market_intelligence
                        is not None
                        else None
                    ),
                )
            )

        except Exception as exc:

            logger.exception(
                "Erreur Decision Engine : %s",
                exc,
            )

            return {
                "status": "DECISION_ERROR",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": DECISION_WAIT,
                "decision_result": {
                    "decision": DECISION_WAIT,
                    "confidence": 0.0,
                    "error": str(exc),
                },
                "signal": None,
            }

        decision = str(
            self._get(
                decision_result,
                "decision",
                DECISION_WAIT,
            )
        ).upper()

        confidence = self._float(
            self._get(
                decision_result,
                "confidence",
            ),
            0.0,
        )

        # --------------------------------------------------------------------
        # 5. WAIT
        # --------------------------------------------------------------------

        if decision == DECISION_WAIT:

            return {
                "status": "WAIT",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": decision,
                "decision_confidence": confidence,
                "decision_result": decision_result,
                "signal": None,
            }

        # --------------------------------------------------------------------
        # 6. PROTECTION : SEULEMENT BUY / SELL
        # --------------------------------------------------------------------

        if decision not in {
            DECISION_BUY,
            DECISION_SELL,
        }:

            return {
                "status": "WAIT",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": DECISION_WAIT,
                "decision_confidence": confidence,
                "decision_result": decision_result,
                "signal": None,
            }

        # --------------------------------------------------------------------
        # 7. ANTI-SPAM
        #
        # L'Anti-Spam ne décide pas.
        # Il vérifie seulement si le signal peut être publié.
        # --------------------------------------------------------------------

        try:

            antispam = self.antispam.verifier(
                setup=setup,
                risk_plan=risk_plan,
                validation=validation,
                decision=decision,
            )

        except TypeError:

            # Compatibilité avec une ancienne signature.
            try:

                antispam = self.antispam.verifier(
                    setup=setup,
                    risk_plan=risk_plan,
                    validation=validation,
                )

            except Exception as exc:

                logger.exception(
                    "Erreur Anti-Spam : %s",
                    exc,
                )

                return {
                    "status": "ANTISPAM_ERROR",
                    "setup": setup,
                    "risk": risk_plan,
                    "confirmation": confirmation,
                    "score": score_result,
                    "validation": validation,
                    "decision": decision,
                    "decision_result": decision_result,
                    "error": str(exc),
                    "signal": None,
                }

        except Exception as exc:

            logger.exception(
                "Erreur Anti-Spam : %s",
                exc,
            )

            return {
                "status": "ANTISPAM_ERROR",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": decision,
                "decision_result": decision_result,
                "error": str(exc),
                "signal": None,
            }

        allowed = bool(
            self._get(
                antispam,
                "allowed",
                False,
            )
        )

        if not allowed:

            return {
                "status": "ANTISPAM_BLOCKED",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": decision,
                "decision_result": decision_result,
                "antispam": antispam,
                "signal": None,
            }

        # --------------------------------------------------------------------
        # 8. CONSTRUCTION DU SIGNAL
        # --------------------------------------------------------------------

        signal = self._construire_signal(
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            validation=validation,
            decision_result=decision_result,
            antispam=antispam,
        )

        # --------------------------------------------------------------------
        # 9. ENREGISTREMENT
        # --------------------------------------------------------------------

        try:

            try:

                self.antispam.enregistrer_signal(
                    setup=setup,
                    risk_plan=risk_plan,
                    setup_id=self._get(
                        antispam,
                        "setup_id",
                    ),
                    decision=decision,
                )

            except TypeError:

                # Compatibilité ancienne signature.
                self.antispam.enregistrer_signal(
                    setup=setup,
                    risk_plan=risk_plan,
                    setup_id=self._get(
                        antispam,
                        "setup_id",
                    ),
                )

        except Exception as exc:

            logger.warning(
                "Signal construit mais enregistrement "
                "Anti-Spam impossible : %s",
                exc,
            )

        # --------------------------------------------------------------------
        # 10. SIGNAL PRÊT
        # --------------------------------------------------------------------

        return {
            "status": "SIGNAL_READY",

            "setup": setup,

            "risk": risk_plan,

            "confirmation": confirmation,

            "score": score_result,

            "validation": validation,

            "decision": decision,

            "decision_confidence": confidence,

            "decision_result": decision_result,

            "antispam": antispam,

            "signal": signal,
        }

    # ========================================================================
    # ANALYSE COMPLÈTE
    # ========================================================================

    async def analyser(
        self,
    ) -> Dict[str, Any]:

        async with self.analysis_lock:

            try:

                # ------------------------------------------------------------
                # RAFRAÎCHISSEMENT
                # ------------------------------------------------------------

                await self.rafraichir_cache()

                # ------------------------------------------------------------
                # PRIX LIVE
                # ------------------------------------------------------------

                current_price = (
                    self.cache.get_current_price()
                )

                if current_price is None:

                    return {
                        "status": "NO_PRICE",

                        "symbol": self.symbol,

                        "reason":
                            "Aucun prix live BiQuote disponible.",
                    }

                # ------------------------------------------------------------
                # DONNÉES
                # ------------------------------------------------------------

                donnees = (
                    self.obtenir_donnees()
                )

                missing_primary = (
                    self.verifier_donnees_principales(
                        donnees
                    )
                )

                if missing_primary:

                    return {
                        "status":
                            "INSUFFICIENT_PRIMARY_DATA",

                        "symbol":
                            self.symbol,

                        "missing_timeframes":
                            missing_primary,
                    }

                # M5/M1 ne sont PAS bloquants.
                missing_secondary = [
                    tf
                    for tf in SECONDARY_TIMEFRAMES
                    if not donnees.get(tf)
                ]

                # ------------------------------------------------------------
                # CARTOGRAPHIE
                # ------------------------------------------------------------

                cartographie = (
                    await self.analyser_marche(
                        donnees
                    )
                )

                # ------------------------------------------------------------
                # ZONES
                # ------------------------------------------------------------

                zones = (
                    await self.analyser_zones(
                        cartographie,
                        current_price,
                    )
                )

                # ------------------------------------------------------------
                # CONTEXTE
                # ------------------------------------------------------------

                contexte = (
                    await self.analyser_contexte(
                        donnees,
                        zones,
                    )
                )

                # ------------------------------------------------------------
                # CONFLUENCES
                # ------------------------------------------------------------

                confluences = (
                    await self.analyser_confluences(
                        donnees,
                        zones,
                        contexte,
                        cartographie,
                    )
                )

                # ------------------------------------------------------------
                # SETUPS
                # ------------------------------------------------------------

                setups_result = (
                    await self.analyser_setups(
                        zones,
                        confluences,
                        contexte,
                        donnees,
                    )
                )

                setups = (
                    self._extraire_setups(
                        setups_result
                    )
                )

                if not setups:

                    result = {
                        "status": "NO_SETUP",

                        "symbol": self.symbol,

                        "current_price":
                            current_price,

                        "cartographie":
                            cartographie,

                        "zones":
                            zones,

                        "contexte":
                            contexte,

                        "confluences":
                            confluences,

                        "setups": [],

                        "results": [],

                        "signals": [],

                        "missing_secondary_timeframes":
                            missing_secondary,
                    }

                    self.last_analysis = result

                    return result

                # ------------------------------------------------------------
                # RISK PLANS
                # ------------------------------------------------------------

                risk_result = (
                    await self.analyser_risque(
                        setups,
                        zones,
                        donnees,
                        current_price,
                    )
                )

                risk_plans = (
                    self._extraire_risk_plans(
                        risk_result
                    )
                )

                # ------------------------------------------------------------
                # TRAITEMENT DE TOUS LES SETUPS
                #
                # IMPORTANT :
                # aucun break après le premier signal.
                # ------------------------------------------------------------

                results: List[
                    Dict[str, Any]
                ] = []

                for index, setup in enumerate(
                    setups
                ):

                    risk_plan = (
                        self._trouver_risk_plan(
                            setup,
                            index,
                            risk_plans,
                        )
                    )

                    if risk_plan is None:

                        results.append({
                            "status":
                                "NO_RISK_PLAN",

                            "setup":
                                setup,

                            "decision":
                                DECISION_WAIT,

                            "signal":
                                None,
                        })

                        continue

                    try:

                        processed = (
                            await self.traiter_setup(
                                setup=setup,
                                risk_plan=risk_plan,
                                zones=zones,
                                contexte=contexte,
                                confluences=confluences,
                                donnees=donnees,
                                market_intelligence=(
                                    cartographie
                                ),
                            )
                        )

                        results.append(
                            processed
                        )

                    except Exception as exc:

                        logger.exception(
                            "Erreur traitement setup : %s",
                            exc,
                        )

                        results.append({
                            "status":
                                "SETUP_ERROR",

                            "setup":
                                setup,

                            "error":
                                str(exc),

                            "decision":
                                DECISION_WAIT,

                            "signal":
                                None,
                        })

                # ------------------------------------------------------------
                # EXTRACTION DES RÉSULTATS
                # ------------------------------------------------------------

                ready = [
                    item
                    for item in results
                    if item.get(
                        "status"
                    ) == "SIGNAL_READY"
                ]

                waiting = [
                    item
                    for item in results
                    if item.get(
                        "status"
                    ) == "WAIT"
                ]

                blocked = [
                    item
                    for item in results
                    if item.get(
                        "status"
                    ) in {
                        "ANTISPAM_BLOCKED",
                        "NO_RISK_PLAN",
                        "SETUP_ERROR",
                        "ANTISPAM_ERROR",
                        "DECISION_ERROR",
                    }
                ]

                # ------------------------------------------------------------
                # TRI PAR CONFIANCE
                # ------------------------------------------------------------

                ready.sort(
                    key=lambda item: (
                        self._float(
                            item.get(
                                "decision_confidence"
                            ),
                            0.0,
                        )
                        or 0.0
                    ),
                    reverse=True,
                )

                # ------------------------------------------------------------
                # SIGNALS
                # ------------------------------------------------------------

                signals = [
                    item.get("signal")
                    for item in ready
                    if item.get(
                        "signal"
                    ) is not None
                ]

                # ------------------------------------------------------------
                # STATUT GLOBAL
                # ------------------------------------------------------------

                if ready:

                    overall_status = (
                        "SIGNAL_READY"
                    )

                elif waiting:

                    overall_status = "WAIT"

                else:

                    overall_status = (
                        "ANALYZED"
                    )

                # ------------------------------------------------------------
                # RÉSULTAT FINAL
                # ------------------------------------------------------------

                result = {

                    "status":
                        overall_status,

                    "engine":
                        ENGINE_NAME,

                    "symbol":
                        self.symbol,

                    "source":
                        "BiQuote",

                    "current_price":
                        current_price,

                    "cartographie":
                        cartographie,

                    "zones":
                        zones,

                    "contexte":
                        contexte,

                    "confluences":
                        confluences,

                    "setups":
                        setups,

                    "risk":
                        risk_result,

                    "results":
                        results,

                    "signals":
                        signals,

                    "signal_count":
                        len(signals),

                    "waiting_count":
                        len(waiting),

                    "blocked_count":
                        len(blocked),

                    "missing_secondary_timeframes":
                        missing_secondary,

                    "reference_score":
                        REFERENCE_SCORE,

                    "reference_rr":
                        REFERENCE_RR,

                    "score_is_blocking":
                        False,

                    "rr_is_blocking":
                        False,

                    "m5_is_blocking":
                        False,

                    "m1_is_blocking":
                        False,

                    "multiple_signals_allowed":
                        True,

                    "signal_quota":
                        None,

                    "forced_signal":
                        False,

                    "decision_owner":
                        "moteur2_decision.py",

                    "auto_execution":
                        False,
                }

                self.last_analysis = result

                logger.info(
                    "Engine 2 terminé : "
                    "status=%s signals=%s waits=%s",
                    overall_status,
                    len(signals),
                    len(waiting),
                )

                return result

            except Exception as exc:

                logger.exception(
                    "Erreur générale Engine 2 : %s",
                    exc,
                )

                result = {
                    "status":
                        "ENGINE_ERROR",

                    "engine":
                        ENGINE_NAME,

                    "symbol":
                        self.symbol,

                    "error":
                        str(exc),

                    "signals":
                        [],
                }

                self.last_analysis = result

                return result

    # ========================================================================
    # STREAM
    # ========================================================================

    async def demarrer_stream(
        self,
    ) -> None:

        await self._call(
            self.stream.start
        )

    # ========================================================================
    # RUN
    # ========================================================================

    async def run(
        self,
        analyse_interval_seconds: int = 10,
    ) -> None:

        if not self.initialized:

            init = (
                await self.initialiser()
            )

            if not init.get(
                "success",
                False,
            ):

                raise RuntimeError(
                    "Impossible d'initialiser Engine 2."
                )

        self.running = True

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

    # ========================================================================
    # STOP
    # ========================================================================

    async def stop(
        self,
    ) -> None:

        self.running = False

        try:

            result = self.stream.stop()

            if inspect.isawaitable(
                result
            ):

                await result

        except Exception as exc:

            logger.warning(
                "Erreur arrêt stream : %s",
                exc,
            )

    # ========================================================================
    # STATUS
    # ========================================================================

    def get_status(
        self,
    ) -> Dict[str, Any]:

        try:

            cache_status = (
                self.cache.get_status()
            )

        except Exception:

            cache_status = {}

        try:

            antispam_status = (
                self.antispam.get_status()
            )

        except Exception:

            antispam_status = {}

        try:

            decision_status = (
                self.decision.get_status()
            )

        except Exception:

            decision_status = {}

        return {

            "engine":
                ENGINE_NAME,

            "module":
                "moteur2",

            "symbol":
                self.symbol,

            "source":
                "BiQuote",

            "running":
                self.running,

            "initialized":
                self.initialized,

            "current_price":
                self.cache.get_current_price(),

            "timeframes":
                list(TIMEFRAMES),

            "primary_timeframes":
                list(PRIMARY_TIMEFRAMES),

            "secondary_timeframes":
                list(SECONDARY_TIMEFRAMES),

            "reference_score":
                REFERENCE_SCORE,

            "reference_rr":
                REFERENCE_RR,

            "score_blocking":
                False,

            "rr_blocking":
                False,

            "m5_blocking":
                False,

            "m1_blocking":
                False,

            "multiple_signals_allowed":
                True,

            "signal_quota":
                None,

            "forced_signals":
                False,

            "auto_execution":
                False,

            "decision_owner":
                "moteur2_decision.py",

            "cache":
                cache_status,

            "decision":
                decision_status,

            "antispam":
                antispam_status,

            "last_analysis":
                self.last_analysis,
        }


# ============================================================================
# RACCOURCI XAUUSD
# ============================================================================

async def analyser_xauusd() -> Dict[str, Any]:

    moteur = Moteur2()

    try:

        init = (
            await moteur.initialiser()
        )

        if not init.get(
            "success",
            False,
        ):

            return init

        return await moteur.analyser()

    finally:

        await moteur.stop()


# ============================================================================
# MAIN
# ============================================================================

async def main() -> None:

    moteur = Moteur2()

    try:

        init = (
            await moteur.initialiser()
        )

        print("=" * 70)
        print(
            "NOVA TRADE AI - ENGINE 2"
        )
        print(
            "SOURCE : BiQuote"
        )
        print(
            "SYMBOL : XAUUSD"
        )
        print(
            "DECISION : moteur2_decision.py"
        )
        print("=" * 70)

        print(init)

        if not init.get(
            "success",
            False,
        ):

            return

        result = (
            await moteur.analyser()
        )

        print()
        print("RESULTAT :")
        print(result)

    finally:

        await moteur.stop()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":

    asyncio.run(main())