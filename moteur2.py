"""
NOVA TRADE AI - ENGINE 2
moteur2.py
Orchestrateur principal du moteur 2.
Pipeline :
BiQuote -> Stream/Cache -> Cartographie -> Zones -> Contexte ->
Confluences -> Setups -> Risk -> Confirmation M5/M1 ->
Score -> Validation -> Anti-spam -> Publication Telegram ->
Enregistrement du signal publié.
Regles :
- XAUUSD / BTCUSD / EURUSD / GBPUSD
- H4 -> H1 -> M15 -> M5 -> M1
- RR minimum 1:3
- Score minimum 60
- M5 = confirmation principale
- M1 = confirmation secondaire
- READY_FOR_SIGNAL appartient exclusivement a moteur2_validation.py
- News / sessions / tracker : informatifs uniquement
- Auto-execution desactivee
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
from moteur2_antispam import Moteur2AntiSpam

logger = logging.getLogger("NOVA_ENGINE_2")

# =====================================================================
# CONFIGURATION LOCALE
# =====================================================================

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
MINIMUM_RR = 3.0
MINIMUM_SCORE = 60.0
READY_FOR_SIGNAL = "READY_FOR_SIGNAL"

# =====================================================================
# NORMALISATION SYMBOLE
# =====================================================================

def _normalize_symbol(symbol: Any) -> str:
    """
    Normalise un symbole sans aucun fallback automatique.
    Un symbole inconnu reste inconnu et sera rejete.
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


# =====================================================================
# MOTEUR 2
# =====================================================================

class Moteur2:
    """
    Orchestrateur principal du moteur 2.
    Le moteur coordonne les differents modules.
    Il ne remplace pas leurs responsabilites :
    - validation finale -> moteur2_validation.py
    - anti-spam -> moteur2_antispam.py
    - publication -> couche Telegram
    - suivi -> tracker/runtime
    - execution automatique -> desactivee
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
                f"Symboles non supportes : {invalid_symbols}"
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

        # =============================================================
        # DATA PROVIDER
        # =============================================================

        self.biquote = BiQuoteClient()

        # =============================================================
        # CACHE
        # =============================================================

        self.cache = Moteur2Cache(
            client=self.biquote,
            symbols=self.symbols,
        )

        # =============================================================
        # STREAM TEMPS REEL
        # =============================================================

        self.stream = BiQuoteStream(
            symbols=self.symbols,
            on_tick=self._handle_tick,
        )

        # =============================================================
        # MODULES
        # =============================================================

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

        # La version de Moteur2Validation chargee par Railway
        # n'accepte pas d'argument dans son constructeur.
        self.validation = Moteur2Validation()

        self.antispam = Moteur2AntiSpam()

        # =============================================================
        # ETAT
        # =============================================================

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

        # Une seule analyse a la fois.
        self.analysis_lock = asyncio.Lock()

    # =================================================================
    # UTILITAIRE GENERIQUE
    # =================================================================

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
        """
        Appelle correctement une fonction synchrone
        ou asynchrone.
        """

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

    # =================================================================
    # TICK TEMPS REEL
    # =================================================================

    async def _handle_tick(
        self,
        tick: Any,
    ) -> None:
        """
        Recoit un tick BiQuote.
        Aucun calcul de setup ou de signal n'est effectue ici.
        """

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
                "Erreur mise a jour tick cache %s : %s",
                symbol,
                exc,
            )

    # =================================================================
    # PRIX COURANT
    # =================================================================

    def _get_current_price(
        self,
        symbol: str,
    ) -> Optional[float]:

        normalized = _normalize_symbol(
            symbol
        )

        # -------------------------------------------------------------
        # 1. Stream temps reel
        # -------------------------------------------------------------

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

        # -------------------------------------------------------------
        # 2. Cache
        # -------------------------------------------------------------

        try:
            price = self.cache.get_current_price(
                normalized
            )

            if price is not None:
                return float(price)

        except Exception:
            pass

        # -------------------------------------------------------------
        # 3. Dernier prix connu
        # -------------------------------------------------------------

        return self.current_prices.get(
            normalized
        )

    # =================================================================
    # RAFRAICHISSEMENT CACHE
    # =================================================================

    async def _refresh_symbol_cache(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Rafraichit les cinq timeframes via le cache.
        IMPORTANT :
        refresh_symbol() est une coroutine.
        Elle ne doit PAS etre placee dans asyncio.to_thread().
        """

        normalized = _normalize_symbol(
            symbol
        )

        result = await self.cache.refresh_symbol(
            normalized,
            force=False,
        )

        return result or {}

    # =================================================================
    # LECTURE CACHE
    # =================================================================

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

    # =================================================================
    # CHANDELIERS
    # =================================================================

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

    # =================================================================
    # EXTRACTION SETUPS
    # =================================================================

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

    # =================================================================
    # TRAITEMENT D'UN SETUP
    # =================================================================

    async def traiter_setup(
        self,
        setup: Any,
        *,
        symbol: str,
        candles: Dict[str, Any],
        zones_result: Any,
        context_result: Any,
        confluences_result: Any,
        current_price: Optional[float],
    ) -> Optional[Dict[str, Any]]:

        normalized = _normalize_symbol(
            symbol
        )

        # =============================================================
        # RISK
        # =============================================================

        risk_plan = self.risk.analyser_setup(
            setup=setup,
            zones=zones_result,
            candles=candles,
            current_price=current_price,
            symbol=normalized,
        )

        # =============================================================
        # CONFIRMATION M5 / M1
        # =============================================================

        confirmation_result = (
            self.confirmation.analyser(
                setup=setup,
                candles=candles,
                risk_plan=risk_plan,
                symbol=normalized,
            )
        )

        # =============================================================
        # SCORE
        # =============================================================

        score_result = self.score.analyser(
            setup=setup,
            zones=zones_result,
            context=context_result,
            confluences=confluences_result,
            confirmation=confirmation_result,
            risk_plan=risk_plan,
            symbol=normalized,
        )

        # =============================================================
        # VALIDATION FINALE
        # =============================================================

        # READY_FOR_SIGNAL appartient exclusivement
        # a moteur2_validation.py.

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

        # =============================================================
        # SCORE
        # =============================================================

        score_value = self._get(
            score_result,
            "score",
            0.0,
        )

        try:
            score_value = float(
                score_value or 0.0
            )

        except (
            TypeError,
            ValueError,
        ):
            score_value = 0.0

        # =============================================================
        # SCORE INSUFFISANT
        # =============================================================

        if score_value < MINIMUM_SCORE:
            return {
                "status": "REJECTED_SCORE",
                "symbol": normalized,
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation_result,
                "score": score_result,
                "validation": validation_result,
                "auto_execution": False,
            }

        # =============================================================
        # VALIDATION NON READY
        # =============================================================

        if (
            validation_status
            != READY_FOR_SIGNAL
            or not validation_valid
        ):
            return {
                "status": (
                    validation_status
                    or "NOT_READY"
                ),
                "symbol": normalized,
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation_result,
                "score": score_result,
                "validation": validation_result,
                "auto_execution": False,
            }

        # =============================================================
        # ANTI-SPAM
        # =============================================================

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
                "antispam": antispam_result,
                "auto_execution": False,
            }

        # =============================================================
        # READY FOR TELEGRAM
        # =============================================================

        setup_id = self._get(
            antispam_result,
            "setup_id",
            None,
        )

        if not setup_id:
            setup_id = self.antispam.generer_setup_id(
                setup,
                risk_plan,
            )

        signal = {
            "status": READY_FOR_SIGNAL,
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

        self.last_signal[
            normalized
        ] = signal

        return signal

    # =================================================================
    # ENREGISTREMENT APRES PUBLICATION
    # =================================================================

    def enregistrer_signal_publie(
        self,
        signal: Any,
    ) -> Optional[str]:
        """
        Enregistre un signal UNIQUEMENT apres sa publication reussie.
        Cette methode doit etre appelee par la couche Telegram
        apres l'envoi reel du message.
        Elle ne cree pas de nouveau signal.
        Elle ne modifie pas Entry / SL / TP.
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
                "Erreur enregistrement signal publie : %s",
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

    # =================================================================
    # ANALYSE D'UN SYMBOLE
    # =================================================================

    async def analyser_symbole(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        normalized = _normalize_symbol(
            symbol
        )

        if normalized not in self.symbols:
            raise ValueError(
                f"Symbole non configure : {normalized}"
            )

        async with self.analysis_lock:

            logger.info(
                "Analyse Engine 2 : %s",
                normalized,
            )

            # =========================================================
            # DONNEES
            # =========================================================

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

            # =========================================================
            # PRIX COURANT
            # =========================================================

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

            # =========================================================
            # CARTOGRAPHIE
            # =========================================================

            cartographie = self.marche.analyser(
                candles,
                symbol=normalized,
            )

            # =========================================================
            # ZONES
            # =========================================================

            zones_result = self.zones.analyser(
                cartographie,
                current_price=current_price,
            )

            # =========================================================
            # CONTEXTE
            # =========================================================

            context_result = self.contexte.analyser(
                cartographie,
                zones_result,
                symbol=normalized,
            )

            # =========================================================
            # CONFLUENCES
            # =========================================================

            confluences_result = (
                self.confluences.analyser(
                    candles_by_timeframe=candles,
                    zones_result=zones_result,
                    context_result=context_result,
                    market_map=cartographie,
                    symbol=normalized,
                )
            )

            # =========================================================
            # SETUPS
            # =========================================================

            setups_result = self.setups.analyser(
                candles_by_timeframe=candles,
                zones_result=zones_result,
                context_result=context_result,
                confluences_result=confluences_result,
                current_price=current_price,
                symbol=normalized,
            )

            setups = self._extract_setups(
                setups_result
            )

            # =========================================================
            # TRAITEMENT
            # =========================================================

            results: List[
                Dict[str, Any]
            ] = []

            ready_signals: List[
                Dict[str, Any]
            ] = []

            for setup in setups:

                processed = await self.traiter_setup(
                    setup,
                    symbol=normalized,
                    candles=candles,
                    zones_result=zones_result,
                    context_result=context_result,
                    confluences_result=confluences_result,
                    current_price=current_price,
                )

                if processed is None:
                    continue

                results.append(
                    processed
                )

                if (
                    processed.get(
                        "status"
                    )
                    == READY_FOR_SIGNAL
                ):
                    ready_signals.append(
                        processed
                    )

                    # Un seul signal READY
                    # par scan et par symbole.
                    break

            # =========================================================
            # RESULTAT FINAL
            # =========================================================

            overall_status = (
                READY_FOR_SIGNAL
                if ready_signals
                else "NO_SIGNAL"
            )

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
                "auto_execution": False,
            }

            self.last_analysis[
                normalized
            ] = result

            logger.info(
                "Analyse Engine 2 terminee : %s -> %s",
                normalized,
                overall_status,
            )

            return result

    # =================================================================
    # ANALYSE TOUS LES MARCHES
    # =================================================================

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

    # =================================================================
    # STREAM
    # =================================================================

    async def start_stream(
        self,
    ) -> None:
        """
        Lance le flux temps reel BiQuote de maniere non bloquante.
        IMPORTANT :
        - BiQuoteStream expose run(), pas start().
        - Une erreur du stream ne doit jamais arreter le moteur.
        - Une annulation normale est propagee pour permettre
          l'arret propre du moteur.
        """

        logger.info(
            "Demarrage du stream BiQuote..."
        )

        try:
            # BiQuoteStream utilise une coroutine run().
            await self.stream.run()

        except asyncio.CancelledError:
            logger.info(
                "Stream BiQuote annule proprement."
            )
            raise

        except Exception as exc:
            # Une erreur du stream ne doit PAS faire crasher
            # le moteur ni le bot Telegram.
            logger.exception(
                "Erreur non bloquante du stream BiQuote : %s",
                exc,
            )

        finally:
            logger.info(
                "Tache stream BiQuote terminee."
            )

    # =================================================================
    # RUN
    # =================================================================

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

        # Laisse le temps au stream
        # de commencer a recevoir les ticks.
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

    # =================================================================
    # STOP
    # =================================================================

    async def stop(
        self,
    ) -> None:

        self.running = False

        # -------------------------------------------------------------
        # Arret du stream
        # -------------------------------------------------------------

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
                "Erreur arret stream : %s",
                exc,
            )

        # -------------------------------------------------------------
        # Annulation tache stream
        # -------------------------------------------------------------

        if self._stream_task is not None:

            self._stream_task.cancel()

            try:
                await self._stream_task

            except asyncio.CancelledError:
                pass

            except Exception:
                pass

            self._stream_task = None

        # -------------------------------------------------------------
        # Fermeture du client BiQuote partage
        # -------------------------------------------------------------

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

    # =================================================================
    # STATUS
    # =================================================================

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
            "minimum_rr": MINIMUM_RR,
            "minimum_score": MINIMUM_SCORE,
            "m5_primary_confirmation": True,
            "m1_secondary_confirmation": True,
            "auto_execution": False,
            "final_validation_owner": (
                "moteur2_validation.py"
            ),
            "antispam_after_validation": True,
            "registration_after_publication": True,
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


# =====================================================================
# COMPATIBILITE
# =====================================================================

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


# =====================================================================
# MAIN LOCAL
# =====================================================================

async def main() -> None:

    moteur = Moteur2()

    try:
        result = await moteur.analyser_tous()
        print(result)

    finally:
        await moteur.stop()


# =====================================================================
# EXECUTION DIRECTE
# =====================================================================

if __name__ == "__main__":
    asyncio.run(
        main()
    )