"""
NOVA TRADE AI — ENGINE 2
moteur2.py

Orchestrateur Engine 2 multi-actifs.

Actifs : XAUUSD, BTCUSD, EURUSD, GBPUSD.
Source marché : BiQuote uniquement.

Pipeline :
BiQuote → Cache → Cartographie → Zones → Contexte →
Confluences → Setups → Risk → Confirmation M5/M1 →
Score → Validation technique → Decision Engine → Anti-spam → Signal.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional

from biquote_client import BiQuoteClient
from biquote_stream import BiQuoteStream
from moteur2_cache import Moteur2Cache
from moteur2_marche import Moteur2Marche
from moteur2_liquidite import Moteur2Liquidite
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
from moteur2_decision import Moteur2Decision
from moteur2_intelligence import Moteur2Intelligence
from moteur2_radar import Moteur2Radar
from moteur2_scenarios import Moteur2Scenarios
from moteur2_opportunites import Moteur2Opportunites
from moteur2_plan import Moteur2Plan
from moteur2_fondamental import Moteur2Fondamental


SYMBOL = "XAUUSD"

# Les quatre actifs surveillés en permanence par Engine 2.
# L'ordre est volontaire : XAUUSD, BTCUSD, EURUSD, GBPUSD.
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

# Objectif opérationnel : rechercher activement les meilleures
# opportunités de la journée. Ce nombre n'est PAS un quota forcé.
DAILY_SIGNAL_TARGET = 3
MAX_SIGNALS_PER_CYCLE = 3

TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)

ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"

logger = logging.getLogger("NOVA_ENGINE_2")


class Moteur2:

    def __init__(self, symbol: str = SYMBOL) -> None:

        self.symbol = (
            symbol.strip().upper().replace("/", "")
        )

        if self.symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(
                f"Engine 2 ne supporte pas {self.symbol}. "
                f"Symboles supportés : {', '.join(SUPPORTED_SYMBOLS)}."
            )

        self.biquote = BiQuoteClient()

        self.stream = BiQuoteStream(
            symbol=self.symbol,
            on_tick=self._on_tick,
        )

        self.cache = Moteur2Cache(
            client=self.biquote,
            symbol=self.symbol,
        )

        self.marche = Moteur2Marche()
        self.liquidite = Moteur2Liquidite()
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
        self.decision = Moteur2Decision()

        # Couches d'observation et de génération ajoutées à Engine 2.
        # Elles sont descriptives/contributives : aucune ne possède la
        # décision finale.
        self.radar = Moteur2Radar()
        self.intelligence = Moteur2Intelligence(
            reference_score=60.0,
            reference_rr=0.0,
        )
        self.scenarios = Moteur2Scenarios(
            reference_score=60.0,
            reference_rr=0.0,
        )
        self.opportunites = Moteur2Opportunites()
        self.plan = Moteur2Plan()
        self.fondamental = Moteur2Fondamental(
            supported_symbols=SUPPORTED_SYMBOLS,
        )

        self.running = False
        self.initialized = False
        self.latest_tick: Optional[Any] = None
        self.last_analysis: Optional[Dict[str, Any]] = None

        self.analysis_lock = asyncio.Lock()

    # ============================================================
    # OUTILS
    # ============================================================

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
        return getattr(data, key, default)

    @staticmethod
    async def _call(
        function: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:

        result = function(*args, **kwargs)

        if inspect.isawaitable(result):
            return await result

        return result

    @staticmethod
    def _to_dict(data: Any) -> Dict[str, Any]:
        """Normalise les dataclasses/objets des couches descriptives."""
        if data is None:
            return {}
        if isinstance(data, dict):
            return data
        to_dict = getattr(data, "to_dict", None)
        if callable(to_dict):
            try:
                value = to_dict()
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
        return getattr(data, "__dict__", {}) or {}

    @classmethod
    def _technical_plan_to_legacy(cls, plan: Any) -> Optional[Dict[str, Any]]:
        """Adapte un TechnicalPlan au format historique attendu par validation/signal."""
        data = cls._to_dict(plan)
        if not data:
            return None
        targets = data.get("targets") or []
        tp_values = []
        for target in targets:
            value = cls._get(target, "price")
            if value is not None:
                try:
                    tp_values.append(float(value))
                except (TypeError, ValueError):
                    pass
        entry = cls._get(data, "entry")
        sl = cls._get(data, "stop_loss")
        if entry is None or sl is None or not tp_values:
            return None
        try:
            entry = float(entry)
            sl = float(sl)
        except (TypeError, ValueError):
            return None
        rr_values = data.get("rr_values") or []
        primary_rr = data.get("best_informational_rr")
        try:
            primary_rr = float(primary_rr) if primary_rr is not None else None
        except (TypeError, ValueError):
            primary_rr = None
        return {
            "symbol": data.get("symbol"),
            "setup_id": data.get("plan_id") or data.get("opportunity_id") or "PLAN",
            "setup_type": data.get("opportunity_type") or "OPPORTUNITE",
            "direction": data.get("direction"),
            "entry": entry,
            "sl": sl,
            "tp1": tp_values[0] if len(tp_values) > 0 else None,
            "tp2": tp_values[1] if len(tp_values) > 1 else None,
            "tp3": tp_values[2] if len(tp_values) > 2 else None,
            "primary_rr": primary_rr,
            "rr_values": rr_values,
            "rr_is_informational": True,
            "risk_managed_here": False,
            "valid": True,
            "geometry_valid": True,
            "metadata": {
                "technical_plan": data,
                "legacy_alias": True,
            },
        }

    @classmethod
    def _match_plan_for_setup(cls, plans: Any, setup: Any) -> Optional[Dict[str, Any]]:
        items = []
        if isinstance(plans, dict):
            items = (
                plans.get("plans")
                or plans.get("opportunities")
                or plans.get("scenarios")
                or []
            )
        elif isinstance(plans, (list, tuple)):
            items = list(plans)
        direction = str(cls._get(setup, "direction", "")).upper()
        setup_id = str(cls._get(setup, "setup_id", ""))
        for item in items:
            data = cls._to_dict(item)
            if not data:
                continue
            ids = {
                str(data.get("opportunity_id", "")),
                str(data.get("plan_id", "")),
                str(data.get("scenario_id", "")),
                str(data.get("setup_id", "")),
            }
            if setup_id and setup_id in ids:
                return data
        for item in items:
            data = cls._to_dict(item)
            if str(data.get("direction", "")).upper() == direction:
                return data
        return None

    # ============================================================
    # TICK LIVE
    # ============================================================

    async def _on_tick(self, tick: Any) -> None:

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

    # ============================================================
    # INITIALISATION
    # ============================================================

    async def initialiser(self) -> Dict[str, Any]:

        try:

            await self._call(
                self.cache.refresh_all
            )

            self.initialized = True

            return {
                "success": True,
                "symbol": self.symbol,
                "timeframes": list(TIMEFRAMES),
                "source": "BiQuote",
            }

        except Exception as exc:

            self.initialized = False

            logger.exception(
                "Échec initialisation Engine 2."
            )

            return {
                "success": False,
                "symbol": self.symbol,
                "error": str(exc),
            }

    async def rafraichir_cache(self) -> Any:
        return await self._call(
            self.cache.refresh_all
        )

    # ============================================================
    # DONNÉES
    # ============================================================

    def obtenir_donnees(self) -> Dict[str, Any]:

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

        return donnees

    # ============================================================
    # CARTOGRAPHIE
    # ============================================================

    async def analyser_marche(
        self,
        donnees: Dict[str, Any],
    ) -> Any:

        return await self._call(
            self.marche.analyser,
            donnees,
            symbol=self.symbol,
        )

    # ============================================================
    # LIQUIDITÉ
    # ============================================================

    async def analyser_liquidite(
        self,
        cartographie: Any,
        current_price: float,
    ) -> Any:
        """
        Analyse descriptive de la liquidité après la cartographie.

        Cette couche est contributive et non bloquante : elle ne décide
        jamais BUY/SELL et ne remplace aucune validation existante.
        """
        return await self._call(
            self.liquidite.analyser,
            cartographie,
            current_price,
        )

    # ============================================================
    # ZONES
    # ============================================================

    async def analyser_zones(
        self,
        cartographie: Any,
        current_price: float,
        liquidite: Any = None,
    ) -> Any:

        # IMPORTANT : méthode réelle de la classe = analyser()
        return await self._call(
            self.zones.analyser,
            cartographie,
            current_price,
            liquidite,
        )

    # ============================================================
    # CONTEXTE
    # ============================================================

    async def analyser_contexte(
        self,
        donnees: Dict[str, Any],
        zones: Any,
        cartographie: Any = None,
        liquidite: Any = None,
    ) -> Any:

        # Contexte enrichi : données + zones + cartographie + liquidité.
        # Cette couche reste descriptive et non bloquante.
        return await self._call(
            self.contexte.analyser,
            donnees,
            zones,
            symbol=self.symbol,
            cartographie=cartographie,
            liquidite=liquidite,
        )

    # ============================================================
    # CONFLUENCES
    # ============================================================

    async def analyser_confluences(
        self,
        donnees: Dict[str, Any],
        zones: Any,
        contexte: Any,
        cartographie: Any,
        liquidite: Any = None,
    ) -> Any:

        # Confluences enrichies : données + zones + contexte +
        # cartographie + liquidité. Couche descriptive et non bloquante.
        return await self._call(
            self.confluences.analyser,
            donnees,
            zones,
            contexte,
            cartographie,
            symbol=self.symbol,
            liquidity_result=liquidite,
        )

    # ============================================================
    # SETUPS
    # ============================================================

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

    # ============================================================
    # RISK
    # ============================================================

    async def analyser_risque(
        self,
        setups: Any,
        zones: Any,
        donnees: Dict[str, Any],
        current_price: float,
    ) -> Any:

        # Signature réelle :
        # analyser_setups(setups, zones, candles, current_price)
        return await self._call(
            self.risk.analyser_setups,
            setups,
            zones,
            donnees,
            current_price,
        )

    # ============================================================
    # CONFIRMATION
    # ============================================================

    async def analyser_confirmation(
        self,
        setup: Any,
        donnees: Dict[str, Any],
        risk_plan: Any,
    ) -> Any:

        # Signature réelle :
        # analyser(setup, candles, risk_plan)
        return await self._call(
            self.confirmation.analyser,
            setup,
            donnees,
            risk_plan,
        )

    # ============================================================
    # SCORE
    # ============================================================

    async def calculer_score(
        self,
        setup: Any,
        zones: Any,
        contexte: Any,
        confluences: Any,
        confirmation: Any,
        risk_plan: Any,
    ) -> Any:

        # Signature réelle :
        # analyser(setup, zones, context, confluences,
        #          confirmation, risk_plan)
        return await self._call(
            self.score.analyser,
            setup=setup,
            zones=zones,
            context=contexte,
            confluences=confluences,
            confirmation=confirmation,
            risk_plan=risk_plan,
        )

    # ============================================================
    # VALIDATION
    # ============================================================

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

    # ============================================================
    # SETUP COMPLET
    # ============================================================

    async def traiter_setup(
        self,
        setup: Any,
        risk_plan: Any,
        zones: Any,
        contexte: Any,
        confluences: Any,
        donnees: Dict[str, Any],
        cartographie: Any = None,
        liquidite: Any = None,
        opportunite: Any = None,
        hypothese: Any = None,
        scenarios: Any = None,
        fondamental: Any = None,
        technical_plan: Any = None,
    ) -> Dict[str, Any]:

        confirmation = await self.analyser_confirmation(
            setup,
            donnees,
            risk_plan,
        )

        score_result = await self.calculer_score(
            setup=setup,
            zones=zones,
            contexte=contexte,
            confluences=confluences,
            confirmation=confirmation,
            risk_plan=risk_plan,
        )

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

        validation_status = str(
            self._get(
                validation,
                "status",
                "UNKNOWN",
            )
        ).upper()

        # --------------------------------------------------------
        # SETUP NON VALIDÉ
        # --------------------------------------------------------

        if not validated:

            return {
                "status": "REJECTED",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": None,
            }

        # --------------------------------------------------------
        # DECISION ENGINE
        # --------------------------------------------------------
        # Le Decision Engine est le propriétaire de la décision
        # stratégique BUY / SELL / WAIT.
        # Il ne fabrique aucun prix et ne remplace ni Risk, ni Validation.
        # La cartographie sert de structure/marché et la liquidité
        # d'intelligence de marché descriptive.
        try:
            decision_result = await self._call(
                self.decision.analyser,
                setup=setup,
                contexte=contexte,
                zones=zones,
                structure=cartographie,
                confluences=confluences,
                risk_plan=risk_plan,
                score_result=score_result,
                validation_result=validation,
                confirmation_result=confirmation,
                market_intelligence={
                    "cartographie": cartographie,
                    "liquidite": liquidite,
                },
                opportunite=opportunite,
                hypothese=hypothese,
                plan=technical_plan,
                technical_plan=technical_plan,
                scenarios=scenarios,
                fondamental=fondamental,
            )
        except TypeError:
            # Compatibilité avec une version du Decision Engine
            # n'acceptant pas encore tous les champs optionnels.
            decision_result = await self._call(
                self.decision.analyser,
                setup=setup,
                contexte=contexte,
                zones=zones,
                structure=cartographie,
                confluences=confluences,
                risk_plan=risk_plan,
                score_result=score_result,
                validation_result=validation,
                confirmation_result=confirmation,
                opportunite=opportunite,
                hypothese=hypothese,
                plan=technical_plan,
                technical_plan=technical_plan,
                scenarios=scenarios,
                fondamental=fondamental,
            )
        except Exception as exc:
            logger.exception(
                "Decision Engine erreur pour %s: %s",
                self.symbol,
                exc,
            )
            return {
                "status": "DECISION_ENGINE_ERROR",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": None,
                "error": str(exc),
            }

        decision = str(
            self._get(decision_result, "decision", "WAIT")
        ).upper()
        setup_direction = str(
            self._get(setup, "direction", "")
        ).upper()

        if decision not in {"BUY", "SELL", "WAIT"}:
            decision = "WAIT"

        decision_confidence = self._get(
            decision_result, "confidence", None
        )
        logger.info(
            "DECISION ENGINE : %s | setup=%s | decision=%s | confidence=%s",
            self.symbol,
            self._get(setup, "setup_id", "SETUP"),
            decision,
            decision_confidence,
        )

        # Le moteur stratégique doit rester cohérent avec le sens du setup.
        # Une divergence devient WAIT, jamais un retournement artificiel.
        if decision in {"BUY", "SELL"} and setup_direction in {"BUY", "SELL"}:
            if decision != setup_direction:
                return {
                    "status": "DECISION_WAIT",
                    "setup": setup,
                    "risk": risk_plan,
                    "confirmation": confirmation,
                    "score": score_result,
                    "validation": validation,
                    "decision": decision_result,
                    "signal": None,
                }

        if decision == "WAIT":
            return {
                "status": "DECISION_WAIT",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": decision_result,
                "signal": None,
            }

        # --------------------------------------------------------
        # SETUP VALIDÉ MAIS M5/M1 EN ATTENTE
        #
        # IMPORTANT :
        # aucun anti-spam, aucun enregistrement actif,
        # aucun signal Telegram envoyé à ce stade.
        # --------------------------------------------------------

        if validation_status != "READY_FOR_SIGNAL":

            return {
                "status": "WAITING_CONFIRMATION",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": decision_result,
                "signal": None,
            }

        # --------------------------------------------------------
        # ANTI-SPAM UNIQUEMENT AU MOMENT DU SIGNAL
        # --------------------------------------------------------

        antispam = self.antispam.verifier(
            setup=setup,
            risk_plan=risk_plan,
            validation=validation,
        )

        if not bool(
            self._get(
                antispam,
                "allowed",
                False,
            )
        ):

            return {
                "status": "ANTISPAM_BLOCKED",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": decision_result,
                "antispam": antispam,
                "signal": None,
            }

        # --------------------------------------------------------
        # CONSTRUCTION SIGNAL
        # --------------------------------------------------------

        setup_id = self._get(
            antispam,
            "setup_id",
        )

        signal = self.signal.construire_signal(
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            validation=validation,
            antispam_result=antispam,
            setup_id=setup_id,
            decision=decision_result,
            technical_plan=technical_plan,
        )

        if signal is None:

            return {
                "status": "SIGNAL_NOT_BUILT",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "decision": decision_result,
                "antispam": antispam,
                "signal": None,
            }

        # --------------------------------------------------------
        # ENREGISTREMENT APRÈS CONSTRUCTION DU SIGNAL
        # --------------------------------------------------------

        self.antispam.enregistrer_signal(
            setup=setup,
            risk_plan=risk_plan,
            setup_id=setup_id,
        )

        return {
            "status": "SIGNAL_READY",
            "signal": signal,
            "setup": setup,
            "risk": risk_plan,
            "confirmation": confirmation,
            "score": score_result,
            "validation": validation,
            "decision": decision_result,
            "antispam": antispam,
        }

    # ============================================================
    # ANALYSE COMPLÈTE
    # ============================================================

    async def analyser(self) -> Dict[str, Any]:

        async with self.analysis_lock:

            await self.rafraichir_cache()

            # Le cache est déjà lié à self.symbol. On tente néanmoins
            # la forme explicite si une implémentation multi-symboles
            # de Moteur2Cache l'accepte, avec fallback rétrocompatible.
            try:
                current_price = self.cache.get_current_price(self.symbol)
            except TypeError:
                current_price = self.cache.get_current_price()

            if current_price is None:

                return {
                    "status": "NO_PRICE",
                    "reason": (
                        "Aucun prix live BiQuote disponible."
                    ),
                }

            donnees = self.obtenir_donnees()

            missing = [
                tf
                for tf in TIMEFRAMES
                if not donnees.get(tf)
            ]

            if missing:

                return {
                    "status": "INSUFFICIENT_DATA",
                    "missing_timeframes": missing,
                }

            cartographie = await self.analyser_marche(
                donnees
            )

            # Couche liquidité : calculée immédiatement après la
            # cartographie, avant les zones, sans modifier les règles
            # de validation existantes.
            liquidite = await self.analyser_liquidite(
                cartographie,
                current_price,
            )

            zones = await self.analyser_zones(
                cartographie,
                current_price,
                liquidite,
            )

            contexte = await self.analyser_contexte(
                donnees,
                zones,
                cartographie,
                liquidite,
            )

            confluences = await self.analyser_confluences(
                donnees,
                zones,
                contexte,
                cartographie,
                liquidite,
            )

            market_snapshot = {
                "price": current_price,
                "current_price": current_price,
                "timeframes": donnees,
            }

            radar_events = self.radar.surveiller(
                self.symbol,
                market_data=market_snapshot,
                zones=self._to_dict(zones).get("zones", []) if isinstance(self._to_dict(zones), dict) else [],
            )

            intelligence_result = self.intelligence.analyser(
                self.symbol,
                market_data=donnees,
                contexte=self._to_dict(contexte),
                zones=zones,
                structure=self._to_dict(cartographie),
                confluences=confluences,
                events=radar_events,
            )
            intelligence_data = self._to_dict(intelligence_result)

            setups_result = await self.analyser_setups(
                zones,
                confluences,
                contexte,
                donnees,
            )

            if isinstance(setups_result, dict):
                setups = (
                    setups_result.get("setups")
                    or setups_result.get("detected_setups")
                    or []
                )
            elif isinstance(setups_result, (list, tuple)):
                setups = list(setups_result)
            else:
                setups = (
                    [setups_result]
                    if setups_result is not None
                    else []
                )

            scenarios_result = self.scenarios.analyser(
                symbol=self.symbol,
                intelligence=intelligence_data,
                radar_events=radar_events,
                contexte=self._to_dict(contexte),
                zones=zones,
                setups=setups,
            )

            fundamental_result = self.fondamental.analyser(
                self.symbol,
                macro_context={},
                technical_context={
                    "intelligence": intelligence_data,
                    "contexte": self._to_dict(contexte),
                    "cartographie": self._to_dict(cartographie),
                },
            )

            opportunities_result = self.opportunites.analyser(
                symbol=self.symbol,
                intelligence=intelligence_data,
                radar_events=radar_events,
                contexte=contexte,
                zones=zones,
                liquidite=liquidite,
                confluences=confluences,
                scenarios=scenarios_result,
                setups=setups,
                market_data=market_snapshot,
                fundamental=fundamental_result,
            )

            technical_plans_result = self.plan.analyser(
                symbol=self.symbol,
                opportunities=opportunities_result,
                current_price=current_price,
                market_map=self._to_dict(cartographie),
                zones=zones,
            )

            # ----------------------------------------------------------
            # DIAGNOSTIC PIPELINE — OBSERVATION UNIQUEMENT
            # ----------------------------------------------------------
            # Ces logs servent à localiser précisément une éventuelle
            # perte d'opportunités entre Opportunités → Plans → Setups.
            # Ils ne filtrent, ne modifient et ne décident absolument rien.
            raw_opportunities = []
            if isinstance(opportunities_result, dict):
                raw_opportunities = opportunities_result.get("opportunities", [])
            elif isinstance(opportunities_result, (list, tuple)):
                raw_opportunities = list(opportunities_result)

            raw_technical_plans = []
            if isinstance(technical_plans_result, dict):
                raw_technical_plans = technical_plans_result.get("plans", [])
            elif isinstance(technical_plans_result, (list, tuple)):
                raw_technical_plans = list(technical_plans_result)

            def _diagnostic_direction(item: Any) -> str:
                data = self._to_dict(item)
                return str(
                    data.get("direction")
                    or data.get("bias")
                    or data.get("side")
                    or "NEUTRAL"
                ).upper()

            opportunity_directions = [
                _diagnostic_direction(item) for item in raw_opportunities
            ]
            plan_directions = [
                _diagnostic_direction(item) for item in raw_technical_plans
            ]

            global_context = {}
            context_data = self._to_dict(contexte)
            if isinstance(context_data, dict):
                candidate_global = context_data.get("global", {})
                if isinstance(candidate_global, dict):
                    global_context = candidate_global

            logger.info(
                "DIAGNOSTIC PIPELINE : %s | opportunities=%d | technical_plans=%d | classic_setups=%d | "
                "context_direction=%s | context_state=%s | context_regime=%s | context_strength=%s",
                self.symbol,
                len(raw_opportunities),
                len(raw_technical_plans),
                len(setups),
                global_context.get("direction", "N/A"),
                global_context.get("state", "N/A"),
                global_context.get("regime", global_context.get("market_regime", "N/A")),
                global_context.get("strength", global_context.get("trend_strength", "N/A")),
            )

            if raw_opportunities:
                logger.info(
                    "DIAGNOSTIC OPPORTUNITIES : %s | directions=%s | types=%s",
                    self.symbol,
                    opportunity_directions,
                    [
                        self._to_dict(item).get("opportunity_type", "N/A")
                        for item in raw_opportunities
                    ],
                )
            else:
                logger.info(
                    "DIAGNOSTIC OPPORTUNITIES : %s | AUCUNE opportunite generee.",
                    self.symbol,
                )

            if raw_technical_plans:
                logger.info(
                    "DIAGNOSTIC PLANS : %s | directions=%s | ids=%s",
                    self.symbol,
                    plan_directions,
                    [
                        self._to_dict(item).get("plan_id", "N/A")
                        for item in raw_technical_plans
                    ],
                )
            else:
                logger.info(
                    "DIAGNOSTIC PLANS : %s | AUCUN plan technique genere.",
                    self.symbol,
                )

            classic_setups_count = len(setups)

            if not setups:
                # Les opportunités autonomes peuvent exister sans setup
                # historique. On crée uniquement un support technique à
                # partir d'un plan réellement généré ; aucune décision ou
                # signal n'est forcé ici.
                raw_plans = (
                    technical_plans_result.get("plans", [])
                    if isinstance(technical_plans_result, dict)
                    else []
                )
                synthetic_setups = []
                for plan_data in raw_plans:
                    plan_dict = self._to_dict(plan_data)
                    raw_direction = str(plan_dict.get("direction", "")).upper().strip()
                    direction_map = {
                        "HAUSSIER": "BUY",
                        "HAUSSIERE": "BUY",
                        "HAUSSIÈRE": "BUY",
                        "BULLISH": "BUY",
                        "BUY": "BUY",
                        "LONG": "BUY",
                        "BAISSIER": "SELL",
                        "BAISSIERE": "SELL",
                        "BAISSIÈRE": "SELL",
                        "BEARISH": "SELL",
                        "SELL": "SELL",
                        "SHORT": "SELL",
                    }
                    direction = direction_map.get(raw_direction, "")
                    if direction not in {"BUY", "SELL"}:
                        continue
                    synthetic_setups.append({
                        "setup_id": plan_dict.get("plan_id") or plan_dict.get("opportunity_id") or "TECHNICAL_OPPORTUNITY",
                        "setup_type": plan_dict.get("opportunity_type") or "OPPORTUNITE",
                        "symbol": self.symbol,
                        "direction": direction,
                        "source": "moteur2_opportunites.py",
                        "autonomous": True,
                    })
                setups = synthetic_setups

                logger.info(
                    "DIAGNOSTIC SYNTHETIC SETUPS : %s | synthetic_setups=%d | directions=%s",
                    self.symbol,
                    len(synthetic_setups),
                    [
                        self._to_dict(item).get("direction", "N/A")
                        for item in synthetic_setups
                    ],
                )

            logger.info(
                "DIAGNOSTIC FINAL SETUPS : %s | classic=%d | final=%d",
                self.symbol,
                classic_setups_count,
                len(setups),
            )

            if not setups:

                result = {
                    "status": "NO_SETUP",
                    "symbol": self.symbol,
                    "current_price": current_price,
                    "cartographie": cartographie,
                    "liquidite": liquidite,
                    "zones": zones,
                    "contexte": contexte,
                    "confluences": confluences,
                    "intelligence": intelligence_data,
                    "radar": [self._to_dict(item) for item in radar_events],
                    "scenarios": [self._to_dict(item) for item in scenarios_result],
                    "fundamental": fundamental_result,
                    "opportunities": opportunities_result,
                    "technical_plans": technical_plans_result,
                    "setups": [],
                    "results": [],
                    "signals": [],
                }

                self.last_analysis = result
                return result

            risk_result = await self.analyser_risque(
                setups,
                zones,
                donnees,
                current_price,
            )

            if isinstance(risk_result, dict):
                risk_plans = (
                    risk_result.get("plans")
                    or risk_result.get("risk_plans")
                    or risk_result.get("valid_plans")
                    or []
                )
            elif isinstance(risk_result, (list, tuple)):
                risk_plans = list(risk_result)
            else:
                risk_plans = []

            results = []

            for index, setup in enumerate(setups):

                setup_id = self._get(
                    setup,
                    "setup_id",
                )

                risk_plan = None

                if setup_id:

                    for candidate in risk_plans:

                        candidate_id = self._get(
                            candidate,
                            "setup_id",
                        )

                        if (
                            candidate_id
                            and candidate_id == setup_id
                        ):
                            risk_plan = candidate
                            break

                if risk_plan is None and index < len(risk_plans):
                    risk_plan = risk_plans[index]

                technical_plan_data = self._match_plan_for_setup(
                    technical_plans_result,
                    setup,
                )

                # Le nouveau plan technique est prioritaire. L'ancien
                # moteur Risk reste un filet de compatibilité tant que
                # toutes les intégrations externes n'ont pas migré.
                technical_plan_legacy = self._technical_plan_to_legacy(
                    technical_plan_data
                ) if technical_plan_data is not None else None

                if technical_plan_legacy is not None:
                    active_plan = technical_plan_legacy
                else:
                    active_plan = risk_plan

                if active_plan is None:

                    results.append({
                        "status": "NO_TECHNICAL_PLAN",
                        "setup": setup,
                    })

                    continue

                results.append(
                    await self.traiter_setup(
                        setup=setup,
                        risk_plan=active_plan,
                        zones=zones,
                        contexte=contexte,
                        confluences=confluences,
                        donnees=donnees,
                        cartographie=cartographie,
                        liquidite=liquidite,
                        opportunite=self._match_plan_for_setup(opportunities_result, setup),
                        hypothese=self._match_plan_for_setup(scenarios_result, setup),
                        scenarios=scenarios_result,
                        fondamental=fundamental_result,
                        technical_plan=technical_plan_data,
                    )
                )

            ready = [
                item
                for item in results
                if item.get("status") == "SIGNAL_READY"
            ]

            waiting = [
                item
                for item in results
                if item.get("status") == "WAITING_CONFIRMATION"
            ]

            if ready:
                overall_status = "SIGNAL_READY"
            elif waiting:
                overall_status = "WAITING_CONFIRMATION"
            else:
                overall_status = "ANALYZED"

            result = {
                "status": overall_status,
                "symbol": self.symbol,
                "current_price": current_price,
                "cartographie": cartographie,
                "liquidite": liquidite,
                "zones": zones,
                "contexte": contexte,
                "confluences": confluences,
                "intelligence": intelligence_data,
                "radar": [self._to_dict(item) for item in radar_events],
                "scenarios": [self._to_dict(item) for item in scenarios_result],
                "fundamental": fundamental_result,
                "opportunities": opportunities_result,
                "technical_plans": technical_plans_result,
                "setups": setups,
                "risk": risk_result,
                "results": results,
                "signals": [
                    item["signal"]
                    for item in ready
                    if item.get("signal") is not None
                ],
            }

            self.last_analysis = result

            logger.info(
                "Engine 2 terminé : %s",
                overall_status,
            )

            return result

    # ============================================================
    # STREAM
    # ============================================================

    async def demarrer_stream(self) -> None:
        await self._call(
            self.stream.start
        )

    # ============================================================
    # RUN
    # ============================================================

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
                        int(analyse_interval_seconds),
                    )
                )

        finally:

            self.running = False

            stream_task.cancel()

            try:
                await stream_task
            except asyncio.CancelledError:
                pass

    # ============================================================
    # STOP
    # ============================================================

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

    # ============================================================
    # STATUS
    # ============================================================

    def _cache_accepts_symbol_price(self) -> bool:
        """Détecte si get_current_price accepte un symbole explicite."""
        try:
            import inspect as _inspect
            signature = _inspect.signature(self.cache.get_current_price)
            parameters = list(signature.parameters.values())
            return any(
                p.kind in (_inspect.Parameter.POSITIONAL_ONLY,
                           _inspect.Parameter.POSITIONAL_OR_KEYWORD,
                           _inspect.Parameter.VAR_POSITIONAL)
                for p in parameters
            )
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:

        try:
            cache_status = self.cache.get_status()
        except Exception:
            cache_status = {}

        try:
            antispam_status = self.antispam.get_status()
        except Exception:
            antispam_status = {}

        return {
            "engine": ENGINE_NAME,
            "symbol": self.symbol,
            "source": "BiQuote",
            "running": self.running,
            "initialized": self.initialized,
            "current_price": (
                self.cache.get_current_price(self.symbol)
                if self._cache_accepts_symbol_price()
                else self.cache.get_current_price()
            ),
            "timeframes": list(TIMEFRAMES),
            "liquidity_layer": True,
            "liquidity_blocking": False,
            "cache": cache_status,
            "antispam": antispam_status,
        }


async def analyser_xauusd() -> Dict[str, Any]:

    moteur = Moteur2()

    try:

        init = await moteur.initialiser()

        if not init["success"]:
            return init

        return await moteur.analyser()

    finally:
        await moteur.stop()


async def main() -> None:
    """Point d'entrée principal : analyse globale des 4 actifs."""
    moteur = obtenir_moteur2_global()
    try:
        init = await moteur.initialiser()
        print(init)
        if not init.get("success", False):
            return
        result = await moteur.analyser()
        print(result)
    finally:
        await moteur.stop()


# ============================================================================
# NOVA ENGINE 2 — ORCHESTRATEUR GLOBAL MULTI-ACTIFS
# ============================================================================

class Moteur2Global:
    """Orchestrateur global multi-actifs d'Engine 2."""

    def __init__(self, symbols=None, max_signals: int = 3, parallel: bool = True,
                 analysis_interval_seconds: int = 900) -> None:
        from moteur2_multi_actifs import Moteur2MultiActifs
        from moteur2_ranking import Moteur2Ranking

        if symbols is None:
            symbols = list(SUPPORTED_SYMBOLS)

        self.symbols = tuple(
            str(symbol).strip().upper().replace('/', '').replace(' ', '')
            .replace('-', '').replace('_', '')
            for symbol in symbols
        )
        invalid = [s for s in self.symbols if s not in SUPPORTED_SYMBOLS]
        if invalid:
            raise ValueError(f"Symboles non supportés : {', '.join(invalid)}")

        self.max_signals = min(
            MAX_SIGNALS_PER_CYCLE,
            max(1, int(max_signals)),
        )
        self.parallel = bool(parallel)
        self.analysis_interval_seconds = max(1, int(analysis_interval_seconds))
        self.multi_actifs = Moteur2MultiActifs(
            symbols=self.symbols,
            analysis_interval_seconds=self.analysis_interval_seconds,
            parallel=self.parallel,
        )
        self.ranking = Moteur2Ranking(max_signals=self.max_signals)
        self.initialized = False
        self.running = False
        self.last_cycle: Optional[Dict[str, Any]] = None
        self.last_ranking: Optional[Dict[str, Any]] = None
        self.analysis_lock = asyncio.Lock()

    async def initialiser(self) -> Dict[str, Any]:
        try:
            result = await self.multi_actifs.initialiser()
            initialized_symbols = result.get('initialized_symbols', [])
            self.initialized = bool(initialized_symbols)
            return {
                'success': self.initialized,
                'engine': ENGINE_NAME,
                'module': 'moteur2_global',
                'symbols': list(self.symbols),
                'initialized_symbols': initialized_symbols,
                'failed_symbols': result.get('failed_symbols', []),
                'max_signals': self.max_signals,
                'analysis_interval_seconds': self.analysis_interval_seconds,
                'forced_signal': False,
                'ranking_is_decision_maker': False,
                'quality_is_blocking': False,
                'results': result.get('results', {}),
            }
        except Exception as exc:
            logger.exception('Erreur initialisation Engine 2 Global : %s', exc)
            self.initialized = False
            return {'success': False, 'engine': ENGINE_NAME,
                    'module': 'moteur2_global', 'symbols': list(self.symbols),
                    'error': str(exc)}

    async def demarrer_streams(self) -> Dict[str, Any]:
        try:
            return await self.multi_actifs.demarrer_streams()
        except Exception as exc:
            logger.exception('Erreur démarrage streams globaux : %s', exc)
            return {'success': False, 'error': str(exc)}

    async def analyser(self) -> Dict[str, Any]:
        async with self.analysis_lock:
            if not self.initialized:
                init = await self.initialiser()
                if not init.get('success', False):
                    return {'status': 'INITIALIZATION_ERROR', 'engine': ENGINE_NAME,
                            'signals': [], 'error': init.get('error', 'Initialisation impossible.')}
            try:
                cycle = await self.multi_actifs.analyser_tous()
                self.last_cycle = cycle
                ranking = self.ranking.ranker(cycle)
                self.last_ranking = ranking
                signals = ranking.get('signals', [])
                return {
                    'status': 'SIGNALS_AVAILABLE' if signals else 'NO_GLOBAL_SIGNAL',
                    'engine': ENGINE_NAME,
                    'module': 'moteur2_global',
                    'symbols': list(self.symbols),
                    'max_signals': self.max_signals,
                    'daily_signal_target': DAILY_SIGNAL_TARGET,
                    'signals': signals,
                    'signal_count': len(signals),
                    'candidates_count': ranking.get('candidate_count', 0),
                    'selected_count': ranking.get('selected_count', 0),
                    'cycle': cycle,
                    'ranking': ranking,
                    'forced_signal': False,
                    'quality_is_blocking': False,
                    'ranking_is_decision_maker': False,
                    'auto_execution': False,
                    'decision_owner': 'moteur2_decision.py',
                    'risk_owner': 'moteur2_risk.py',
                    'validation_owner': 'moteur2_validation.py',
                    'ranking_owner': 'moteur2_ranking.py',
                }
            except Exception as exc:
                logger.exception('Erreur analyse Engine 2 Global : %s', exc)
                return {'status': 'GLOBAL_ENGINE_ERROR', 'engine': ENGINE_NAME,
                        'module': 'moteur2_global', 'signals': [], 'signal_count': 0,
                        'error': str(exc), 'forced_signal': False, 'auto_execution': False}

    async def analyser_symbol(self, symbol: str) -> Dict[str, Any]:
        """Analyse l'actif demandé via le moteur global multi-actifs.

        Cette méthode est une compatibilité pour l'interface Telegram :
        le moteur global analyse toujours le portefeuille des 4 actifs, puis
        retourne uniquement le résultat de l'actif demandé.
        Elle ne modifie ni la stratégie, ni le ranking, ni les critères de validation.
        """
        normalized = (
            str(symbol).strip().upper()
            .replace('/', '')
            .replace(' ', '')
            .replace('-', '')
            .replace('_', '')
        )

        if normalized not in self.symbols:
            return {
                'status': 'UNSUPPORTED_SYMBOL',
                'engine': ENGINE_NAME,
                'symbol': normalized,
                'signals': [],
                'error': f'Symbole non supporté : {normalized}',
            }

        global_result = await self.analyser()
        cycle = global_result.get('cycle') or self.last_cycle or {}
        results = cycle.get('results') or {}

        # Compatibilité avec les deux formes possibles de stockage.
        result = results.get(normalized)
        if result is None:
            for key, value in results.items():
                key_normalized = (
                    str(key).strip().upper()
                    .replace('/', '')
                    .replace(' ', '')
                    .replace('-', '')
                    .replace('_', '')
                )
                if key_normalized == normalized:
                    result = value
                    break

        if result is None:
            return {
                'status': 'SYMBOL_RESULT_UNAVAILABLE',
                'engine': ENGINE_NAME,
                'symbol': normalized,
                'signals': [],
                'global_status': global_result.get('status'),
                'error': f'Aucun résultat disponible pour {normalized}.',
            }

        return result

    def obtenir_top_signaux(self) -> List[Any]:
        if not self.last_ranking:
            return []
        return self.last_ranking.get('signals', [])

    def get_status(self) -> Dict[str, Any]:
        try:
            multi_status = self.multi_actifs.get_status()
        except Exception as exc:
            multi_status = {'status': 'ERROR', 'error': str(exc)}
        try:
            ranking_status = self.ranking.get_status()
        except Exception as exc:
            ranking_status = {'status': 'ERROR', 'error': str(exc)}
        return {
            'engine': ENGINE_NAME, 'module': 'moteur2_global',
            'symbols': list(self.symbols), 'symbol_count': len(self.symbols),
            'initialized': self.initialized, 'running': self.running,
            'max_signals': self.max_signals,
            'daily_signal_target': DAILY_SIGNAL_TARGET,
            'analysis_interval_seconds': self.analysis_interval_seconds,
            'forced_signal': False, 'quality_is_blocking': False,
            'ranking_is_decision_maker': False, 'auto_execution': False,
            'multi_actifs': multi_status, 'ranking': ranking_status,
            'last_signal_count': len(self.obtenir_top_signaux()),
        }

    async def run(self, analysis_interval_seconds: Optional[int] = None,
                  start_streams: bool = True) -> None:
        if not self.initialized:
            init = await self.initialiser()
            if not init.get('success', False):
                raise RuntimeError('Impossible d\'initialiser Engine 2 Global.')
        self.running = True
        interval = self.analysis_interval_seconds if analysis_interval_seconds is None else max(1, int(analysis_interval_seconds))
        stream_task = None
        try:
            if start_streams:
                stream_task = asyncio.create_task(self.demarrer_streams())
            while self.running:
                try:
                    await self.analyser()
                except Exception as exc:
                    logger.exception('Erreur cycle global : %s', exc)
                await asyncio.sleep(interval)
        finally:
            self.running = False
            if stream_task is not None:
                stream_task.cancel()
                try:
                    await stream_task
                except asyncio.CancelledError:
                    pass

    async def stop(self) -> None:
        self.running = False
        try:
            await self.multi_actifs.stop()
        except Exception as exc:
            logger.warning('Erreur arrêt Engine 2 Global : %s', exc)


# ============================================================================
# INSTANCE GLOBALE LAZY
# ============================================================================

_moteur2_global: Optional[Moteur2Global] = None


def obtenir_moteur2_global() -> Moteur2Global:
    global _moteur2_global
    if _moteur2_global is None:
        _moteur2_global = Moteur2Global(
            symbols=SUPPORTED_SYMBOLS,
            max_signals=3,
            parallel=True,
            analysis_interval_seconds=900,
        )
    return _moteur2_global


async def initialiser_engine2_global() -> Dict[str, Any]:
    return await obtenir_moteur2_global().initialiser()


async def demarrer_streams_engine2_global() -> Dict[str, Any]:
    return await obtenir_moteur2_global().demarrer_streams()


async def analyser_engine2_global() -> Dict[str, Any]:
    return await obtenir_moteur2_global().analyser()


async def arreter_engine2_global() -> None:
    await obtenir_moteur2_global().stop()


def statut_engine2_global() -> Dict[str, Any]:
    return obtenir_moteur2_global().get_status()


def top_signaux_engine2_global() -> List[Any]:
    return obtenir_moteur2_global().obtenir_top_signaux()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    asyncio.run(main())
