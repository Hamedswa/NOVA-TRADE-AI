"""
NOVA TRADE AI — ENGINE 2
moteur2.py

ORCHESTRATEUR PRINCIPAL

Architecture :

    BiQuote
        ↓
    Stream / Cache
        ↓
    Market Radar
        ↓
    Market Cartography
        ↓
    Zones
        ↓
    Context
        ↓
    Confluences
        ↓
    Market Intelligence
        ↓
    Scenarios / Opportunities
        ↓
    Setups
        ↓
    Risk / Safety Plan
        ↓
    Confirmation M5/M1
        ↓
    Informative Score
        ↓
    Technical Validation
        ↓
    DECISION ENGINE
        ↓
    BUY / SELL / WAIT
        ↓
    AntiSpam
        ↓
    Signal Builder
        ↓
    Telegram

PRINCIPES :

    - Decision Engine = autorité stratégique.
    - Intelligence = observation adaptative.
    - Radar = surveillance des changements.
    - Scenarios = possibilités de marché.
    - Setups = détection d'opportunités.
    - Risk = construction Entry / SL / TP.
    - Validation = sécurité technique.
    - Confirmation M5/M1 = information de timing.
    - Score = information.
    - RR = information.
    - AntiSpam = protection technique.
    - Signal Builder = assemblage final.

Aucun quota de signaux.
Aucun signal forcé.
Plusieurs opportunités possibles.
Pas d'exécution automatique.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from biquote_client import BiQuoteClient
from biquote_stream import BiQuoteStream
from moteur2_cache import Moteur2Cache

from moteur2_radar import Moteur2Radar
from moteur2_marche import Moteur2Marche
from moteur2_zones import Moteur2Zones
from moteur2_contexte import Moteur2Contexte
from moteur2_confluences import Moteur2Confluences
from moteur2_intelligence import Moteur2Intelligence
from moteur2_scenarios import Moteur2Scenarios
from moteur2_setups import Moteur2Setups

from moteur2_risk import Moteur2Risk
from moteur2_confirmation import Moteur2Confirmation
from moteur2_score import Moteur2Score
from moteur2_validation import Moteur2Validation
from moteur2_decision import Moteur2Decision
from moteur2_antispam import Moteur2AntiSpam
from moteur2_signal import Moteur2Signal


# ============================================================================
# CONSTANTES
# ============================================================================

ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"

SYMBOL = "XAUUSD"

# ---------------------------------------------------------------------------
# ACTIFS SUPPORTÉS PAR ENGINE 2
# ---------------------------------------------------------------------------

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "GBPUSD",
    "EURUSD",
)

TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)

PRIMARY_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
)

SECONDARY_TIMEFRAMES = (
    "M5",
    "M1",
)

REFERENCE_SCORE = 60.0
REFERENCE_RR = 3.0

DECISION_BUY = "BUY"
DECISION_SELL = "SELL"
DECISION_WAIT = "WAIT"

logger = logging.getLogger(
    "NOVA_ENGINE_2"
)


# ============================================================================
# MOTEUR PRINCIPAL
# ============================================================================

class Moteur2:

    def __init__(
        self,
        symbol: str = SYMBOL,
    ) -> None:

        self.symbol = (
            str(symbol)
            .strip()
            .upper()
            .replace("/", "")
            .replace(" ", "")
        )

        # --------------------------------------------------------------------
        # VALIDATION DU SYMBOLE
        # --------------------------------------------------------------------

        if self.symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(
                "Symbole non supporté par Engine 2 : "
                f"{self.symbol}. "
                f"Symboles autorisés : "
                f"{', '.join(SUPPORTED_SYMBOLS)}"
            )

        # --------------------------------------------------------------------
        # SOURCE
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
        # OBSERVATION DU MARCHÉ
        # --------------------------------------------------------------------

        self.radar = Moteur2Radar()

        self.marche = Moteur2Marche()

        self.zones = Moteur2Zones()

        self.contexte = Moteur2Contexte()

        self.confluences = Moteur2Confluences()

        self.intelligence = Moteur2Intelligence(
            reference_score=REFERENCE_SCORE,
            reference_rr=REFERENCE_RR,
        )

        self.scenarios = Moteur2Scenarios(
            reference_score=REFERENCE_SCORE,
            reference_rr=REFERENCE_RR,
        )

        self.setups = Moteur2Setups()

        # --------------------------------------------------------------------
        # PLAN DE RISQUE
        # --------------------------------------------------------------------

        self.risk = Moteur2Risk()

        # --------------------------------------------------------------------
        # TIMING
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
        # ANTI-SPAM
        # --------------------------------------------------------------------

        self.antispam = Moteur2AntiSpam()

        # --------------------------------------------------------------------
        # CONSTRUCTEUR SIGNAL
        # --------------------------------------------------------------------

        self.signal_builder = Moteur2Signal()

        # --------------------------------------------------------------------
        # ÉTAT
        # --------------------------------------------------------------------

        self.running = False
        self.initialized = False

        self.latest_tick: Optional[Any] = None

        self.last_analysis: Optional[
            Dict[str, Any]
        ] = None

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
            return data.get(
                key,
                default,
            )

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

    @staticmethod
    def _direction(
        value: Any,
    ) -> Optional[str]:

        if value is None:
            return None

        value = (
            str(value)
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

        if value in (
            "BUY",
            "SELL",
        ):
            return value

        return None

    @staticmethod
    def _as_dict(
        value: Any,
    ) -> Any:

        if value is None:
            return None

        if hasattr(
            value,
            "to_dict",
        ):

            try:
                return value.to_dict()
            except Exception:
                pass

        if isinstance(
            value,
            dict,
        ):
            return value

        if hasattr(
            value,
            "__dict__",
        ):
            return value.__dict__

        return value

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
    # CONSTRUCTION MARKET DATA
    # ========================================================================

    def _construire_market_data(
        self,
        donnees: Dict[str, Any],
        current_price: float,
        cartographie: Any = None,
    ) -> Dict[str, Any]:

        data: Dict[str, Any] = {
            "symbol": self.symbol,
            "price": current_price,
            "current_price": current_price,
            "timeframes": {},
        }

        for timeframe in TIMEFRAMES:

            candles = donnees.get(
                timeframe
            )

            if not candles:
                continue

            item: Dict[str, Any] = {
                "candles": candles,
            }

            if isinstance(
                candles,
                (list, tuple),
            ) and candles:

                last = candles[-1]

                close = self._get(
                    last,
                    "close",
                )

                if close is not None:
                    item["price"] = (
                        self._float(close)
                    )

                item["close"] = (
                    self._float(close)
                )

                item["direction"] = (
                    self._infer_candle_direction(
                        candles
                    )
                )

                item["momentum"] = (
                    self._infer_momentum(
                        candles
                    )
                )

                item["volatility"] = (
                    self._infer_volatility(
                        candles
                    )
                )

            data["timeframes"][
                timeframe
            ] = item

            data[timeframe] = item

        # Informations déjà produites par la cartographie.
        cartography_data = (
            self._as_dict(
                cartographie
            )
        )

        if isinstance(
            cartography_data,
            dict,
        ):

            for key in (
                "direction",
                "bias",
                "momentum",
                "volatility",
                "pressure",
                "market_state",
                "market_regime",
            ):

                if key in cartography_data:
                    data[key] = (
                        cartography_data[key]
                    )

        return data

    def _infer_candle_direction(
        self,
        candles: Any,
    ) -> str:

        if not isinstance(
            candles,
            (list, tuple),
        ):
            return "NEUTRAL"

        recent = list(
            candles[-5:]
        )

        buy = 0
        sell = 0

        for candle in recent:

            open_price = self._float(
                self._get(
                    candle,
                    "open",
                )
            )

            close_price = self._float(
                self._get(
                    candle,
                    "close",
                )
            )

            if (
                open_price is None
                or close_price is None
            ):
                continue

            if close_price > open_price:
                buy += 1

            elif close_price < open_price:
                sell += 1

        if buy > sell:
            return "BUY"

        if sell > buy:
            return "SELL"

        return "NEUTRAL"

    def _infer_momentum(
        self,
        candles: Any,
    ) -> float:

        if not isinstance(
            candles,
            (list, tuple),
        ):
            return 0.0

        if len(candles) < 3:
            return 0.0

        first = self._float(
            self._get(
                candles[-3],
                "close",
            )
        )

        last = self._float(
            self._get(
                candles[-1],
                "close",
            )
        )

        if (
            first is None
            or last is None
            or first == 0
        ):
            return 0.0

        return (
            (last - first)
            / abs(first)
        ) * 100.0

    def _infer_volatility(
        self,
        candles: Any,
    ) -> float:

        if not isinstance(
            candles,
            (list, tuple),
        ):
            return 0.0

        ranges: List[float] = []

        for candle in list(
            candles[-10:]
        ):

            high = self._float(
                self._get(
                    candle,
                    "high",
                )
            )

            low = self._float(
                self._get(
                    candle,
                    "low",
                )
            )

            if (
                high is not None
                and low is not None
            ):

                ranges.append(
                    abs(high - low)
                )

        if not ranges:
            return 0.0

        average = (
            sum(ranges)
            / len(ranges)
        )

        return average

    # ========================================================================
    # CARTOGRAPHIE
    # ========================================================================

    async def analyser_marche(
        self,
        donnees: Dict[str, Any],
    ) -> Any:

        try:

            return await self._call(
                self.marche.cartographier_marche,
                donnees,
                symbol=self.symbol,
            )

        except TypeError:

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

        try:

            return await self._call(
                self.zones.analyser,
                cartographie,
                current_price,
                symbol=self.symbol,
            )

        except TypeError:

            try:

                return await self._call(
                    self.zones.analyser,
                    cartographie,
                    current_price,
                )

            except TypeError:

                return await self._call(
                    self.zones.analyser,
                    market=cartographie,
                    current_price=current_price,
                )

    # ========================================================================
    # CONTEXTE
    # ========================================================================

    async def analyser_contexte(
        self,
        donnees: Dict[str, Any],
        zones: Any,
    ) -> Any:

        try:

            return await self._call(
                self.contexte.analyser,
                donnees,
                zones,
                symbol=self.symbol,
            )

        except TypeError:

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

        try:

            return await self._call(
                self.confluences.analyser,
                donnees,
                zones,
                contexte,
                cartographie,
                symbol=self.symbol,
            )

        except TypeError:

            return await self._call(
                self.confluences.analyser,
                donnees,
                zones,
                contexte,
                cartographie,
            )

    # ========================================================================
    # MARKET INTELLIGENCE
    # ========================================================================

    async def analyser_intelligence(
        self,
        market_data: Dict[str, Any],
        contexte: Any,
        zones: Any,
        confluences: Any,
        cartographie: Any,
    ) -> Any:

        context_data = self._as_dict(
            contexte
        )

        structure = {}

        if isinstance(
            context_data,
            dict,
        ):

            structure = (
                context_data.get(
                    "structure",
                    {},
                )
                or {}
            )

        return await self._call(
            self.intelligence.analyser,
            symbol=self.symbol,
            market_data=market_data,
            contexte=context_data,
            zones=zones,
            structure=structure,
            confluences=confluences,
        )

    # ========================================================================
    # RADAR
    # ========================================================================

    async def analyser_radar(
        self,
        market_data: Dict[str, Any],
        zones: Any,
    ) -> Any:

        zones_data = zones

        if not isinstance(
            zones_data,
            list,
        ):

            if isinstance(
                zones_data,
                dict,
            ):

                zones_data = (
                    zones_data.get(
                        "zones"
                    )
                    or zones_data.get(
                        "important_zones"
                    )
                    or []
                )

            else:

                zones_data = []

        return await self._call(
            self.radar.surveiller,
            self.symbol,
            market_data,
            zones_data,
        )

    # ========================================================================
    # SCÉNARIOS
    # ========================================================================

    async def analyser_scenarios(
        self,
        intelligence: Any,
        radar_events: Any,
        contexte: Any,
        zones: Any,
        setups: Any,
    ) -> Any:

        return await self._call(
            self.scenarios.analyser,
            symbol=self.symbol,
            intelligence=intelligence,
            radar_events=radar_events,
            contexte=self._as_dict(
                contexte
            ),
            zones=self._extract_list(
                zones,
                (
                    "zones",
                    "important_zones",
                ),
            ),
            setups=self._extract_list(
                setups,
                (
                    "setups",
                    "detected_setups",
                    "opportunities",
                ),
            ),
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

        try:

            return await self._call(
                self.setups.analyser,
                zones,
                confluences,
                contexte,
                donnees,
                symbol=self.symbol,
            )

        except TypeError:

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
            symbol=self.symbol,
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
    # VALIDATION
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
    # EXTRACTION
    # ========================================================================

    @staticmethod
    def _extract_list(
        value: Any,
        keys: tuple,
    ) -> List[Any]:

        if value is None:
            return []

        if isinstance(
            value,
            (list, tuple),
        ):
            return list(value)

        if isinstance(
            value,
            dict,
        ):

            for key in keys:

                items = value.get(
                    key
                )

                if isinstance(
                    items,
                    (list, tuple),
                ):
                    return list(items)

                if items is not None:
                    return [items]

        return [value]

    @classmethod
    def _extraire_setups(
        cls,
        result: Any,
    ) -> List[Any]:

        return cls._extract_list(
            result,
            (
                "setups",
                "detected_setups",
                "opportunities",
            ),
        )

    @classmethod
    def _extraire_risk_plans(
        cls,
        result: Any,
    ) -> List[Any]:

        return cls._extract_list(
            result,
            (
                "plans",
                "risk_plans",
                "valid_plans",
                "results",
            ),
        )

    def _trouver_risk_plan(
        self,
        setup: Any,
        index: int,
        risk_plans: List[Any],
    ) -> Any:

        setup_id = (
            self._get(
                setup,
                "setup_id",
            )
            or self._get(
                setup,
                "id",
            )
        )

        if setup_id is not None:

            setup_id = str(
                setup_id
            )

            for plan in risk_plans:

                plan_id = (
                    self._get(
                        plan,
                        "setup_id",
                    )
                    or self._get(
                        plan,
                        "id",
                    )
                )

                if (
                    plan_id is not None
                    and str(plan_id)
                    == setup_id
                ):

                    return plan

        if index < len(
            risk_plans
        ):

            return risk_plans[index]

        return None

    # ========================================================================
    # TRAITEMENT SETUP
    # ========================================================================

    async def traiter_setup(
        self,
        setup: Any,
        risk_plan: Any,
        zones: Any,
        contexte: Any,
        confluences: Any,
        donnees: Dict[str, Any],
        intelligence: Any = None,
        scenarios: Any = None,
    ) -> Dict[str, Any]:

        # --------------------------------------------------------------------
        # CONFIRMATION
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
                "Erreur confirmation : %s",
                exc,
            )

            confirmation = {
                "confirmation_status":
                    "UNAVAILABLE",
                "m5_confirmed": False,
                "m1_confirmed": False,
                "confirmation_valid": True,
                "error": str(exc),
                "metadata": {
                    "m5_is_blocking": False,
                    "m1_is_blocking": False,
                },
            }

        # --------------------------------------------------------------------
        # SCORE
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
                "Erreur score : %s",
                exc,
            )

            score_result = {
                "score": None,
                "quality": "UNAVAILABLE",
                "error": str(exc),
            }

        # --------------------------------------------------------------------
        # VALIDATION TECHNIQUE
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
                "Erreur validation : %s",
                exc,
            )

            validation = {
                "valid": False,
                "status": "TECHNICAL_ERROR",
                "technical_blockers": [
                    str(exc)
                ],
            }

        # --------------------------------------------------------------------
        # DECISION ENGINE
        # --------------------------------------------------------------------

        try:

            decision_result = (
                self.decision.analyser(
                    setup=setup,
                    contexte=contexte,
                    zones=zones,
                    structure=self._get(
                        self._as_dict(
                            contexte
                        ),
                        "structure",
                    ),
                    confluences=confluences,
                    risk_plan=risk_plan,
                    score_result=score_result,
                    validation_result=validation,
                    confirmation_result=confirmation,
                    market_intelligence=(
                        intelligence
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
        # WAIT
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
                "intelligence": intelligence,
                "scenarios": scenarios,
                "signal": None,
            }

        if decision not in (
            DECISION_BUY,
            DECISION_SELL,
        ):

            return {
                "status": "WAIT",
                "setup": setup,
                "risk": risk_plan,
                "decision": DECISION_WAIT,
                "decision_result": decision_result,
                "signal": None,
            }

        # --------------------------------------------------------------------
        # ANTI-SPAM
        # --------------------------------------------------------------------

        try:

            antispam = (
                self.antispam.verifier(
                    setup=setup,
                    risk_plan=risk_plan,
                    validation=validation,
                    decision=decision,
                )
            )

        except TypeError:

            antispam = (
                self.antispam.verifier(
                    setup=setup,
                    risk_plan=risk_plan,
                    validation=validation,
                )
            )

        except Exception as exc:

            logger.exception(
                "Erreur AntiSpam : %s",
                exc,
            )

            return {
                "status": "ANTISPAM_ERROR",
                "setup": setup,
                "risk": risk_plan,
                "decision": decision,
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
                "status":
                    "ANTISPAM_BLOCKED",

                "setup":
                    setup,

                "risk":
                    risk_plan,

                "confirmation":
                    confirmation,

                "score":
                    score_result,

                "validation":
                    validation,

                "decision":
                    decision,

                "decision_result":
                    decision_result,

                "antispam":
                    antispam,

                "signal":
                    None,
            }

        # --------------------------------------------------------------------
        # SIGNAL BUILDER
        # --------------------------------------------------------------------

        try:

            signal = (
                self.signal_builder.construire_signal(
                    setup=setup,
                    risk_plan=risk_plan,
                    confirmation=confirmation,
                    score_result=score_result,
                    validation=validation,
                    antispam_result=antispam,
                    decision_result=decision_result,
                    intelligence=intelligence,
                    scenarios=scenarios,
                )
            )

        except Exception as exc:

            logger.exception(
                "Erreur Signal Builder : %s",
                exc,
            )

            return {
                "status": "SIGNAL_BUILD_ERROR",
                "setup": setup,
                "risk": risk_plan,
                "decision": decision,
                "error": str(exc),
                "signal": None,
            }

        if signal is None:

            return {
                "status": "SIGNAL_NOT_BUILDABLE",
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
        # ENREGISTREMENT ANTISPAM
        # --------------------------------------------------------------------

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

            try:

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
                    "Enregistrement AntiSpam impossible : %s",
                    exc,
                )

        except Exception as exc:

            logger.warning(
                "Enregistrement AntiSpam impossible : %s",
                exc,
            )

        return {
            "status": "SIGNAL_READY",

            "setup": setup,
            "risk": risk_plan,

            "confirmation": confirmation,
            "score": score_result,
            "validation": validation,

            "decision": decision,
            "decision_confidence": confidence,

            "decision_result":
                decision_result,

            "intelligence":
                intelligence,

            "scenarios":
                scenarios,

            "antispam":
                antispam,

            "signal":
                signal,
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
                # REFRESH
                # ------------------------------------------------------------

                await self.rafraichir_cache()

                # ------------------------------------------------------------
                # PRIX
                # ------------------------------------------------------------

                current_price = (
                    self.cache.get_current_price(
                        self.symbol
                    )
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

                missing_secondary = [
                    tf
                    for tf in SECONDARY_TIMEFRAMES
                    if not donnees.get(tf)
                ]

                # ------------------------------------------------------------
                # MARKET CARTOGRAPHY
                # ------------------------------------------------------------

                cartographie = (
                    await self.analyser_marche(
                        donnees
                    )
                )

                # ------------------------------------------------------------
                # MARKET DATA ENRICHI
                # ------------------------------------------------------------

                market_data = (
                    self._construire_market_data(
                        donnees,
                        current_price,
                        cartographie,
                    )
                )

                # ------------------------------------------------------------
                # RADAR
                #
                # Le radar observe avant la construction des scénarios.
                # ------------------------------------------------------------

                radar_events = (
                    await self.analyser_radar(
                        market_data,
                        [],
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
                # RADAR AVEC ZONES
                #
                # Deuxième lecture pour intégrer les interactions avec
                # les zones détectées.
                # ------------------------------------------------------------

                radar_events = (
                    await self.analyser_radar(
                        market_data,
                        zones,
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
                # MARKET INTELLIGENCE
                # ------------------------------------------------------------

                intelligence = (
                    await self.analyser_intelligence(
                        market_data=market_data,
                        contexte=contexte,
                        zones=zones,
                        confluences=confluences,
                        cartographie=cartographie,
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

                # ------------------------------------------------------------
                # SCÉNARIOS
                #
                # Les scénarios utilisent à la fois :
                # Intelligence + Radar + Zones + Setups.
                # ------------------------------------------------------------

                scenarios = (
                    await self.analyser_scenarios(
                        intelligence=intelligence,
                        radar_events=radar_events,
                        contexte=contexte,
                        zones=zones,
                        setups=setups,
                    )
                )

                # ------------------------------------------------------------
                # AUCUN SETUP
                # ------------------------------------------------------------

                if not setups:

                    result = {
                        "status":
                            "NO_SETUP",

                        "engine":
                            ENGINE_NAME,

                        "symbol":
                            self.symbol,

                        "source":
                            "BiQuote",

                        "current_price":
                            current_price,

                        "market_data":
                            market_data,

                        "radar":
                            radar_events,

                        "cartographie":
                            cartographie,

                        "zones":
                            zones,

                        "contexte":
                            contexte,

                        "confluences":
                            confluences,

                        "intelligence":
                            intelligence,

                        "scenarios":
                            scenarios,

                        "setups":
                            [],

                        "results":
                            [],

                        "signals":
                            [],

                        "signal_count":
                            0,

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
                # TOUS LES SETUPS
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
                                intelligence=intelligence,
                                scenarios=scenarios,
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
                # RÉSULTATS
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
                        "SIGNAL_BUILD_ERROR",
                        "SIGNAL_NOT_BUILDABLE",
                    }
                ]

                # ------------------------------------------------------------
                # TRI PAR CONVICTION
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

                signals = [
                    item.get(
                        "signal"
                    )
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

                    overall_status = (
                        "WAIT"
                    )

                else:

                    overall_status = (
                        "ANALYZED"
                    )

                # ------------------------------------------------------------
                # RESULTAT FINAL
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

                    "market_data":
                        market_data,

                    "radar":
                        radar_events,

                    "cartographie":
                        cartographie,

                    "zones":
                        zones,

                    "contexte":
                        contexte,

                    "confluences":
                        confluences,

                    "intelligence":
                        intelligence,

                    "scenarios":
                        scenarios,

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

                    "architecture":
                        {
                            "radar":
                                "moteur2_radar.py",

                            "intelligence":
                                "moteur2_intelligence.py",

                            "scenarios":
                                "moteur2_scenarios.py",

                            "decision":
                                "moteur2_decision.py",

                            "risk":
                                "moteur2_risk.py",

                            "validation":
                                "moteur2_validation.py",

                            "confirmation":
                                "moteur2_confirmation.py",

                            "signal":
                                "moteur2_signal.py",
                        },
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

        try:

            radar_status = (
                self.radar.get_status()
            )

        except Exception:

            radar_status = {}

        try:

            intelligence_status = {
                "module":
                    "MARKET_INTELLIGENCE",
                "adaptive":
                    True,
                "decision_owner":
                    "moteur2_decision.py",
            }

        except Exception:

            intelligence_status = {}

        try:

            scenarios_status = {
                "module":
                    "SCENARIO_ENGINE",
                "adaptive":
                    True,
                "decision_owner":
                    "moteur2_decision.py",
            }

        except Exception:

            scenarios_status = {}

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
                self.cache.get_current_price(
                    self.symbol
                ),

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

            "radar":
                radar_status,

            "intelligence":
                intelligence_status,

            "scenarios":
                scenarios_status,

            "decision":
                decision_status,

            "antispam":
                antispam_status,

            "cache":
                cache_status,

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
            "RADAR : moteur2_radar.py"
        )
        print(
            "INTELLIGENCE : moteur2_intelligence.py"
        )
        print(
            "SCENARIOS : moteur2_scenarios.py"
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
        print(
            "RESULTAT :"
        )
        print(result)

    finally:

        await moteur.stop()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":

# ============================================================================
# NOVA ENGINE 2 — ORCHESTRATEUR GLOBAL MULTI-ACTIFS
# ============================================================================
#
# IMPORTANT :
# L'import est volontairement effectué à l'intérieur de la classe.
#
# Pourquoi ?
# moteur2_multi_actifs.py importe Moteur2 depuis moteur2.py.
# Faire l'import en haut de moteur2.py créerait une dépendance circulaire.
# ============================================================================


class Moteur2Global:
    """
    Orchestrateur global de NOVA TRADE AI Engine 2.

    Architecture :

        XAUUSD ─┐
        BTCUSD ─┤
        EURUSD ─┼──> moteurs indépendants
        GBPUSD ─┘
                    ↓
              résultats individuels
                    ↓
              ranking global
                    ↓
                 TOP 3

    Ce gestionnaire ne remplace pas Moteur2.

    Moteur2 reste responsable de l'analyse complète d'un seul actif.

    Moteur2Global ajoute uniquement :
        - multi-actifs ;
        - ranking global ;
        - maximum 3 signaux ;
        - aucun signal forcé.
    """

    def __init__(
        self,
        symbols=None,
        max_signals: int = 3,
        parallel: bool = True,
    ) -> None:

        # ---------------------------------------------------------------
        # Import tardif pour éviter l'import circulaire.
        # ---------------------------------------------------------------

        from moteur2_multi_actifs import (
            Moteur2MultiActifs,
        )

        from moteur2_ranking import (
            Moteur2Ranking,
        )

        # ---------------------------------------------------------------
        # Configuration
        # ---------------------------------------------------------------

        if symbols is None:

            symbols = list(
                SUPPORTED_SYMBOLS
            )

        self.symbols = tuple(
            str(symbol)
            .strip()
            .upper()
            .replace("/", "")
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
            for symbol in symbols
        )

        self.max_signals = max(
            1,
            int(max_signals),
        )

        self.parallel = bool(
            parallel
        )

        # ---------------------------------------------------------------
        # Gestionnaire des moteurs individuels
        # ---------------------------------------------------------------

        self.multi_actifs = (
            Moteur2MultiActifs(
                symbols=self.symbols,
                parallel=self.parallel,
            )
        )

        # ---------------------------------------------------------------
        # Ranking global
        # ---------------------------------------------------------------

        self.ranking = Moteur2Ranking(
            max_signals=self.max_signals
        )

        # ---------------------------------------------------------------
        # État
        # ---------------------------------------------------------------

        self.initialized = False
        self.running = False

        self.last_cycle = None
        self.last_ranking = None

        self.analysis_lock = asyncio.Lock()

    # ====================================================================
    # INITIALISATION
    # ====================================================================

    async def initialiser(
        self,
    ) -> Dict[str, Any]:

        logger.info(
            "=================================================="
        )

        logger.info(
            "NOVA TRADE AI — ENGINE 2 GLOBAL"
        )

        logger.info(
            "Initialisation multi-actifs..."
        )

        logger.info(
            "Actifs : %s",
            ", ".join(self.symbols),
        )

        logger.info(
            "Maximum signaux : %s",
            self.max_signals,
        )

        logger.info(
            "=================================================="
        )

        try:

            result = (
                await self.multi_actifs.initialiser()
            )

            initialized_symbols = (
                result.get(
                    "initialized_symbols",
                    [],
                )
            )

            self.initialized = bool(
                initialized_symbols
            )

            return {
                "success":
                    self.initialized,

                "engine":
                    ENGINE_NAME,

                "module":
                    "moteur2_global",

                "symbols":
                    list(self.symbols),

                "initialized_symbols":
                    initialized_symbols,

                "failed_symbols":
                    result.get(
                        "failed_symbols",
                        [],
                    ),

                "max_signals":
                    self.max_signals,

                "forced_signal":
                    False,

                "ranking_is_decision_maker":
                    False,

                "quality_is_blocking":
                    False,

                "results":
                    result.get(
                        "results",
                        {},
                    ),
            }

        except Exception as exc:

            logger.exception(
                "Erreur initialisation Engine 2 Global : %s",
                exc,
            )

            self.initialized = False

            return {
                "success": False,
                "engine": ENGINE_NAME,
                "module": "moteur2_global",
                "symbols": list(
                    self.symbols
                ),
                "error": str(exc),
            }

    # ====================================================================
    # STREAMS
    # ====================================================================

    async def demarrer_streams(
        self,
    ) -> Dict[str, Any]:

        try:

            return await (
                self.multi_actifs.demarrer_streams()
            )

        except Exception as exc:

            logger.exception(
                "Erreur démarrage streams globaux : %s",
                exc,
            )

            return {
                "success": False,
                "error": str(exc),
            }

    # ====================================================================
    # ANALYSE GLOBALE
    # ====================================================================

    async def analyser(
        self,
    ) -> Dict[str, Any]:

        async with self.analysis_lock:

            if not self.initialized:

                init = (
                    await self.initialiser()
                )

                if not init.get(
                    "success",
                    False,
                ):

                    return {
                        "status":
                            "INITIALIZATION_ERROR",

                        "engine":
                            ENGINE_NAME,

                        "signals":
                            [],

                        "error":
                            init.get(
                                "error",
                                "Initialisation impossible.",
                            ),
                    }

            try:

                # --------------------------------------------------------
                # 1. Analyse indépendante des 4 actifs
                # --------------------------------------------------------

                cycle = (
                    await self.multi_actifs.analyser_tous()
                )

                self.last_cycle = cycle

                # --------------------------------------------------------
                # 2. Ranking global
                # --------------------------------------------------------

                ranking = (
                    self.ranking.ranker(
                        cycle
                    )
                )

                self.last_ranking = ranking

                # --------------------------------------------------------
                # 3. Signaux finaux
                # --------------------------------------------------------

                signals = ranking.get(
                    "signals",
                    [],
                )

                # --------------------------------------------------------
                # 4. Résultat global
                # --------------------------------------------------------

                result = {

                    "status":
                        "SIGNALS_AVAILABLE"
                        if signals
                        else "NO_GLOBAL_SIGNAL",

                    "engine":
                        ENGINE_NAME,

                    "module":
                        "moteur2_global",

                    "symbols":
                        list(self.symbols),

                    "max_signals":
                        self.max_signals,

                    "signals":
                        signals,

                    "signal_count":
                        len(signals),

                    "candidates_count":
                        ranking.get(
                            "candidate_count",
                            0,
                        ),

                    "selected_count":
                        ranking.get(
                            "selected_count",
                            0,
                        ),

                    "cycle":
                        cycle,

                    "ranking":
                        ranking,

                    # ----------------------------------------------------
                    # Sécurité architecturale
                    # ----------------------------------------------------

                    "forced_signal":
                        False,

                    "quality_is_blocking":
                        False,

                    "ranking_is_decision_maker":
                        False,

                    "auto_execution":
                        False,

                    "decision_owner":
                        "moteur2_decision.py",

                    "risk_owner":
                        "moteur2_risk.py",

                    "validation_owner":
                        "moteur2_validation.py",

                    "ranking_owner":
                        "moteur2_ranking.py",
                }

                logger.info(
                    "ENGINE 2 GLOBAL : "
                    "%s candidat(s) → %s signal(aux) retenu(s).",
                    ranking.get(
                        "candidate_count",
                        0,
                    ),
                    len(signals),
                )

                return result

            except Exception as exc:

                logger.exception(
                    "Erreur analyse Engine 2 Global : %s",
                    exc,
                )

                return {
                    "status":
                        "GLOBAL_ENGINE_ERROR",

                    "engine":
                        ENGINE_NAME,

                    "module":
                        "moteur2_global",

                    "signals":
                        [],

                    "signal_count":
                        0,

                    "error":
                        str(exc),

                    "forced_signal":
                        False,

                    "auto_execution":
                        False,
                }

    # ====================================================================
    # TOP 3
    # ====================================================================

    def obtenir_top_signaux(
        self,
    ) -> List[Any]:

        if not self.last_ranking:

            return []

        return self.last_ranking.get(
            "signals",
            [],
        )

    # ====================================================================
    # STATUS
    # ====================================================================

    def get_status(
        self,
    ) -> Dict[str, Any]:

        try:

            multi_status = (
                self.multi_actifs.get_status()
            )

        except Exception as exc:

            multi_status = {
                "status":
                    "ERROR",
                "error":
                    str(exc),
            }

        try:

            ranking_status = (
                self.ranking.get_status()
            )

        except Exception as exc:

            ranking_status = {
                "status":
                    "ERROR",
                "error":
                    str(exc),
            }

        return {

            "engine":
                ENGINE_NAME,

            "module":
                "moteur2_global",

            "symbols":
                list(self.symbols),

            "symbol_count":
                len(self.symbols),

            "initialized":
                self.initialized,

            "running":
                self.running,

            "max_signals":
                self.max_signals,

            "forced_signal":
                False,

            "quality_is_blocking":
                False,

            "ranking_is_decision_maker":
                False,

            "auto_execution":
                False,

            "multi_actifs":
                multi_status,

            "ranking":
                ranking_status,

            "last_signal_count":
                len(
                    self.obtenir_top_signaux()
                ),
        }

    # ====================================================================
    # RUN CONTINU
    # ====================================================================

    async def run(
        self,
        analysis_interval_seconds: int = 10,
        start_streams: bool = True,
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
                    "Impossible d'initialiser "
                    "Engine 2 Global."
                )

        self.running = True

        logger.info(
            "ENGINE 2 GLOBAL démarré."
        )

        stream_task = None

        try:

            # ------------------------------------------------------------
            # Les streams sont démarrés une seule fois.
            # ------------------------------------------------------------

            if start_streams:

                stream_task = asyncio.create_task(
                    self.demarrer_streams()
                )

            # ------------------------------------------------------------
            # Boucle globale
            # ------------------------------------------------------------

            while self.running:

                try:

                    await self.analyser()

                except Exception as exc:

                    logger.exception(
                        "Erreur cycle global : %s",
                        exc,
                    )

                await asyncio.sleep(
                    max(
                        1,
                        int(
                            analysis_interval_seconds
                        ),
                    )
                )

        finally:

            self.running = False

            if stream_task is not None:

                stream_task.cancel()

                try:

                    await stream_task

                except asyncio.CancelledError:

                    pass

    # ====================================================================
    # STOP
    # ====================================================================

    async def stop(
        self,
    ) -> None:

        self.running = False

        try:

            await self.multi_actifs.stop()

        except Exception as exc:

            logger.warning(
                "Erreur arrêt Engine 2 Global : %s",
                exc,
            )


# ============================================================================
# INSTANCE GLOBALE
# ============================================================================

moteur2_global = Moteur2Global(
    symbols=SUPPORTED_SYMBOLS,
    max_signals=3,
    parallel=True,
)


# ============================================================================
# RACCOURCIS GLOBAUX
# ============================================================================

async def initialiser_engine2_global(
) -> Dict[str, Any]:

    return await (
        moteur2_global.initialiser()
    )


async def analyser_engine2_global(
) -> Dict[str, Any]:

    return await (
        moteur2_global.analyser()
    )


async def arreter_engine2_global(
) -> None:

    await (
        moteur2_global.stop()
    )


def statut_engine2_global(
) -> Dict[str, Any]:

    return (
        moteur2_global.get_status()
    )


def top_signaux_engine2_global(
) -> List[Any]:

    return (
        moteur2_global.obtenir_top_signaux()
    )
    asyncio.run(main())