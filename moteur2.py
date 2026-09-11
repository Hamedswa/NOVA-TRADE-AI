"""
NOVA TRADE AI - ENGINE 2
moteur2.py

ORCHESTRATEUR PRINCIPAL DU MOTEUR 2

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
    Setups / opportunités
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
    Anti-spam
        ↓
    Publication Telegram
        ↓
    Enregistrement du signal publié


PHILOSOPHIE :

    Le moteur ne fonctionne PAS comme une checklist rigide.

    Le marché est observé en continu.

    Les informations disponibles sont combinées afin de permettre
    au Decision Engine de déterminer si une opportunité est exploitable.

    Le score n'est PAS un veto.
    Le RR n'est PAS un veto.
    M5 n'est PAS un veto.
    M1 n'est PAS un veto.

    La validation technique vérifie uniquement que le dossier est
    techniquement cohérent.

    Le Risk Engine construit Entry / SL / TP.

    Le Decision Engine est le seul propriétaire de la décision
    stratégique BUY / SELL / WAIT.

    Plusieurs opportunités peuvent être retenues sur un même scan.

    Aucun quota de signal.

    Aucun signal forcé.

    Auto-exécution désactivée.
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


logger = logging.getLogger("NOVA_ENGINE_2")


# ============================================================================
# CONFIGURATION
# ============================================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
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

CONFIRMATION_TIMEFRAMES = (
    "M5",
    "M1",
)

ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"

CANDLE_LIMIT = 300

SCAN_INTERVAL_SECONDS = 60

# ============================================================================
# RÉFÉRENCES UNIQUEMENT
# ============================================================================

# IMPORTANT :
# Ces valeurs ne sont PLUS des conditions de rejet.
#
# Elles restent conservées pour compatibilité avec d'autres modules
# et pour afficher des références de qualité.

REFERENCE_RR = 3.0
REFERENCE_SCORE = 60.0

# Compatibilité avec l'ancien code.
MINIMUM_RR = REFERENCE_RR
MINIMUM_SCORE = REFERENCE_SCORE

READY_FOR_SIGNAL = "READY_FOR_SIGNAL"

DECISION_BUY = "BUY"
DECISION_SELL = "SELL"
DECISION_WAIT = "WAIT"


# ============================================================================
# NORMALISATION SYMBOLE
# ============================================================================

def _normalize_symbol(symbol: Any) -> str:
    """
    Normalise un symbole sans fallback automatique.
    """

    value = (
        str(symbol or "")
        .strip()
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    aliases = {
        "GOLD": "XAUUSD",
        "XAU": "XAUUSD",
        "BTC": "BTCUSD",
        "EUR": "EURUSD",
        "GBP": "GBPUSD",
    }

    return aliases.get(
        value,
        value,
    )


# ============================================================================
# MOTEUR 2
# ============================================================================

class Moteur2:
    """
    Orchestrateur principal du moteur 2.

    Responsabilités :

        - récupération des données
        - orchestration des modules
        - analyse des opportunités
        - transmission des informations au Decision Engine
        - conservation des résultats
        - préparation des signaux pour Telegram

    Le moteur2.py ne prend pas lui-même la décision stratégique.

    Le Decision Engine est propriétaire de :

        BUY
        SELL
        WAIT
    """

    def __init__(
        self,
        symbols: Optional[
            List[str] | tuple[str, ...]
        ] = None,
    ) -> None:

        raw_symbols = (
            symbols
            if symbols is not None
            else SUPPORTED_SYMBOLS
        )

        normalized_symbols = tuple(
            _normalize_symbol(symbol)
            for symbol in raw_symbols
        )

        invalid_symbols = [
            symbol
            for symbol in normalized_symbols
            if symbol not in SUPPORTED_SYMBOLS
        ]

        if invalid_symbols:
            raise ValueError(
                f"Symboles non supportés : {invalid_symbols}"
            )

        self.symbols = tuple(
            dict.fromkeys(
                normalized_symbols
            )
        )

        if not self.symbols:
            raise ValueError(
                "Le moteur 2 doit avoir au moins un symbole."
            )

        # ====================================================================
        # DATA PROVIDER
        # ====================================================================

        self.biquote = BiQuoteClient()

        # ====================================================================
        # CACHE
        # ====================================================================

        self.cache = Moteur2Cache(
            client=self.biquote,
            symbols=self.symbols,
        )

        # ====================================================================
        # STREAM TEMPS RÉEL
        # ====================================================================

        self.stream = BiQuoteStream(
            symbols=self.symbols,
            on_tick=self._handle_tick,
        )

        # ====================================================================
        # MODULES D'ANALYSE
        # ====================================================================

        self.marche = Moteur2Marche()

        self.zones = Moteur2Zones()

        self.contexte = Moteur2Contexte()

        self.confluences = Moteur2Confluences()

        self.setups = Moteur2Setups()

        # ====================================================================
        # RISK ENGINE
        # ====================================================================

        # reference_rr est utilisé comme référence.
        # Le Risk Engine ne doit plus bloquer uniquement parce que le RR
        # est inférieur à 3.
        self.risk = Moteur2Risk(
            min_rr=REFERENCE_RR,
        )

        # ====================================================================
        # CONFIRMATION
        # ====================================================================

        self.confirmation = Moteur2Confirmation()

        # ====================================================================
        # SCORE
        # ====================================================================

        self.score = Moteur2Score(
            minimum_rr=REFERENCE_RR,
        )

        # ====================================================================
        # VALIDATION TECHNIQUE
        # ====================================================================

        self.validation = Moteur2Validation()

        # ====================================================================
        # CERVEAU STRATÉGIQUE
        # ====================================================================

        self.decision = Moteur2Decision(
            reference_score=REFERENCE_SCORE,
            reference_rr=REFERENCE_RR,
        )

        # ====================================================================
        # ANTI-SPAM
        # ====================================================================

        self.antispam = Moteur2AntiSpam()

        # ====================================================================
        # ÉTAT
        # ====================================================================

        self.running = False

        self.current_prices: Dict[
            str,
            float,
        ] = {}

        self.last_analysis: Dict[
            str,
            Dict[str, Any],
        ] = {}

        self.last_signal: Dict[
            str,
            Dict[str, Any],
        ] = {}

        self._stream_task: Optional[
            asyncio.Task
        ] = None

        # Une seule analyse technique simultanée.
        self.analysis_lock = asyncio.Lock()

    # ========================================================================
    # UTILITAIRE GÉNÉRIQUE
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
    def _extract_price(
        tick: Any,
    ) -> Optional[float]:

        if tick is None:
            return None

        for key in (
            "mid",
            "price",
            "last",
            "bid",
            "ask",
        ):

            value = Moteur2._get(
                tick,
                key,
            )

            if value is None:
                continue

            try:

                price = float(value)

                if price > 0:
                    return price

            except (
                TypeError,
                ValueError,
            ):
                continue

        return None

    # ========================================================================
    # TICK TEMPS RÉEL
    # ========================================================================

    async def _handle_tick(
        self,
        tick: Any,
    ) -> None:

        symbol = _normalize_symbol(
            self._get(
                tick,
                "symbol",
            )
        )

        if symbol not in self.symbols:
            return

        price = self._extract_price(
            tick
        )

        if price is not None:

            self.current_prices[
                symbol
            ] = price

        try:

            result = self.cache.update_tick(
                tick
            )

            if inspect.isawaitable(result):
                await result

        except Exception as exc:

            logger.warning(
                "Erreur mise à jour tick cache %s : %s",
                symbol,
                exc,
            )

    # ========================================================================
    # PRIX COURANT
    # ========================================================================

    def _get_current_price(
        self,
        symbol: str,
    ) -> Optional[float]:

        normalized = _normalize_symbol(
            symbol
        )

        # --------------------------------------------------------------------
        # 1. STREAM
        # --------------------------------------------------------------------

        try:

            tick = self.stream.get_latest_tick(
                normalized
            )

            price = self._extract_price(
                tick
            )

            if price is not None:
                return price

        except Exception:
            pass

        # --------------------------------------------------------------------
        # 2. CACHE
        # --------------------------------------------------------------------

        try:

            price = self.cache.get_current_price(
                normalized
            )

            if price is not None:
                return float(price)

        except Exception:
            pass

        # --------------------------------------------------------------------
        # 3. DERNIER PRIX CONNU
        # --------------------------------------------------------------------

        return self.current_prices.get(
            normalized
        )

    # ========================================================================
    # RAFRAÎCHISSEMENT CACHE
    # ========================================================================

    async def _refresh_symbol_cache(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        normalized = _normalize_symbol(
            symbol
        )

        result = await self.cache.refresh_symbol(
            normalized,
            force=False,
        )

        return result or {}

    # ========================================================================
    # LECTURE CACHE
    # ========================================================================

    def _get_cached_candles(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        normalized = _normalize_symbol(
            symbol
        )

        candles_by_timeframe: Dict[
            str,
            Any,
        ] = {}

        for timeframe in TIMEFRAMES:

            try:

                candles = (
                    self.cache.get_closed_candles(
                        normalized,
                        timeframe,
                    )
                )

            except TypeError:

                candles = (
                    self.cache.get_candles(
                        normalized,
                        timeframe,
                    )
                )

            except Exception as exc:

                logger.warning(
                    "Erreur lecture cache %s %s : %s",
                    normalized,
                    timeframe,
                    exc,
                )

                candles = None

            if candles:

                candles_by_timeframe[
                    timeframe
                ] = candles

        return candles_by_timeframe

    # ========================================================================
    # CHANDELIERS
    # ========================================================================

    async def _get_candles(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        normalized = _normalize_symbol(
            symbol
        )

        await self._refresh_symbol_cache(
            normalized
        )

        return self._get_cached_candles(
            normalized
        )

    # ========================================================================
    # EXTRACTION DES SETUPS
    # ========================================================================

    @staticmethod
    def _extract_setups(
        setups_result: Any,
    ) -> List[Any]:

        if setups_result is None:
            return []

        if isinstance(
            setups_result,
            dict,
        ):

            for key in (
                "setups",
                "results",
                "candidates",
                "items",
            ):

                value = setups_result.get(
                    key
                )

                if isinstance(
                    value,
                    list,
                ):
                    return value

            return [
                setups_result
            ]

        if isinstance(
            setups_result,
            (
                list,
                tuple,
            ),
        ):

            return list(
                setups_result
            )

        return [
            setups_result
        ]

    # ========================================================================
    # TRAITEMENT D'UN SETUP
    # ========================================================================

    async def traiter_setup(
        self,
        setup: Any,
        *,
        symbol: str,
        candles: Dict[str, Any],
        zones_result: Any,
        context_result: Any,
        confluences_result: Any,
        cartographie_result: Any,
        current_price: Optional[float],
    ) -> Optional[Dict[str, Any]]:

        normalized = _normalize_symbol(
            symbol
        )

        # ====================================================================
        # 1. RISK ENGINE
        # ====================================================================
        #
        # Construit le plan.
        #
        # Il ne décide PAS si le trade doit être pris.
        #

        risk_plan = self.risk.analyser_setup(
            setup=setup,
            zones=zones_result,
            candles=candles,
            current_price=current_price,
            symbol=normalized,
        )

        # ====================================================================
        # 2. CONFIRMATION M5 / M1
        # ====================================================================
        #
        # Information supplémentaire.
        # Pas de veto automatique.
        #

        confirmation_result = (
            self.confirmation.analyser(
                setup=setup,
                candles=candles,
                risk_plan=risk_plan,
                symbol=normalized,
            )
        )

        # ====================================================================
        # 3. SCORE
        # ====================================================================
        #
        # Mesure descriptive.
        # Pas de seuil de rejet.
        #

        score_result = self.score.analyser(
            setup=setup,
            zones=zones_result,
            context=context_result,
            confluences=confluences_result,
            confirmation=confirmation_result,
            risk_plan=risk_plan,
            symbol=normalized,
        )

        # ====================================================================
        # 4. VALIDATION TECHNIQUE
        # ====================================================================
        #
        # Vérifie uniquement la cohérence technique du dossier.
        #

        validation_result = (
            self.validation.analyser(
                setup=setup,
                risk_plan=risk_plan,
                confirmation=confirmation_result,
                score_result=score_result,
                context=context_result,
                confluences=confluences_result,
            )
        )

        validation_status = str(
            self._get(
                validation_result,
                "status",
                "",
            )
        ).strip().upper()

        validation_valid = bool(
            self._get(
                validation_result,
                "valid",
                self._get(
                    validation_result,
                    "validated",
                    False,
                ),
            )
        )

        # ====================================================================
        # 5. DECISION ENGINE
        # ====================================================================
        #
        # C'est ICI que le cerveau décide.
        #
        # Il reçoit toutes les informations disponibles.
        #
        # IMPORTANT :
        # validation_valid=False n'est pas automatiquement interprété
        # comme une décision stratégique.
        #
        # En revanche, si le dossier est techniquement impossible,
        # le Decision Engine le transforme en WAIT technique.
        #

        decision_result = self.decision.analyser(
            setup=setup,
            contexte=context_result,
            zones=zones_result,
            structure=cartographie_result,
            confluences=confluences_result,
            risk_plan=risk_plan,
            score_result=score_result,
            validation_result=validation_result,
            confirmation_result=confirmation_result,
            market_intelligence=cartographie_result,
        )

        decision = str(
            self._get(
                decision_result,
                "decision",
                DECISION_WAIT,
            )
        ).strip().upper()

        confidence = self._get(
            decision_result,
            "confidence",
            0.0,
        )

        try:
            confidence = float(
                confidence
            )

        except (
            TypeError,
            ValueError,
        ):
            confidence = 0.0

        # ====================================================================
        # 6. WAIT
        # ====================================================================
        #
        # WAIT est une décision légitime.
        #
        # On ne force jamais un signal.
        #

        if decision == DECISION_WAIT:

            return {
                "status": DECISION_WAIT,
                "symbol": normalized,
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation_result,
                "score": score_result,
                "validation": validation_result,
                "decision": decision_result,
                "decision_confidence": confidence,
                "registered": False,
                "published": False,
                "auto_execution": False,
            }

        # ====================================================================
        # 7. DECISION ACTIONNABLE
        # ====================================================================
        #
        # BUY / SELL.
        #
        # Le Decision Engine a choisi l'opportunité.
        #

        if decision not in (
            DECISION_BUY,
            DECISION_SELL,
        ):

            logger.warning(
                "Decision inconnue %s pour %s",
                decision,
                normalized,
            )

            return {
                "status": DECISION_WAIT,
                "symbol": normalized,
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation_result,
                "score": score_result,
                "validation": validation_result,
                "decision": decision_result,
                "decision_confidence": confidence,
                "registered": False,
                "published": False,
                "auto_execution": False,
            }

        # ====================================================================
        # 8. ANTI-SPAM
        # ====================================================================
        #
        # L'anti-spam ne décide pas du marché.
        #
        # Il empêche uniquement la répétition abusive d'un même setup.
        #

        antispam_result = (
            self.antispam.verifier(
                setup=setup,
                risk_plan=risk_plan,
                validation=validation_result,
            )
        )

        antispam_allowed = bool(
            self._get(
                antispam_result,
                "allowed",
                False,
            )
        )

        if not antispam_allowed:

            return {
                "status": "ANTISPAM_REJECTED",
                "symbol": normalized,
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation_result,
                "score": score_result,
                "validation": validation_result,
                "decision": decision_result,
                "antispam": antispam_result,
                "decision_confidence": confidence,
                "registered": False,
                "published": False,
                "auto_execution": False,
            }

        # ====================================================================
        # 9. IDENTIFIANT SETUP
        # ====================================================================

        setup_id = self._get(
            antispam_result,
            "setup_id",
            None,
        )

        if not setup_id:

            try:

                setup_id = (
                    self.antispam.generer_setup_id(
                        setup,
                        risk_plan,
                    )
                )

            except Exception:

                setup_id = self._get(
                    setup,
                    "setup_id",
                    None,
                )

        # ====================================================================
        # 10. SIGNAL PRÊT POUR TELEGRAM
        # ====================================================================

        signal = {
            "status": READY_FOR_SIGNAL,

            "decision": decision,

            "decision_result": decision_result,

            "decision_confidence": confidence,

            "symbol": normalized,

            "setup_id": setup_id,

            "setup": setup,

            "risk": risk_plan,

            "confirmation": confirmation_result,

            "score": score_result,

            "validation": validation_result,

            "antispam": antispam_result,

            "registered": False,

            "published": False,

            "auto_execution": False,
        }

        # Conservation du dernier signal actionnable.
        self.last_signal[
            normalized
        ] = signal

        return signal

    # ========================================================================
    # ENREGISTREMENT APRES PUBLICATION
    # ========================================================================

    def enregistrer_signal_publie(
        self,
        signal: Any,
    ) -> Optional[str]:
        """
        Enregistre un signal uniquement après publication réussie.

        Cette méthode :
            - ne crée pas de nouveau signal
            - ne modifie pas Entry
            - ne modifie pas SL
            - ne modifie pas TP
            - ne prend aucune décision stratégique
        """

        if signal is None:
            return None

        status = str(
            self._get(
                signal,
                "status",
                "",
            )
        ).strip().upper()

        if status != READY_FOR_SIGNAL:

            logger.warning(
                "Tentative d'enregistrement d'un signal non READY."
            )

            return None

        setup = self._get(
            signal,
            "setup",
            None,
        )

        risk_plan = self._get(
            signal,
            "risk",
            None,
        )

        validation = self._get(
            signal,
            "validation",
            None,
        )

        antispam_result = self._get(
            signal,
            "antispam",
            None,
        )

        setup_id = self._get(
            antispam_result,
            "setup_id",
            None,
        )

        if not setup_id:

            setup_id = self._get(
                signal,
                "setup_id",
                None,
            )

        try:

            registered_id = (
                self.antispam.enregistrer_signal(
                    setup=setup,
                    risk_plan=risk_plan,
                    setup_id=setup_id,
                    validation=validation,
                )
            )

        except Exception as exc:

            logger.exception(
                "Erreur enregistrement signal publié : %s",
                exc,
            )

            return None

        if registered_id:

            symbol = _normalize_symbol(
                self._get(
                    signal,
                    "symbol",
                    "",
                )
            )

            if symbol:

                stored_signal = self.last_signal.get(
                    symbol
                )

                if stored_signal is not None:

                    stored_signal[
                        "registered"
                    ] = True

                    stored_signal[
                        "published"
                    ] = True

                    stored_signal[
                        "setup_id"
                    ] = registered_id

            return registered_id

        return None

    # ========================================================================
    # ANALYSE D'UN SYMBOLE
    # ========================================================================

    async def analyser_symbole(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        normalized = _normalize_symbol(
            symbol
        )

        if normalized not in self.symbols:

            raise ValueError(
                f"Symbole non configuré : {normalized}"
            )

        async with self.analysis_lock:

            logger.info(
                "Analyse Engine 2 : %s",
                normalized,
            )

            # =================================================================
            # DONNÉES
            # =================================================================

            candles = await self._get_candles(
                normalized
            )

            missing_timeframes = [
                timeframe
                for timeframe in TIMEFRAMES
                if not candles.get(
                    timeframe
                )
            ]

            if missing_timeframes:

                result = {
                    "status": "INSUFFICIENT_DATA",
                    "symbol": normalized,
                    "missing_timeframes": (
                        missing_timeframes
                    ),
                    "candles": candles,
                    "auto_execution": False,
                }

                self.last_analysis[
                    normalized
                ] = result

                return result

            # =================================================================
            # PRIX COURANT
            # =================================================================

            current_price = (
                self._get_current_price(
                    normalized
                )
            )

            if current_price is None:

                result = {
                    "status": "NO_CURRENT_PRICE",
                    "symbol": normalized,
                    "candles": candles,
                    "auto_execution": False,
                }

                self.last_analysis[
                    normalized
                ] = result

                return result

            # =================================================================
            # CARTOGRAPHIE
            # =================================================================

            cartographie = self.marche.analyser(
                candles,
                symbol=normalized,
            )

            # =================================================================
            # ZONES
            # =================================================================

            zones_result = self.zones.analyser(
                cartographie,
                current_price=current_price,
            )

            # =================================================================
            # CONTEXTE
            # =================================================================

            context_result = self.contexte.analyser(
                cartographie,
                zones_result,
                symbol=normalized,
            )

            # =================================================================
            # CONFLUENCES
            # =================================================================

            confluences_result = (
                self.confluences.analyser(
                    candles_by_timeframe=candles,
                    zones_result=zones_result,
                    context_result=context_result,
                    market_map=cartographie,
                    symbol=normalized,
                )
            )

            # =================================================================
            # SETUPS / OPPORTUNITÉS
            # =================================================================

            setups_result = self.setups.analyser(
                candles_by_timeframe=candles,
                zones_result=zones_result,
                context_result=context_result,
                confluences_result=confluences_result,
                symbol=normalized,
            )

            setups = self._extract_setups(
                setups_result
            )

            # =================================================================
            # TRAITEMENT DE TOUTES LES OPPORTUNITÉS
            # =================================================================

            results: List[
                Dict[str, Any]
            ] = []

            ready_signals: List[
                Dict[str, Any]
            ] = []

            wait_setups: List[
                Dict[str, Any]
            ] = []

            rejected_setups: List[
                Dict[str, Any]
            ] = []

            # IMPORTANT :
            #
            # Ancien comportement :
            #
            #     if READY:
            #         append()
            #         break
            #
            # Cela empêchait le moteur de détecter plusieurs opportunités
            # valides sur le même symbole.
            #
            # NOUVEAU :
            #
            # Toutes les opportunités sont examinées.
            #
            # Aucun quota.
            #
            # Aucun break après le premier signal.

            for setup in setups:

                try:

                    processed = await self.traiter_setup(
                        setup,
                        symbol=normalized,
                        candles=candles,
                        zones_result=zones_result,
                        context_result=context_result,
                        confluences_result=confluences_result,
                        cartographie_result=cartographie,
                        current_price=current_price,
                    )

                except asyncio.CancelledError:
                    raise

                except Exception as exc:

                    logger.exception(
                        "Erreur traitement setup %s : %s",
                        normalized,
                        exc,
                    )

                    processed = {
                        "status": "SETUP_ERROR",
                        "symbol": normalized,
                        "setup": setup,
                        "error": str(exc),
                        "auto_execution": False,
                    }

                if processed is None:
                    continue

                results.append(
                    processed
                )

                processed_status = str(
                    processed.get(
                        "status",
                        "",
                    )
                ).upper()

                # -------------------------------------------------------------
                # SIGNAL ACTIONNABLE
                # -------------------------------------------------------------

                if processed_status == READY_FOR_SIGNAL:

                    ready_signals.append(
                        processed
                    )

                # -------------------------------------------------------------
                # WAIT
                # -------------------------------------------------------------

                elif processed_status == DECISION_WAIT:

                    wait_setups.append(
                        processed
                    )

                # -------------------------------------------------------------
                # AUTRES REJETS TECHNIQUES / ANTI-SPAM
                # -------------------------------------------------------------

                else:

                    rejected_setups.append(
                        processed
                    )

            # =================================================================
            # TRI DES SIGNAUX
            # =================================================================
            #
            # Tous les signaux sont conservés.
            #
            # On les classe simplement du plus convaincant au moins
            # convaincant pour faciliter leur traitement par Telegram.
            #

            ready_signals.sort(
                key=lambda item: float(
                    item.get(
                        "decision_confidence",
                        0.0,
                    )
                    or 0.0
                ),
                reverse=True,
            )

            # =================================================================
            # STATUT GLOBAL
            # =================================================================

            if ready_signals:

                overall_status = READY_FOR_SIGNAL

            elif wait_setups:

                overall_status = DECISION_WAIT

            else:

                overall_status = "NO_SIGNAL"

            # =================================================================
            # RESULTAT FINAL
            # =================================================================

            result = {
                "status": overall_status,

                "symbol": normalized,

                "current_price": current_price,

                "cartographie": cartographie,

                "zones": zones_result,

                "contexte": context_result,

                "confluences": confluences_result,

                "setups": setups,

                "results": results,

                "signals": ready_signals,

                "ready_signals_count": len(
                    ready_signals
                ),

                "wait_count": len(
                    wait_setups
                ),

                "rejected_count": len(
                    rejected_setups
                ),

                "auto_execution": False,

                "decision_engine": {
                    "owner": "moteur2_decision.py",
                    "score_blocking": False,
                    "rr_blocking": False,
                    "m5_blocking": False,
                    "m1_blocking": False,
                    "signal_quota": None,
                    "forced_signal": False,
                },
            }

            self.last_analysis[
                normalized
            ] = result

            logger.info(
                "Analyse Engine 2 terminée : %s -> %s | "
                "setups=%d | signals=%d | wait=%d",
                normalized,
                overall_status,
                len(setups),
                len(ready_signals),
                len(wait_setups),
            )

            return result

    # ========================================================================
    # ANALYSE TOUS LES MARCHÉS
    # ========================================================================

    async def analyser_tous(
        self,
    ) -> Dict[str, Any]:

        results: Dict[
            str,
            Any,
        ] = {}

        for symbol in self.symbols:

            try:

                results[
                    symbol
                ] = await self.analyser_symbole(
                    symbol
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                logger.exception(
                    "Erreur analyse %s : %s",
                    symbol,
                    exc,
                )

                results[
                    symbol
                ] = {
                    "status": "ERROR",
                    "symbol": symbol,
                    "error": str(exc),
                    "auto_execution": False,
                }

        return results

    # ========================================================================
    # STREAM
    # ========================================================================

    async def start_stream(
        self,
    ) -> None:

        logger.info(
            "Démarrage du stream BiQuote..."
        )

        try:

            await self.stream.run()

        except asyncio.CancelledError:

            logger.info(
                "Stream BiQuote annulé proprement."
            )

            raise

        except Exception as exc:

            logger.exception(
                "Erreur non bloquante du stream BiQuote : %s",
                exc,
            )

        finally:

            logger.info(
                "Tâche stream BiQuote terminée."
            )

    # ========================================================================
    # RUN
    # ========================================================================

    async def run(
        self,
    ) -> None:

        if self.running:
            return

        self.running = True

        self._stream_task = (
            asyncio.create_task(
                self.start_stream()
            )
        )

        await asyncio.sleep(1)

        try:

            while self.running:

                try:

                    await self.analyser_tous()

                except asyncio.CancelledError:
                    raise

                except Exception as exc:

                    logger.exception(
                        "Erreur analyse globale : %s",
                        exc,
                    )

                await asyncio.sleep(
                    max(
                        1,
                        int(
                            SCAN_INTERVAL_SECONDS
                        ),
                    )
                )

        finally:

            self.running = False

            if self._stream_task is not None:

                self._stream_task.cancel()

                try:

                    await self._stream_task

                except asyncio.CancelledError:
                    pass

                except Exception:
                    pass

                self._stream_task = None

    # ========================================================================
    # STOP
    # ========================================================================

    async def stop(
        self,
    ) -> None:

        self.running = False

        # --------------------------------------------------------------------
        # ARRÊT STREAM
        # --------------------------------------------------------------------

        try:

            stop_method = getattr(
                self.stream,
                "stop",
                None,
            )

            if stop_method is not None:

                result = stop_method()

                if inspect.isawaitable(
                    result
                ):
                    await result

        except Exception as exc:

            logger.warning(
                "Erreur arrêt stream : %s",
                exc,
            )

        # --------------------------------------------------------------------
        # ANNULATION TÂCHE STREAM
        # --------------------------------------------------------------------

        if self._stream_task is not None:

            self._stream_task.cancel()

            try:

                await self._stream_task

            except asyncio.CancelledError:
                pass

            except Exception:
                pass

            self._stream_task = None

        # --------------------------------------------------------------------
        # FERMETURE BIQUOTE
        # --------------------------------------------------------------------

        try:

            close_method = getattr(
                self.biquote,
                "close",
                None,
            )

            if close_method is not None:

                result = close_method()

                if inspect.isawaitable(
                    result
                ):
                    await result

        except Exception as exc:

            logger.warning(
                "Erreur fermeture BiQuote : %s",
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

            decision_status = {
                "engine": "moteur2_decision.py",
            }

        return {
            "engine": ENGINE_NAME,

            "symbols": list(
                self.symbols
            ),

            "source": "BiQuote",

            "running": self.running,

            "timeframes": list(
                TIMEFRAMES
            ),

            "primary_timeframes": list(
                PRIMARY_TIMEFRAMES
            ),

            "confirmation_timeframes": list(
                CONFIRMATION_TIMEFRAMES
            ),

            # Références uniquement.
            "reference_rr": REFERENCE_RR,

            "reference_score": REFERENCE_SCORE,

            # Anciennes clés conservées pour compatibilité.
            "minimum_rr": REFERENCE_RR,

            "minimum_score": REFERENCE_SCORE,

            # Nouveaux comportements.
            "rr_blocking": False,

            "score_blocking": False,

            "m5_blocking": False,

            "m1_blocking": False,

            "validation_decides_trade": False,

            "risk_decides_trade": False,

            "decision_owner": (
                "moteur2_decision.py"
            ),

            "signal_quota": None,

            "forced_signals": False,

            "multiple_signals_per_scan": True,

            "auto_execution": False,

            "final_validation_owner": (
                "moteur2_validation.py"
            ),

            "antispam_after_decision": True,

            "registration_after_publication": True,

            "decision_engine": decision_status,

            "cache": cache_status,

            "antispam": antispam_status,

            "current_prices": dict(
                self.current_prices
            ),

            "last_analysis": dict(
                self.last_analysis
            ),

            "last_signal": dict(
                self.last_signal
            ),
        }


# ============================================================================
# COMPATIBILITÉ
# ============================================================================

async def analyser_xauusd() -> Dict[str, Any]:

    moteur = Moteur2(
        symbols=("XAUUSD",)
    )

    try:

        return await moteur.analyser_symbole(
            "XAUUSD"
        )

    finally:

        await moteur.stop()


# ============================================================================
# MAIN LOCAL
# ============================================================================

async def main() -> None:

    moteur = Moteur2()

    try:

        result = await moteur.analyser_tous()

        print(result)

    finally:

        await moteur.stop()


# ============================================================================
# EXÉCUTION DIRECTE
# ============================================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )