"""
NOVA TRADE AI - MOTEUR 2
Orchestrateur principal du moteur déterministe multi-actifs.

Actifs :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD

Timeframes :
    H4
    H1
    M15
    M5
    M1

Pipeline :
    BiQuote
        ↓
    Cartographie marché
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
    Confirmation M5 / M1
        ↓
    Score
        ↓
    Validation finale
        ↓
    Anti-spam
        ↓
    Signal

RÈGLES :
    - BiQuote est la seule source de données.
    - Le moteur fonctionne indépendamment par symbole.
    - Aucun symbole ne sert de fallback à un autre.
    - H4 / H1 / M15 constituent le contexte principal.
    - M5 est la confirmation principale.
    - M1 est secondaire.
    - RR minimum = 3.0.
    - TP1 est obligatoire.
    - TP2 / TP3 sont facultatifs.
    - Score minimum = 60.
    - READY_FOR_SIGNAL est produit uniquement par
      moteur2_validation.py.
    - L'anti-spam intervient uniquement après READY_FOR_SIGNAL.
    - Aucun signal n'est exécuté automatiquement.
    - Les superviseurs news/session restent informatifs.
    - Le tracker reste observation-only.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from biquote_client import BiQuoteClient
from biquote_stream import BiQuoteStream

from moteur2_antispam import Moteur2AntiSpam
from moteur2_cache import Moteur2Cache
from moteur2_confirmation import Moteur2Confirmation
from moteur2_confluences import Moteur2Confluences
from moteur2_contexte import Moteur2Contexte
from moteur2_marche import Moteur2Marche
from moteur2_risk import Moteur2Risk
from moteur2_score import Moteur2Score
from moteur2_setups import Moteur2Setups
from moteur2_validation import Moteur2Validation
from moteur2_zones import Moteur2Zones


logger = logging.getLogger(__name__)


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

REQUIRED_TIMEFRAMES = TIMEFRAMES

CANDLE_LIMIT = 300

SCAN_INTERVAL_SECONDS = 60

MINIMUM_RR = 3.0

MINIMUM_SCORE = 60.0


# ============================================================================
# MOTEUR 2
# ============================================================================

class Moteur2:
    """
    Orchestrateur principal du moteur 2.

    Le moteur :
        - collecte les données BiQuote ;
        - construit l'analyse ;
        - détecte les setups ;
        - construit le RiskPlan ;
        - analyse M5/M1 ;
        - calcule le score ;
        - demande la validation finale ;
        - passe dans l'anti-spam uniquement si READY ;
        - publie un objet de signal interne.

    Le moteur ne réalise aucune exécution automatique.
    """

    SYMBOLS = SUPPORTED_SYMBOLS

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
    ) -> None:

        self.logger = logger

        # ====================================================================
        # SYMBOLES
        # ====================================================================

        requested_symbols = (
            symbols
            if symbols is not None
            else list(SUPPORTED_SYMBOLS)
        )

        normalized_symbols: List[str] = []

        for symbol in requested_symbols:

            normalized = self._normalize_symbol(symbol)

            if (
                normalized
                and normalized not in normalized_symbols
            ):
                normalized_symbols.append(normalized)

        if not normalized_symbols:
            normalized_symbols = list(SUPPORTED_SYMBOLS)

        self.symbols = tuple(normalized_symbols)

        # ====================================================================
        # CLIENT BIQUOTE
        # ====================================================================

        self.biquote = BiQuoteClient()

        # ====================================================================
        # CACHE
        # ====================================================================

        self.cache = Moteur2Cache()

        # ====================================================================
        # STREAM TEMPS RÉEL
        # ====================================================================

        self.stream = BiQuoteStream(
            symbols=self.symbols,
            on_tick=self._handle_tick,
        )

        # ====================================================================
        # MODULES
        # ====================================================================

        self.marche = Moteur2Marche()

        self.zones = Moteur2Zones()

        self.contexte = Moteur2Contexte()

        self.confluences = Moteur2Confluences()

        self.setups = Moteur2Setups()

        self.risk = Moteur2Risk(
            min_rr=MINIMUM_RR,
        )

        self.confirmation = Moteur2Confirmation()

        self.score = Moteur2Score(
            minimum_rr=MINIMUM_RR,
        )

        self.validation = Moteur2Validation()

        self.antispam = Moteur2AntiSpam()

        # ====================================================================
        # ÉTAT
        # ====================================================================

        self.running = False

        self.last_error: Optional[str] = None

        self.last_analysis: Dict[
            str,
            Dict[str, Any],
        ] = {}

        self.last_signal: Dict[
            str,
            Optional[Dict[str, Any]],
        ] = {
            symbol: None
            for symbol in self.symbols
        }

        self.current_prices: Dict[
            str,
            Optional[float],
        ] = {
            symbol: None
            for symbol in self.symbols
        }

        self.symbol_errors: Dict[
            str,
            Optional[str],
        ] = {
            symbol: None
            for symbol in self.symbols
        }

        self.analysis_lock = asyncio.Lock()

        self.stream_task: Optional[
            asyncio.Task
        ] = None

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> Optional[str]:

        if symbol is None:
            return None

        value = (
            str(symbol)
            .upper()
            .strip()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )

        if value in SUPPORTED_SYMBOLS:
            return value

        return None

    @staticmethod
    def _now() -> str:

        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:

        try:

            if value is None:
                return None

            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _get(
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:

        if obj is None:
            return default

        if isinstance(obj, dict):

            return obj.get(
                key,
                default,
            )

        return getattr(
            obj,
            key,
            default,
        )

    # ========================================================================
    # COPIE SETUP + SYMBOLE
    # ========================================================================

    def _prepare_setup(
        self,
        setup: Any,
        symbol: str,
    ) -> Any:
        """
        Garantit que le setup porte le symbole réellement analysé.

        Le module setup historique peut retourner un dictionnaire
        sans champ symbol ou avec un symbole par défaut.

        Ici nous ne modifions pas sa logique :
        nous préparons simplement une représentation compatible
        avec les modules Risk / Validation / Anti-spam.
        """

        if isinstance(setup, dict):

            prepared = dict(setup)

            prepared["symbol"] = symbol

            return prepared

        try:

            prepared = copy.copy(setup)

            setattr(
                prepared,
                "symbol",
                symbol,
            )

            return prepared

        except Exception:

            return {
                "setup_id": self._get(
                    setup,
                    "setup_id",
                    self._get(
                        setup,
                        "id",
                        "SETUP",
                    ),
                ),
                "zone_id": self._get(
                    setup,
                    "zone_id",
                    "",
                ),
                "setup_type": self._get(
                    setup,
                    "setup_type",
                    self._get(
                        setup,
                        "type",
                        "UNKNOWN",
                    ),
                ),
                "direction": self._get(
                    setup,
                    "direction",
                    self._get(
                        setup,
                        "bias",
                        "",
                    ),
                ),
                "zone_price": self._get(
                    setup,
                    "zone_price",
                    0.0,
                ),
                "timeframe": self._get(
                    setup,
                    "timeframe",
                    "M15",
                ),
                "confidence": self._get(
                    setup,
                    "confidence",
                    0.0,
                ),
                "context": self._get(
                    setup,
                    "context",
                    "",
                ),
                "reason": self._get(
                    setup,
                    "reason",
                    "",
                ),
                "entry_ready": self._get(
                    setup,
                    "entry_ready",
                    False,
                ),
                "waiting_for_confirmation": self._get(
                    setup,
                    "waiting_for_confirmation",
                    True,
                ),
                "supporting_confluences": self._get(
                    setup,
                    "supporting_confluences",
                    [],
                ),
                "opposing_confluences": self._get(
                    setup,
                    "opposing_confluences",
                    [],
                ),
                "symbol": symbol,
            }

    # ========================================================================
    # EXTRACTION PRIX
    # ========================================================================

    def _extract_price(
        self,
        tick: Any,
    ) -> Optional[float]:

        if tick is None:
            return None

        keys = (
            "mid",
            "price",
            "last",
            "close",
        )

        if isinstance(tick, dict):

            for key in keys:

                value = self._safe_float(
                    tick.get(key)
                )

                if value is not None:
                    return value

            bid = self._safe_float(
                tick.get("bid")
            )

            ask = self._safe_float(
                tick.get("ask")
            )

            if (
                bid is not None
                and ask is not None
            ):
                return (
                    bid + ask
                ) / 2.0

            return None

        for key in keys:

            value = self._safe_float(
                getattr(
                    tick,
                    key,
                    None,
                )
            )

            if value is not None:
                return value

        bid = self._safe_float(
            getattr(
                tick,
                "bid",
                None,
            )
        )

        ask = self._safe_float(
            getattr(
                tick,
                "ask",
                None,
            )
        )

        if (
            bid is not None
            and ask is not None
        ):
            return (
                bid + ask
            ) / 2.0

        return None

    # ========================================================================
    # EXTRACTION SYMBOLE TICK
    # ========================================================================

    def _extract_tick_symbol(
        self,
        tick: Any,
    ) -> Optional[str]:

        for key in (
            "symbol",
            "ticker",
            "instrument",
            "pair",
        ):

            value = self._get(
                tick,
                key,
                None,
            )

            normalized = self._normalize_symbol(
                value
            )

            if normalized:
                return normalized

        return None

    # ========================================================================
    # TICK → CACHE
    # ========================================================================

    async def _handle_tick(
        self,
        tick: Any,
    ) -> None:

        try:

            symbol = self._extract_tick_symbol(
                tick
            )

            if symbol is None:
                return

            price = self._extract_price(
                tick
            )

            if price is None:
                return

            self.current_prices[
                symbol
            ] = price

            try:

                self.cache.update_tick(
                    tick
                )

            except Exception:

                self.logger.debug(
                    "Impossible de mettre à jour "
                    "le cache tick pour %s.",
                    symbol,
                    exc_info=True,
                )

        except Exception:

            self.logger.exception(
                "Erreur traitement tick BiQuote."
            )

    # ========================================================================
    # PRIX COURANT
    # ========================================================================

    async def _get_current_price(
        self,
        symbol: str,
    ) -> Optional[float]:

        normalized = self._normalize_symbol(
            symbol
        )

        if normalized is None:
            return None

        # --------------------------------------------------------------------
        # 1. STREAM
        # --------------------------------------------------------------------

        try:

            tick = (
                self.stream.get_latest_tick(
                    normalized
                )
            )

            price = self._extract_price(
                tick
            )

            if price is not None:

                self.current_prices[
                    normalized
                ] = price

                return price

        except Exception:

            self.logger.debug(
                "Prix stream indisponible pour %s.",
                normalized,
                exc_info=True,
            )

        # --------------------------------------------------------------------
        # 2. CACHE
        # --------------------------------------------------------------------

        try:

            price = self._safe_float(
                self.cache.get_current_price(
                    normalized
                )
            )

            if price is not None:

                self.current_prices[
                    normalized
                ] = price

                return price

        except Exception:

            self.logger.debug(
                "Prix cache indisponible pour %s.",
                normalized,
                exc_info=True,
            )

        # --------------------------------------------------------------------
        # 3. DERNIER PRIX CONNU
        # --------------------------------------------------------------------

        return self.current_prices.get(
            normalized
        )

    # ========================================================================
    # DONNÉES OHLC
    # ========================================================================

    async def _get_candles(
        self,
        symbol: str,
    ) -> Dict[str, List[Any]]:

        normalized = self._normalize_symbol(
            symbol
        )

        if normalized is None:

            raise ValueError(
                f"Symbole non supporté : {symbol}"
            )

        data: Dict[
            str,
            List[Any],
        ] = {}

        for timeframe in TIMEFRAMES:

            candles = await asyncio.to_thread(
                self.biquote.get_candles,
                timeframe=timeframe,
                symbol=normalized,
                limit=CANDLE_LIMIT,
                closed_only=True,
            )

            if not candles:

                raise RuntimeError(
                    f"Aucune bougie {timeframe} "
                    f"pour {normalized}"
                )

            data[
                timeframe
            ] = candles

        return data

    # ========================================================================
    # EXTRACTION SETUPS
    # ========================================================================

    @staticmethod
    def _extract_setups(
        setups_result: Any,
    ) -> List[Any]:

        if setups_result is None:
            return []

        if isinstance(
            setups_result,
            list,
        ):
            return setups_result

        if isinstance(
            setups_result,
            tuple,
        ):
            return list(
                setups_result
            )

        if isinstance(
            setups_result,
            dict,
        ):

            setups = setups_result.get(
                "setups"
            )

            if isinstance(
                setups,
                list,
            ):
                return setups

        return []

    # ========================================================================
    # BUILD SIGNAL
    # ========================================================================

    def _build_signal(
        self,
        symbol: str,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        validation_result: Any,
        antispam_result: Any,
    ) -> Dict[str, Any]:

        validation_metadata = (
            self._get(
                validation_result,
                "metadata",
                {},
            )
            or {}
        )

        return {
            "engine": "MOTEUR_2",
            "symbol": symbol,
            "setup": setup,
            "risk": risk_plan,
            "confirmation": confirmation,
            "score": score_result,
            "validation": validation_result,
            "antispam": antispam_result,
            "status": "READY_FOR_SIGNAL",
            "auto_execution": False,
            "timestamp": self._now(),
            "metadata": {
                "final_validation_owner": (
                    "moteur2_validation.py"
                ),
                "validation_metadata": (
                    validation_metadata
                ),
                "minimum_rr": MINIMUM_RR,
                "minimum_score": MINIMUM_SCORE,
                "m5_primary": True,
                "m1_secondary": True,
            },
        }

    # ========================================================================
    # TRAITEMENT D'UN SETUP
    # ========================================================================

    async def traiter_setup(
        self,
        symbol: str,
        setup: Any,
        zones_result: Dict[str, Any],
        contexte_result: Dict[str, Any],
        confluences_result: Dict[str, Any],
        donnees: Dict[str, List[Any]],
        current_price: Optional[float],
    ) -> Dict[str, Any]:

        prepared_setup = self._prepare_setup(
            setup,
            symbol,
        )

        result: Dict[str, Any] = {
            "symbol": symbol,
            "setup": prepared_setup,
            "risk": None,
            "confirmation": None,
            "score": None,
            "validation": None,
            "antispam": None,
            "signal": None,
            "status": "REJECTED",
        }

        # ====================================================================
        # RISK
        # ====================================================================

        try:

            risk_plan = self.risk.analyser_setup(
                setup=prepared_setup,
                zones=zones_result,
                candles=donnees,
                current_price=current_price,
                symbol=symbol,
            )

        except Exception as exc:

            self.logger.exception(
                "Erreur Risk %s.",
                symbol,
            )

            result["reason"] = (
                f"RISK_ERROR: {exc}"
            )

            return result

        result["risk"] = risk_plan

        if risk_plan is None:

            result["reason"] = (
                "RiskPlan indisponible."
            )

            return result

        risk_valid = self._get(
            risk_plan,
            "valid",
            False,
        )

        if risk_valid is False:

            result["reason"] = self._get(
                risk_plan,
                "reason",
                "RiskPlan invalide.",
            )

            return result

        # ====================================================================
        # CONFIRMATION M5 / M1
        # ====================================================================

        try:

            confirmation_result = (
                self.confirmation.analyser(
                    prepared_setup,
                    donnees,
                    risk_plan,
                    symbol=symbol,
                )
            )

        except Exception as exc:

            self.logger.exception(
                "Erreur Confirmation %s.",
                symbol,
            )

            result["reason"] = (
                f"CONFIRMATION_ERROR: {exc}"
            )

            return result

        result["confirmation"] = (
            confirmation_result
        )

        # ====================================================================
        # SCORE
        # ====================================================================

        try:

            score_result = self.score.analyser(
                prepared_setup,
                zones=zones_result,
                context=contexte_result,
                confluences=confluences_result,
                confirmation=confirmation_result,
                risk_plan=risk_plan,
                symbol=symbol,
            )

        except Exception as exc:

            self.logger.exception(
                "Erreur Score %s.",
                symbol,
            )

            result["reason"] = (
                f"SCORE_ERROR: {exc}"
            )

            return result

        result["score"] = score_result

        # ====================================================================
        # VALIDATION FINALE
        # ====================================================================

        try:

            validation_result = (
                self.validation.analyser(
                    setup=prepared_setup,
                    risk_plan=risk_plan,
                    confirmation=confirmation_result,
                    score_result=score_result,
                    context=contexte_result,
                    confluences=confluences_result,
                )
            )

        except Exception as exc:

            self.logger.exception(
                "Erreur Validation %s.",
                symbol,
            )

            result["reason"] = (
                f"VALIDATION_ERROR: {exc}"
            )

            return result

        result["validation"] = (
            validation_result
        )

        validation_status = str(
            self._get(
                validation_result,
                "status",
                "REJECTED",
            )
        ).upper().strip()

        result["status"] = validation_status

        # ====================================================================
        # READY UNIQUEMENT
        # ====================================================================

        if (
            validation_status
            != "READY_FOR_SIGNAL"
        ):

            result["reason"] = self._get(
                validation_result,
                "reason",
                "Validation non prête.",
            )

            return result

        validation_valid = bool(
            self._get(
                validation_result,
                "valid",
                False,
            )
        )

        if not validation_valid:

            result["status"] = "REJECTED"

            result["reason"] = (
                "READY_FOR_SIGNAL reçu "
                "sans validation.valid=True."
            )

            return result

        # ====================================================================
        # ANTISPAM
        # ====================================================================

        try:

            antispam_result = (
                self.antispam.verifier(
                    setup=prepared_setup,
                    risk_plan=risk_plan,
                    validation=validation_result,
                )
            )

        except Exception as exc:

            self.logger.exception(
                "Erreur Anti-spam %s.",
                symbol,
            )

            result["reason"] = (
                f"ANTISPAM_ERROR: {exc}"
            )

            return result

        result["antispam"] = (
            antispam_result
        )

        allowed = bool(
            self._get(
                antispam_result,
                "allowed",
                False,
            )
        )

        if not allowed:

            result["status"] = (
                "ANTISPAM_BLOCKED"
            )

            result["reason"] = self._get(
                antispam_result,
                "reason",
                "Signal bloqué par l'anti-spam.",
            )

            return result

        # ====================================================================
        # SIGNAL FINAL
        # ====================================================================

        signal_result = self._build_signal(
            symbol=symbol,
            setup=prepared_setup,
            risk_plan=risk_plan,
            confirmation=confirmation_result,
            score_result=score_result,
            validation_result=validation_result,
            antispam_result=antispam_result,
        )

        result["signal"] = signal_result

        # ====================================================================
        # ENREGISTREMENT ANTISPAM
        # ====================================================================

        setup_id = self._get(
            antispam_result,
            "setup_id",
            None,
        )

        if not setup_id:

            setup_id = (
                self.antispam.generer_setup_id(
                    prepared_setup,
                    risk_plan,
                )
            )

        try:

            self.antispam.enregistrer_signal(
                setup=prepared_setup,
                risk_plan=risk_plan,
                setup_id=setup_id,
                extra={
                    "symbol": symbol,
                    "validation_status": (
                        validation_status
                    ),
                    "score": self._get(
                        score_result,
                        "score",
                        None,
                    ),
                    "rr": self._get(
                        risk_plan,
                        "primary_rr",
                        None,
                    ),
                },
            )

        except Exception:

            self.logger.exception(
                "Erreur enregistrement anti-spam %s.",
                symbol,
            )

            # Le signal reste READY :
            # l'échec de l'enregistrement ne doit pas
            # créer une nouvelle décision de trading.

        result["status"] = (
            "READY_FOR_SIGNAL"
        )

        return result

    # ========================================================================
    # ANALYSE D'UN SYMBOLE
    # ========================================================================

    async def analyser_symbole(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        normalized = self._normalize_symbol(
            symbol
        )

        if normalized is None:

            return {
                "engine": "MOTEUR_2",
                "symbol": symbol,
                "status": "ERROR",
                "error": "UNSUPPORTED_SYMBOL",
                "timestamp": self._now(),
            }

        self.symbol_errors[
            normalized
        ] = None

        try:

            # ================================================================
            # DONNÉES
            # ================================================================

            donnees = await self._get_candles(
                normalized
            )

            missing = [
                timeframe
                for timeframe in REQUIRED_TIMEFRAMES
                if (
                    timeframe not in donnees
                    or not donnees[timeframe]
                )
            ]

            if missing:

                raise RuntimeError(
                    "Timeframes manquants : "
                    + ", ".join(missing)
                )

            # ================================================================
            # PRIX
            # ================================================================

            current_price = (
                await self._get_current_price(
                    normalized
                )
            )

            # ================================================================
            # CARTOGRAPHIE
            # ================================================================

            market_map = self.marche.analyser(
                donnees,
                symbol=normalized,
            )

            if not market_map:

                raise RuntimeError(
                    "Cartographie vide."
                )

            # ================================================================
            # ZONES
            # ================================================================

            zones_result = self.zones.analyser(
                market_map,
                current_price=current_price,
            )

            # ================================================================
            # CONTEXTE
            # ================================================================

            contexte_result = (
                self.contexte.analyser(
                    donnees,
                    zones_result,
                    symbol=normalized,
                )
            )

            # ================================================================
            # CONFLUENCES
            # ================================================================

            confluences_result = (
                self.confluences.analyser(
                    donnees,
                    zones_result,
                    contexte_result,
                    market_map=market_map,
                    symbol=normalized,
                )
            )

            # ================================================================
            # SETUPS
            # ================================================================

            setups_result = self.setups.analyser(
                zones_result=zones_result,
                confluences_result=confluences_result,
                context_result=contexte_result,
                candles_by_timeframe=donnees,
            )

            setups = self._extract_setups(
                setups_result
            )

            # ================================================================
            # TRAITEMENT
            # ================================================================

            processed: List[
                Dict[str, Any]
            ] = []

            ready_signal: Optional[
                Dict[str, Any]
            ] = None

            for setup in setups:

                item = await self.traiter_setup(
                    symbol=normalized,
                    setup=setup,
                    zones_result=zones_result,
                    contexte_result=contexte_result,
                    confluences_result=confluences_result,
                    donnees=donnees,
                    current_price=current_price,
                )

                processed.append(item)

                if (
                    item.get("status")
                    == "READY_FOR_SIGNAL"
                ):

                    ready_signal = item

                    break

            # ================================================================
            # RESULTAT
            # ================================================================

            result = {
                "engine": "MOTEUR_2",
                "symbol": normalized,
                "timestamp": self._now(),
                "current_price": current_price,
                "market_map": market_map,
                "zones": zones_result,
                "context": contexte_result,
                "confluences": confluences_result,
                "setups": setups,
                "results": processed,
                "signal": ready_signal,
                "status": (
                    "READY_FOR_SIGNAL"
                    if ready_signal is not None
                    else "NO_SIGNAL"
                ),
            }

            self.last_analysis[
                normalized
            ] = result

            if ready_signal is not None:

                self.last_signal[
                    normalized
                ] = ready_signal

            return result

        except Exception as exc:

            self.symbol_errors[
                normalized
            ] = str(exc)

            self.last_error = str(exc)

            self.logger.exception(
                "Erreur analyse %s.",
                normalized,
            )

            result = {
                "engine": "MOTEUR_2",
                "symbol": normalized,
                "timestamp": self._now(),
                "status": "ERROR",
                "error": str(exc),
            }

            self.last_analysis[
                normalized
            ] = result

            return result

    # ========================================================================
    # ANALYSE TOUS LES ACTIFS
    # ========================================================================

    async def analyser_tous(
        self,
    ) -> Dict[str, Dict[str, Any]]:

        results: Dict[
            str,
            Dict[str, Any],
        ] = {}

        for symbol in self.symbols:

            results[
                symbol
            ] = await self.analyser_symbole(
                symbol
            )

        return results

    # ========================================================================
    # STREAM BIQUOTE
    # ========================================================================

    async def start_stream(
        self,
    ) -> None:

        try:

            self.logger.info(
                "Démarrage flux BiQuote : %s",
                ", ".join(self.symbols),
            )

            await self.stream.run()

        except asyncio.CancelledError:

            self.logger.info(
                "Flux BiQuote Moteur 2 arrêté."
            )

            raise

        except Exception as exc:

            self.last_error = str(exc)

            self.logger.exception(
                "Erreur stream BiQuote."
            )

    # ========================================================================
    # BOUCLE PRINCIPALE
    # ========================================================================

    async def run(
        self,
    ) -> None:

        if self.running:
            return

        self.running = True

        self.logger.info(
            "========================================"
        )

        self.logger.info(
            "NOVA TRADE AI — MOTEUR 2"
        )

        self.logger.info(
            "========================================"
        )

        self.logger.info(
            "BiQuote : source unique"
        )

        self.logger.info(
            "Actifs : %s",
            ", ".join(self.symbols),
        )

        self.logger.info(
            "Timeframes : H4 → H1 → M15 → M5 → M1"
        )

        self.logger.info(
            "RR minimum : %.1fR",
            MINIMUM_RR,
        )

        self.logger.info(
            "Score minimum : %.0f",
            MINIMUM_SCORE,
        )

        self.logger.info(
            "M5 : confirmation principale"
        )

        self.logger.info(
            "M1 : confirmation secondaire"
        )

        self.logger.info(
            "Auto-exécution : OFF"
        )

        # ====================================================================
        # STREAM UNIQUE
        # ====================================================================

        self.stream_task = asyncio.create_task(
            self.start_stream()
        )

        try:

            await asyncio.sleep(1)

            # ================================================================
            # PREMIER SCAN
            # ================================================================

            async with self.analysis_lock:

                await self.analyser_tous()

            # ================================================================
            # BOUCLE
            # ================================================================

            while self.running:

                await asyncio.sleep(
                    SCAN_INTERVAL_SECONDS
                )

                if not self.running:
                    break

                async with self.analysis_lock:

                    await self.analyser_tous()

        except asyncio.CancelledError:

            self.logger.info(
                "Moteur 2 annulé."
            )

            raise

        except Exception as exc:

            self.last_error = str(exc)

            self.logger.exception(
                "Erreur boucle Moteur 2."
            )

        finally:

            self.running = False

            if (
                self.stream_task is not None
                and not self.stream_task.done()
            ):

                self.stream_task.cancel()

                try:

                    await self.stream_task

                except asyncio.CancelledError:
                    pass

                except Exception:

                    self.logger.exception(
                        "Erreur fermeture stream."
                    )

            self.stream_task = None

            try:

                self.biquote.close()

            except Exception:

                self.logger.exception(
                    "Erreur fermeture client BiQuote."
                )

    # ========================================================================
    # ARRÊT
    # ========================================================================

    async def stop(
        self,
    ) -> None:

        self.running = False

        # --------------------------------------------------------------------
        # STREAM
        # --------------------------------------------------------------------

        try:

            if hasattr(
                self.stream,
                "stop",
            ):

                stop_result = (
                    self.stream.stop()
                )

                if asyncio.iscoroutine(
                    stop_result
                ):

                    await stop_result

        except Exception:

            self.logger.exception(
                "Erreur arrêt stream BiQuote."
            )

        # --------------------------------------------------------------------
        # TASK STREAM
        # --------------------------------------------------------------------

        if (
            self.stream_task is not None
            and not self.stream_task.done()
        ):

            self.stream_task.cancel()

            try:

                await self.stream_task

            except asyncio.CancelledError:
                pass

            except Exception:

                self.logger.exception(
                    "Erreur arrêt tâche stream."
                )

        self.stream_task = None

        # --------------------------------------------------------------------
        # CLIENT BIQUOTE
        # --------------------------------------------------------------------

        try:

            self.biquote.close()

        except Exception:

            self.logger.exception(
                "Erreur fermeture BiQuote."
            )

    # ========================================================================
    # STATUT
    # ========================================================================

    def get_status(
        self,
    ) -> Dict[str, Any]:

        return {
            "engine": "MOTEUR_2",
            "data_source": "BiQuote",
            "symbols": list(
                self.symbols
            ),
            "timeframes": list(
                TIMEFRAMES
            ),
            "running": self.running,
            "current_prices": dict(
                self.current_prices
            ),
            "last_error": self.last_error,
            "symbol_errors": dict(
                self.symbol_errors
            ),
            "last_analysis": dict(
                self.last_analysis
            ),
            "last_signal": dict(
                self.last_signal
            ),
            "minimum_rr": MINIMUM_RR,
            "minimum_score": MINIMUM_SCORE,
            "tp1_required": True,
            "tp2_optional": True,
            "tp3_optional": True,
            "m5_primary_confirmation": True,
            "m1_secondary_confirmation": True,
            "final_validation_owner": (
                "moteur2_validation.py"
            ),
            "auto_execution": False,
            "news_supervisor_can_block": False,
            "session_supervisor_can_block": False,
            "tracker_can_modify_signal": False,
        }


# ============================================================================
# TEST / ENTRYPOINT
# ============================================================================

async def main() -> None:

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )

    moteur = Moteur2()

    try:

        await moteur.run()

    except KeyboardInterrupt:

        pass

    finally:

        await moteur.stop()


if __name__ == "__main__":

    asyncio.run(main())