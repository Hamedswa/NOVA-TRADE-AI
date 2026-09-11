"""
NOVA TRADE AI - MOTEUR 2
Moteur déterministe multi-actifs basé exclusivement sur BiQuote.
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
IMPORTANT
---------
- Moteur 2 est indépendant du Moteur 1.
- BiQuote est la seule source de données.
- M5 est la confirmation principale.
- M1 est secondaire.
- RR minimum = 3.0.
- TP1 est obligatoire.
- Score minimum = 60.
- READY_FOR_SIGNAL est produit uniquement par
  moteur2_validation.py.
- L'anti-spam intervient uniquement après READY_FOR_SIGNAL.
- Aucun signal n'est exécuté automatiquement.
- Les superviseurs news/session restent indépendants.
- Aucun concept d'analyse interdit n'est utilisé ici.
"""
from __future__ import annotations
import asyncio
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
# ============================================================
# CONFIGURATION MOTEUR 2
# ============================================================
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
# ============================================================
# MOTEUR 2
# ============================================================
class Moteur2:
    """
    Moteur principal du second moteur de NOVA TRADE AI.
    Le moteur fonctionne indépendamment pour chaque symbole.
    Aucun symbole n'est utilisé comme fallback pour un autre.
    Chaque cycle :
        symbole
          ↓
        H4/H1/M15/M5/M1
          ↓
        analyse
          ↓
        validation
          ↓
        anti-spam
          ↓
        signal éventuel
    """
    SYMBOLS = SUPPORTED_SYMBOLS
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
    ) -> None:
        self.logger = logger
        # ----------------------------------------------------
        # SYMBOLES
        # ----------------------------------------------------
        requested_symbols = (
            symbols
            if symbols is not None
            else list(SUPPORTED_SYMBOLS)
        )
        normalized_symbols: List[str] = []
        for symbol in requested_symbols:
            normalized = self._normalize_symbol(
                symbol
            )
            if (
                normalized
                and normalized not in normalized_symbols
            ):
                normalized_symbols.append(
                    normalized
                )
        if not normalized_symbols:
            normalized_symbols = list(
                SUPPORTED_SYMBOLS
            )
        self.symbols = tuple(
            normalized_symbols
        )
        # ----------------------------------------------------
        # CLIENT BIQUOTE
        # ----------------------------------------------------
        self.biquote = BiQuoteClient()
        # ----------------------------------------------------
        # CACHE
        # ----------------------------------------------------
        self.cache = Moteur2Cache()
        # ----------------------------------------------------
        # STREAM TEMPS RÉEL
        #
        # Un seul flux pour les 4 actifs.
        # ----------------------------------------------------
        self.stream = BiQuoteStream(
            symbols=self.symbols,
            on_tick=self._handle_tick,
        )
        # ----------------------------------------------------
        # MODULES MOTEUR 2
        # ----------------------------------------------------
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
        # ----------------------------------------------------
        # ÉTAT GLOBAL
        # ----------------------------------------------------
        self.running = False
        self.last_error: Optional[str] = None
        # Dernière analyse par symbole.
        self.last_analysis: Dict[
            str,
            Dict[str, Any],
        ] = {}
        # Dernier signal par symbole.
        self.last_signal: Dict[
            str,
            Optional[Dict[str, Any]],
        ] = {
            symbol: None
            for symbol in self.symbols
        }
        # Dernier prix par symbole.
        self.current_prices: Dict[
            str,
            Optional[float],
        ] = {
            symbol: None
            for symbol in self.symbols
        }
        # Dernière erreur par symbole.
        self.symbol_errors: Dict[
            str,
            Optional[str],
        ] = {
            symbol: None
            for symbol in self.symbols
        }
        # Verrou d'analyse :
        # évite plusieurs analyses simultanées
        # du même moteur.
        self.analysis_lock = asyncio.Lock()
    # ========================================================
    # UTILITAIRES
    # ========================================================
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
        if isinstance(
            obj,
            dict,
        ):
            return obj.get(
                key,
                default,
            )
        return getattr(
            obj,
            key,
            default,
        )
    # ========================================================
    # PRIX TICK
    # ========================================================
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
        if isinstance(
            tick,
            dict,
        ):
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
    def _extract_tick_symbol(
        self,
        tick: Any,
    ) -> Optional[str]:
        candidates = (
            "symbol",
            "ticker",
            "instrument",
            "pair",
        )
        for key in candidates:
            value = self._get(
                tick,
                key,
                None,
            )
            symbol = self._normalize_symbol(
                value
            )
            if symbol:
                return symbol
        return None
    # ========================================================
    # TICK → CACHE
    # ========================================================
    async def _handle_tick(
        self,
        tick: Any,
    ) -> None:
        """
        Callback du flux temps réel BiQuote.
        Le tick est uniquement transmis au cache
        et utilisé comme prix courant.
        Aucun calcul de setup n'est effectué ici.
        """
        try:
            symbol = (
                self._extract_tick_symbol(
                    tick
                )
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
            # Mise à jour du cache.
            try:
                self.cache.update_tick(
                    tick
                )
            except Exception:
                self.logger.debug(
                    "Cache tick non mis à jour pour %s.",
                    symbol,
                    exc_info=True,
                )
        except Exception:
            self.logger.exception(
                "Erreur traitement tick BiQuote."
            )
    # ========================================================
    # PRIX COURANT
    # ========================================================
    async def _get_current_price(
        self,
        symbol: str,
    ) -> Optional[float]:
        """
        Priorité :
            1. dernier tick du stream ;
            2. cache ;
            3. dernier prix connu.
        Le REST get_tick() n'est pas utilisé comme
        source principale.
        """
        normalized = self._normalize_symbol(
            symbol
        )
        if normalized is None:
            return None
        # ----------------------------------------------------
        # Stream
        # ----------------------------------------------------
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
        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------
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
        # ----------------------------------------------------
        # Dernier prix connu
        # ----------------------------------------------------
        return self.current_prices.get(
            normalized
        )
    # ========================================================
    # DONNÉES OHLC
    # ========================================================
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
            try:
                candles = await asyncio.to_thread(
                    self.biquote.get_candles,
                    timeframe=timeframe,
                    symbol=normalized,
                    limit=CANDLE_LIMIT,
                    closed_only=True,
                )
                if not candles:
                    raise RuntimeError(
                        f"Aucune bougie {timeframe}"
                        f" pour {normalized}"
                    )
                data[
                    timeframe
                ] = candles
                self.logger.debug(
                    "BiQuote OHLC %s %s : %s bougies.",
                    normalized,
                    timeframe,
                    len(candles),
                )
            except Exception as exc:
                self.logger.error(
                    "Erreur BiQuote %s %s : %s",
                    normalized,
                    timeframe,
                    exc,
                )
                raise
        return data
    # ========================================================
    # CARTOGRAPHIE
    # ========================================================
    def _cartographier(
        self,
        symbol: str,
        donnees: Dict[str, List[Any]],
    ) -> Dict[str, Any]:
        try:
            return self.marche.analyser(
                donnees,
                symbol=symbol,
            )
        except TypeError:
            try:
                return self.marche.analyser(
                    donnees
                )
            except Exception:
                self.logger.exception(
                    "Erreur cartographie %s.",
                    symbol,
                )
                return {}
        except Exception:
            self.logger.exception(
                "Erreur cartographie %s.",
                symbol,
            )
            return {}
    # ========================================================
    # EXTRACTION SETUPS
    # ========================================================
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
            for key in (
                "setups",
                "candidates",
                "results",
            ):
                value = setups_result.get(
                    key
                )
                if isinstance(
                    value,
                    list,
                ):
                    return value
        return []
    # ========================================================
    # CREATION DU SIGNAL
    # ========================================================
    def _build_signal(
        self,
        symbol: str,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        validation_result: Any,
    ) -> Dict[str, Any]:
        """
        Construit uniquement l'objet de signal final.
        Aucun nouveau calcul n'est effectué ici.
        Le signal ne peut être construit qu'après
        READY_FOR_SIGNAL.
        """
        return {
            "engine": "MOTEUR_2",
            "symbol": symbol,
            "setup": setup,
            "risk": risk_plan,
            "confirmation": confirmation,
            "score": score_result,
            "validation": validation_result,
            "status": "READY_FOR_SIGNAL",
            "auto_execution": False,
            "timestamp": self._now(),
        }
    # ========================================================
    # TRAITEMENT D'UN SETUP
    # ========================================================
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
        result: Dict[str, Any] = {
            "symbol": symbol,
            "setup": setup,
            "risk": None,
            "confirmation": None,
            "score": None,
            "validation": None,
            "antispam": None,
            "signal": None,
            "status": "REJECTED",
        }
        # ----------------------------------------------------
        # RISK
        # ----------------------------------------------------
        try:
            risk_plans = (
                self.risk.analyser_setups(
                    setup,
                    zones_result,
                    donnees,
                    current_price,
                )
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
        if not risk_plans:
            result["reason"] = (
                "Aucun RiskPlan valide."
            )
            return result
        # Le Risk module peut retourner
        # une liste de plans.
        risk_plan = risk_plans[0]
        result["risk"] = risk_plan
        # ----------------------------------------------------
        # CONFIRMATION
        # ----------------------------------------------------
        try:
            confirmation_result = (
                self.confirmation.analyser(
                    setup,
                    donnees,
                    risk_plan,
                    symbol=symbol,
                )
            )
        except TypeError:
            try:
                confirmation_result = (
                    self.confirmation.analyser(
                        setup,
                        donnees,
                        risk_plan,
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
        # ----------------------------------------------------
        # SCORE
        # ----------------------------------------------------
        try:
            score_result = (
                self.score.analyser(
                    setup,
                    zones=zones_result,
                    context=contexte_result,
                    confluences=confluences_result,
                    confirmation=confirmation_result,
                    risk_plan=risk_plan,
                    symbol=symbol,
                )
            )
        except TypeError:
            try:
                score_result = (
                    self.score.analyser(
                        setup,
                        zones=zones_result,
                        context=contexte_result,
                        confluences=confluences_result,
                        confirmation=confirmation_result,
                        risk_plan=risk_plan,
                    )
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
        # ----------------------------------------------------
        # VALIDATION FINALE
        # ----------------------------------------------------
        try:
            validation_result = (
                self.validation.analyser(
                    setup=setup,
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
        result["status"] = (
            validation_status
        )
        # ----------------------------------------------------
        # PAS READY
        # ----------------------------------------------------
        if validation_status != (
            "READY_FOR_SIGNAL"
        ):
            result["reason"] = (
                self._get(
                    validation_result,
                    "reason",
                    "Validation non prête.",
                )
            )
            return result
        # ----------------------------------------------------
        # ANTISPAM
        # ----------------------------------------------------
        try:
            antispam_result = (
                self.antispam.verifier(
                    setup=setup,
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
            result["reason"] = (
                self._get(
                    antispam_result,
                    "reason",
                    "Signal bloqué par l'anti-spam.",
                )
            )
            return result
        # ----------------------------------------------------
        # SIGNAL FINAL
        # ----------------------------------------------------
        signal_result = self._build_signal(
            symbol=symbol,
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation_result,
            score_result=score_result,
            validation_result=validation_result,
        )
        result["signal"] = (
            signal_result
        )
        # ----------------------------------------------------
        # ENREGISTREMENT ANTISPAM
        # ----------------------------------------------------
        setup_id = (
            self._get(
                validation_result,
                "metadata",
                {},
            )
            or {}
        )
        setup_id = (
            setup_id.get(
                "setup_id"
            )
            if isinstance(
                setup_id,
                dict,
            )
            else None
        )
        try:
            self.antispam.enregistrer_signal(
                setup=setup,
                risk_plan=risk_plan,
                setup_id=(
                    setup_id
                    or self.antispam.generer_setup_id(
                        setup,
                        risk_plan,
                    )
                ),
                extra={
                    "symbol": symbol,
                    "validation_status": (
                        validation_status
                    ),
                },
            )
        except Exception:
            self.logger.exception(
                "Erreur enregistrement anti-spam %s.",
                symbol,
            )
        result["status"] = (
            "READY_FOR_SIGNAL"
        )
        return result
    # ========================================================
    # ANALYSE D'UN SYMBOLE
    # ========================================================
    async def analyser_symbole(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        normalized = self._normalize_symbol(
            symbol
        )
        if normalized is None:
            return {
                "symbol": symbol,
                "status": "ERROR",
                "error": (
                    "UNSUPPORTED_SYMBOL"
                ),
                "timestamp": self._now(),
            }
        self.symbol_errors[
            normalized
        ] = None
        try:
            # ------------------------------------------------
            # DONNÉES
            # ------------------------------------------------
            donnees = (
                await self._get_candles(
                    normalized
                )
            )
            missing = [
                tf
                for tf in REQUIRED_TIMEFRAMES
                if (
                    tf not in donnees
                    or not donnees[tf]
                )
            ]
            if missing:
                raise RuntimeError(
                    "Timeframes manquants : "
                    + ", ".join(missing)
                )
            # ------------------------------------------------
            # PRIX
            # ------------------------------------------------
            current_price = (
                await self._get_current_price(
                    normalized
                )
            )
            # ------------------------------------------------
            # CARTOGRAPHIE
            # ------------------------------------------------
            market_map = (
                self._cartographier(
                    normalized,
                    donnees,
                )
            )
            if not market_map:
                raise RuntimeError(
                    "Cartographie vide."
                )
            # ------------------------------------------------
            # ZONES
            # ------------------------------------------------
            zones_result = (
                self.zones.analyser(
                    market_map,
                    current_price=current_price,
                )
            )
            # ------------------------------------------------
            # CONTEXTE
            # ------------------------------------------------
            contexte_result = (
                self.contexte.analyser(
                    donnees,
                    zones_result,
                    symbol=normalized,
                )
            )
            # ------------------------------------------------
            # CONFLUENCES
            # ------------------------------------------------
            confluences_result = (
                self.confluences.analyser(
                    donnees,
                    zones_result,
                    contexte_result,
                    market_map=market_map,
                    symbol=normalized,
                )
            )
            # ------------------------------------------------
            # SETUPS
            # ------------------------------------------------
            setups_result = (
                self.setups.analyser(
                    zones_result,
                    confluences_result,
                    contexte_result,
                    donnees,
                    symbol=normalized,
                )
            )
            setups = self._extract_setups(
                setups_result
            )
            # ------------------------------------------------
            # TRAITEMENT
            # ------------------------------------------------
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
                processed.append(
                    item
                )
                if (
                    item.get("status")
                    == "READY_FOR_SIGNAL"
                ):
                    ready_signal = (
                        item
                    )
                    break
            # ------------------------------------------------
            # RESULTAT
            # ------------------------------------------------
            result = {
                "engine": "MOTEUR_2",
                "symbol": normalized,
                "timestamp": self._now(),
                "current_price": (
                    current_price
                ),
                "market_map": market_map,
                "zones": zones_result,
                "context": contexte_result,
                "confluences": (
                    confluences_result
                ),
                "setups": setups,
                "results": processed,
                "signal": (
                    ready_signal
                ),
                "status": (
                    "READY_FOR_SIGNAL"
                    if ready_signal
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
            self.last_error = str(
                exc
            )
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
    # ========================================================
    # ANALYSE TOUS LES ACTIFS
    # ========================================================
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
    # ========================================================
    # STREAM BIQUOTE
    # ========================================================
    async def start_stream(
        self,
    ) -> None:
        try:
            self.logger.info(
                "Démarrage flux temps réel BiQuote : %s",
                ", ".join(self.symbols),
            )
            await self.stream.run()
        except asyncio.CancelledError:
            self.logger.info(
                "Flux BiQuote Moteur 2 arrêté."
            )
            raise
        except Exception as exc:
            self.last_error = str(
                exc
            )
            self.logger.exception(
                "Erreur stream BiQuote : %s",
                exc,
            )
    # ========================================================
    # BOUCLE PRINCIPALE
    # ========================================================
    async def run(
        self,
    ) -> None:
        self.running = True
        self.logger.info(
            "NOVA TRADE AI — MOTEUR 2 démarré."
        )
        self.logger.info(
            "Actifs : %s",
            ", ".join(self.symbols),
        )
        self.logger.info(
            "Timeframes : H4 → H1 → M15 → M5 → M1"
        )
        self.logger.info(
            "RR minimum : 1:3"
        )
        # ----------------------------------------------------
        # STREAM UNIQUE
        # ----------------------------------------------------
        stream_task = asyncio.create_task(
            self.start_stream()
        )
        try:
            # Petit délai pour permettre
            # au flux de commencer à recevoir
            # les premiers ticks.
            await asyncio.sleep(
                1
            )
            # ------------------------------------------------
            # PREMIER SCAN
            # ------------------------------------------------
            async with self.analysis_lock:
                await self.analyser_tous()
            # ------------------------------------------------
            # BOUCLE
            # ------------------------------------------------
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
            self.last_error = str(
                exc
            )
            self.logger.exception(
                "Erreur boucle Moteur 2."
            )
        finally:
            self.running = False
            # ------------------------------------------------
            # ARRÊT STREAM
            # ------------------------------------------------
            if not stream_task.done():
                stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
            except Exception:
                self.logger.exception(
                    "Erreur fermeture stream."
                )
            # ------------------------------------------------
            # CLIENT BIQUOTE
            # ------------------------------------------------
            try:
                self.biquote.close()
            except Exception:
                self.logger.exception(
                    "Erreur fermeture client BiQuote."
                )
    # ========================================================
    # ARRÊT
    # ========================================================
    async def stop(
        self,
    ) -> None:
        self.running = False
        # ----------------------------------------------------
        # Stream
        # ----------------------------------------------------
        try:
            if hasattr(
                self.stream,
                "stop",
            ):
                result = (
                    self.stream.stop()
                )
                if asyncio.iscoroutine(
                    result
                ):
                    await result
        except Exception:
            self.logger.exception(
                "Erreur arrêt stream BiQuote."
            )
        # ----------------------------------------------------
        # Client
        # ----------------------------------------------------
        try:
            self.biquote.close()
        except Exception:
            self.logger.exception(
                "Erreur fermeture BiQuote."
            )
    # ========================================================
    # STATUT
    # ========================================================
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
            "final_validation_owner": (
                "moteur2_validation.py"
            ),
            "minimum_rr": 3.0,
            "minimum_score": 60.0,
            "m5_primary_confirmation": True,
            "m1_secondary_confirmation": True,
            "auto_execution": False,
        }
# ============================================================
# TEST AUTONOME
# ============================================================
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