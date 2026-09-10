# moteur2.py
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
from moteur2_signal import Moteur2Signal
from moteur2_validation import Moteur2Validation
from moteur2_zones import Moteur2Zones


logger = logging.getLogger(__name__)


class Moteur2:
    """
    Moteur 2 de NOVA TRADE AI.

    Marché :
        XAU/USD uniquement.

    Source :
        BiQuote uniquement.

    Pipeline :
        BiQuote
        -> marché
        -> cartographie
        -> zones
        -> contexte
        -> confluences
        -> setups
        -> risk
        -> confirmation M5/M1
        -> score
        -> validation
        -> anti-spam
        -> signal
    """

    SYMBOL = "XAUUSD"

    def __init__(self) -> None:
        self.logger = logger

        self.biquote = BiQuoteClient()
        self.stream = BiQuoteStream()

        self.cache = Moteur2Cache()
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

        self.running = False
        self.last_analysis: Optional[Dict[str, Any]] = None
        self.last_signal: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None

        self.current_price: Optional[float] = None

    # ============================================================
    # UTILITAIRES
    # ============================================================

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)

    def _extract_price(self, tick: Any) -> Optional[float]:
        if tick is None:
            return None

        if isinstance(tick, dict):
            for key in ("mid", "price", "last", "close"):
                value = self._safe_float(tick.get(key))
                if value is not None:
                    return value

        for key in ("mid", "price", "last", "close"):
            value = self._safe_float(getattr(tick, key, None))
            if value is not None:
                return value

        return None

    # ============================================================
    # DONNÉES BIQUOTE
    # ============================================================

    async def _get_candles(self) -> Dict[str, List[Any]]:
        """
        Récupère les données nécessaires depuis BiQuote.

        Le tick temps réel ne remplace jamais une bougie M1 clôturée.
        """

        timeframes = {
            "H4": "4h",
            "H1": "1h",
            "M15": "15m",
            "M5": "5m",
            "M1": "1m",
        }

        data: Dict[str, List[Any]] = {}

        for name, timeframe in timeframes.items():
            candles = await self.biquote.get_ohlc(
                self.SYMBOL,
                timeframe=timeframe,
                limit=300,
            )

            if candles:
                data[name] = candles

        return data

    # ============================================================
    # CARTOGRAPHIE
    # ============================================================

    def _cartographier(
        self,
        donnees: Dict[str, List[Any]],
    ) -> Dict[str, Any]:
        """
        Cartographie générale du marché.

        La logique détaillée reste dans moteur2_marche.py.
        """

        try:
            return self.marche.analyser(donnees)
        except TypeError:
            try:
                return self.marche.analyser(
                    self.SYMBOL,
                    donnees,
                )
            except Exception:
                return {}

    # ============================================================
    # TRAITEMENT D'UN SETUP
    # ============================================================

    async def traiter_setup(
        self,
        setup: Any,
        zones_result: Dict[str, Any],
        contexte_result: Dict[str, Any],
        confluences_result: Dict[str, Any],
        donnees: Dict[str, List[Any]],
        current_price: Optional[float],
    ) -> Dict[str, Any]:

        result: Dict[str, Any] = {
            "setup": setup,
            "risk": None,
            "confirmation": None,
            "score": None,
            "validation": None,
            "antispam": None,
            "signal": None,
            "status": "REJECTED",
        }

        # --------------------------------------------------------
        # RISK
        # --------------------------------------------------------

        try:
            risk_plans = self.risk.analyser_setups(
                setup,
                zones_result,
                donnees,
                current_price,
            )
        except Exception as exc:
            self.logger.exception("Erreur risk Engine 2")
            result["reason"] = f"RISK_ERROR: {exc}"
            return result

        if not risk_plans:
            result["reason"] = "Aucun risk plan valide"
            return result

        risk_plan = risk_plans[0]
        result["risk"] = risk_plan

        # --------------------------------------------------------
        # CONFIRMATION M5 / M1
        # --------------------------------------------------------

        try:
            confirmation_result = self.confirmation.analyser(
                setup,
                donnees,
                risk_plan,
            )
        except Exception as exc:
            self.logger.exception("Erreur confirmation Engine 2")
            result["reason"] = f"CONFIRMATION_ERROR: {exc}"
            return result

        result["confirmation"] = confirmation_result

        # --------------------------------------------------------
        # SCORE
        # --------------------------------------------------------

        try:
            score_result = self.score.analyser(
                setup,
                zones=zones_result,
                context=contexte_result,
                confluences=confluences_result,
                confirmation=confirmation_result,
                risk_plan=risk_plan,
            )
        except Exception as exc:
            self.logger.exception("Erreur score Engine 2")
            result["reason"] = f"SCORE_ERROR: {exc}"
            return result

        result["score"] = score_result

        # --------------------------------------------------------
        # VALIDATION
        # --------------------------------------------------------

        try:
            validation_result = self.validation.analyser(
                setup=setup,
                risk_plan=risk_plan,
                confirmation=confirmation_result,
                score_result=score_result,
                context=contexte_result,
                confluences=confluences_result,
            )
        except TypeError:
            try:
                validation_result = self.validation.analyser(
                    setup,
                    risk_plan,
                    confirmation_result,
                    score_result,
                )
            except Exception as exc:
                self.logger.exception("Erreur validation Engine 2")
                result["reason"] = f"VALIDATION_ERROR: {exc}"
                return result
        except Exception as exc:
            self.logger.exception("Erreur validation Engine 2")
            result["reason"] = f"VALIDATION_ERROR: {exc}"
            return result

        result["validation"] = validation_result

        validation_status = str(
            self._get(
                validation_result,
                "status",
                self._get(
                    validation_result,
                    "validation_status",
                    "REJECTED",
                ),
            )
        ).upper()

        result["status"] = validation_status

        # --------------------------------------------------------
        # SETUP VALIDE MAIS EN ATTENTE M5/M1
        # --------------------------------------------------------

        if validation_status == "VALIDATED_WAITING_CONFIRMATION":
            result["waiting_confirmation"] = True
            result["reason"] = (
                "Setup validé. Confirmation M5/M1 encore attendue."
            )
            return result

        # --------------------------------------------------------
        # TOUT CE QUI N'EST PAS READY EST REFUSÉ
        # --------------------------------------------------------

        if validation_status != "READY_FOR_SIGNAL":
            result["reason"] = self._get(
                validation_result,
                "reason",
                "Validation refusée",
            )
            return result

        # --------------------------------------------------------
        # ANTI-SPAM UNIQUEMENT POUR UN SIGNAL PRÊT
        # --------------------------------------------------------

        try:
            antispam_result = self.antispam.verifier(
                setup,
                risk_plan,
                validation_result,
            )
        except Exception as exc:
            self.logger.exception("Erreur anti-spam Engine 2")
            result["reason"] = f"ANTISPAM_ERROR: {exc}"
            return result

        result["antispam"] = antispam_result

        spam_blocked = bool(
            self._get(antispam_result, "blocked", False)
            or self._get(antispam_result, "is_duplicate", False)
            or self._get(antispam_result, "duplicate", False)
        )

        if spam_blocked:
            result["status"] = "REJECTED"
            result["reason"] = self._get(
                antispam_result,
                "reason",
                "Signal bloqué par anti-spam",
            )
            return result

        # --------------------------------------------------------
        # CONSTRUCTION SIGNAL
        # --------------------------------------------------------

        try:
            signal_result = self.signal.creer_signal(
                setup=setup,
                risk_plan=risk_plan,
                score_result=score_result,
                validation_result=validation_result,
                confirmation_result=confirmation_result,
            )
        except TypeError:
            try:
                signal_result = self.signal.creer_signal(
                    setup,
                    risk_plan,
                    score_result,
                    validation_result,
                    confirmation_result,
                )
            except Exception as exc:
                self.logger.exception("Erreur création signal")
                result["reason"] = f"SIGNAL_ERROR: {exc}"
                return result
        except Exception as exc:
            self.logger.exception("Erreur création signal")
            result["reason"] = f"SIGNAL_ERROR: {exc}"
            return result

        result["signal"] = signal_result

        # --------------------------------------------------------
        # ENREGISTREMENT ANTI-SPAM
        # --------------------------------------------------------

        try:
            self.antispam.enregistrer_signal(
                setup,
                risk_plan,
                setup_id=self._get(setup, "setup_id"),
            )
        except Exception:
            self.logger.exception(
                "Impossible d'enregistrer le signal anti-spam"
            )

        result["status"] = "READY_FOR_SIGNAL"

        return result

    # ============================================================
    # ANALYSE XAU/USD
    # ============================================================

    async def analyser_xauusd(self) -> Dict[str, Any]:
        self.last_error = None

        try:
            donnees = await self._get_candles()

            if not donnees:
                raise RuntimeError(
                    "Aucune donnée OHLC reçue depuis BiQuote"
                )

            # ----------------------------------------------------
            # CARTOGRAPHIE
            # ----------------------------------------------------

            cartographie = self._cartographier(donnees)

            # ----------------------------------------------------
            # PRIX COURANT
            # ----------------------------------------------------

            current_price = self.current_price

            if current_price is None:
                try:
                    tick = await self.biquote.get_latest_tick(
                        self.SYMBOL
                    )
                    current_price = self._extract_price(tick)
                except Exception:
                    current_price = None

            self.current_price = current_price

            # ----------------------------------------------------
            # ZONES
            # ----------------------------------------------------

            zones_result = self.zones.analyser(
                cartographie,
                current_price=current_price,
            )

            # ----------------------------------------------------
            # CONTEXTE
            # ----------------------------------------------------

            contexte_result = self.contexte.analyser(
                donnees,
                zones_result,
            )

            # ----------------------------------------------------
            # CONFLUENCES
            # ----------------------------------------------------

            confluences_result = self.confluences.analyser(
                donnees,
                zones_result,
                contexte_result,
                cartographie,
            )

            # ----------------------------------------------------
            # SETUPS
            # ----------------------------------------------------

            setups_result = self.setups.analyser(
                zones_result,
                confluences_result,
                contexte_result,
                donnees,
            )

            setups = []

            if isinstance(setups_result, list):
                setups = setups_result
            elif isinstance(setups_result, dict):
                setups = (
                    setups_result.get("setups")
                    or setups_result.get("candidates")
                    or setups_result.get("results")
                    or []
                )

            # ----------------------------------------------------
            # TRAITEMENT
            # ----------------------------------------------------

            processed: List[Dict[str, Any]] = []

            for setup in setups:
                item = await self.traiter_setup(
                    setup,
                    zones_result,
                    contexte_result,
                    confluences_result,
                    donnees,
                    current_price,
                )

                processed.append(item)

                if item.get("status") == "READY_FOR_SIGNAL":
                    self.last_signal = item

                    # Un seul signal final par cycle d'analyse.
                    break

            result = {
                "symbol": self.SYMBOL,
                "timestamp": self._now(),
                "current_price": current_price,
                "market_map": cartographie,
                "zones": zones_result,
                "context": contexte_result,
                "confluences": confluences_result,
                "setups": setups,
                "results": processed,
                "signal": self.last_signal,
            }

            self.last_analysis = result

            return result

        except Exception as exc:
            self.last_error = str(exc)

            self.logger.exception(
                "Erreur analyse XAU/USD Engine 2"
            )

            result = {
                "symbol": self.SYMBOL,
                "timestamp": self._now(),
                "status": "ERROR",
                "error": str(exc),
            }

            self.last_analysis = result

            return result

    # ============================================================
    # STREAM BIQUOTE
    # ============================================================

    async def _handle_tick(self, tick: Any) -> None:
        price = self._extract_price(tick)

        if price is not None:
            self.current_price = price

        try:
            await self.stream.handle_tick(tick)
        except AttributeError:
            pass

    async def start_stream(self) -> None:
        """
        Démarre le flux temps réel BiQuote.

        Le stream est continu.
        Aucun polling du tick n'est nécessaire.
        """

        try:
            if hasattr(self.stream, "start"):
                await self.stream.start(
                    symbols=[self.SYMBOL],
                    callback=self._handle_tick,
                )
                return

            if hasattr(self.stream, "run"):
                await self.stream.run(
                    symbols=[self.SYMBOL],
                    callback=self._handle_tick,
                )
                return

            if hasattr(self.stream, "connect"):
                await self.stream.connect()

                if hasattr(self.stream, "subscribe"):
                    await self.stream.subscribe([self.SYMBOL])

        except Exception as exc:
            self.logger.exception(
                "Erreur stream BiQuote: %s",
                exc,
            )

    # ============================================================
    # BOUCLE
    # ============================================================

    async def run(self) -> None:
        self.running = True

        self.logger.info(
            "NOVA TRADE AI — Moteur 2 démarré — %s",
            self.SYMBOL,
        )

        stream_task = asyncio.create_task(
            self.start_stream()
        )

        try:
            # Première analyse immédiate.
            await self.analyser_xauusd()

            # Les fréquences ci-dessous sont celles du cache.
            # Le stream BiQuote reste continu indépendamment.
            last_h4 = 0.0
            last_h1 = 0.0
            last_m15 = 0.0
            last_m5 = 0.0
            last_m1 = 0.0

            loop = asyncio.get_running_loop()

            while self.running:
                now = loop.time()

                # M1
                if now - last_m1 >= 60:
                    await self.analyser_xauusd()
                    last_m1 = now

                # M5
                if now - last_m5 >= 600:
                    await self.analyser_xauusd()
                    last_m5 = now

                # M15
                if now - last_m15 >= 1800:
                    await self.analyser_xauusd()
                    last_m15 = now

                # H1
                if now - last_h1 >= 7200:
                    await self.analyser_xauusd()
                    last_h1 = now

                # H4
                if now - last_h4 >= 28800:
                    await self.analyser_xauusd()
                    last_h4 = now

                await asyncio.sleep(1)

        finally:
            self.running = False

            if not stream_task.done():
                stream_task.cancel()

            try:
                await stream_task
            except asyncio.CancelledError:
                pass

            try:
                await self.biquote.close()
            except Exception:
                pass

    async def stop(self) -> None:
        self.running = False

        try:
            if hasattr(self.stream, "stop"):
                result = self.stream.stop()

                if asyncio.iscoroutine(result):
                    await result
        except Exception:
            self.logger.exception(
                "Erreur arrêt stream BiQuote"
            )

        try:
            await self.biquote.close()
        except Exception:
            pass

    # ============================================================
    # STATUS
    # ============================================================

    def get_status(self) -> Dict[str, Any]:
        return {
            "engine": "MOTEUR_2",
            "symbol": self.SYMBOL,
            "data_source": "BIQUOTE",
            "running": self.running,
            "current_price": self.current_price,
            "last_error": self.last_error,
            "last_analysis": self.last_analysis,
            "last_signal": self.last_signal,
        }


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
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