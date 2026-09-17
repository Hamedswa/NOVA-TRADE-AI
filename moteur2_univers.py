"""
NOVA TRADE AI - MOTEUR 2
UNIVERS DE MARCHÉ
Rôle
----
Gestion descriptive et dynamique de l'univers de marchés que le moteur
pourra observer.
Architecture visée :
    UNIVERS
       ↓
    RADAR
       ↓
    MARCHÉS INTÉRESSANTS
       ↓
    ANALYSE APPROFONDIE
       ↓
    OPPORTUNITÉS
       ↓
    RANKING
IMPORTANT
---------
Ce module NE récupère aucune donnée directement auprès de BiQuote.
Il ne modifie :
    - aucun stream
    - aucun cache
    - aucun client BiQuote
    - moteur2_multi_actifs.py
Il fournit uniquement une couche de gestion de l'univers.
L'univers actif actuel reste volontairement limité aux quatre actifs
validés du moteur 2 :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD
L'architecture permet cependant d'ajouter progressivement d'autres
marchés lorsque les capacités réelles de la source de données auront
été vérifiées.
Ce module ne :
    - décide pas BUY / SELL / WAIT
    - ne calcule pas de risque financier
    - n'impose aucun RR minimum
    - ne filtre pas une opportunité technique
    - n'utilise pas BOS / CHoCH / OB / FVG / SMC / ICT
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
# ============================================================================
# UNIVERS ACTUEL VALIDÉ
# ============================================================================
CURRENT_SUPPORTED_SYMBOLS: Tuple[str, ...] = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)
# ============================================================================
# CATÉGORIES
# ============================================================================
FOREX_SYMBOLS: Tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
)
CRYPTO_SYMBOLS: Tuple[str, ...] = (
    "BTCUSD",
)
METAL_SYMBOLS: Tuple[str, ...] = (
    "XAUUSD",
)
# ============================================================================
# PROFILS DES MARCHÉS
# ============================================================================
MARKET_PROFILES: Dict[str, Dict[str, Any]] = {
    "XAUUSD": {
        "asset_class": "METAL",
        "base": "XAU",
        "quote": "USD",
        "name": "Gold / US Dollar",
        "priority": 1,
        "24h": False,
        "fundamental_groups": [
            "USD",
            "rates",
            "real_yields",
            "inflation",
            "central_banks",
            "geopolitics",
            "risk_sentiment",
        ],
    },
    "BTCUSD": {
        "asset_class": "CRYPTO",
        "base": "BTC",
        "quote": "USD",
        "name": "Bitcoin / US Dollar",
        "priority": 1,
        "24h": True,
        "fundamental_groups": [
            "USD",
            "liquidity",
            "rates",
            "risk_sentiment",
            "crypto_flows",
            "regulation",
            "crypto_events",
        ],
    },
    "EURUSD": {
        "asset_class": "FOREX",
        "base": "EUR",
        "quote": "USD",
        "name": "Euro / US Dollar",
        "priority": 1,
        "24h": False,
        "fundamental_groups": [
            "USD",
            "EUR",
            "ECB",
            "FED",
            "rates",
            "inflation",
            "employment",
            "GDP",
            "PMI",
        ],
    },
    "GBPUSD": {
        "asset_class": "FOREX",
        "base": "GBP",
        "quote": "USD",
        "name": "British Pound / US Dollar",
        "priority": 1,
        "24h": False,
        "fundamental_groups": [
            "USD",
            "GBP",
            "BOE",
            "FED",
            "rates",
            "inflation",
            "employment",
            "GDP",
            "PMI",
        ],
    },
}
# ============================================================================
# DATACLASS
# ============================================================================
@dataclass
class MarketInstrument:
    """
    Représente un marché connu de l'univers.
    Ce n'est PAS une donnée de prix.
    Les champs de surveillance sont descriptifs et peuvent être remplis
    ultérieurement par le radar ou une source externe.
    """
    symbol: str
    asset_class: str = "UNKNOWN"
    base: Optional[str] = None
    quote: Optional[str] = None
    name: Optional[str] = None
    enabled: bool = True
    priority: int = 5
    data_available: Optional[bool] = None
    radar_interest: float = 0.0
    attention: str = "NORMAL"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "base": self.base,
            "quote": self.quote,
            "name": self.name,
            "enabled": self.enabled,
            "priority": self.priority,
            "data_available": self.data_available,
            "radar_interest": round(
                float(self.radar_interest),
                2,
            ),
            "attention": self.attention,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "updated_at": self.updated_at,
        }
# ============================================================================
# MOTEUR UNIVERS
# ============================================================================
class Moteur2Univers:
    """
    Gestionnaire de l'univers de marché.
    Philosophie :
        ne pas supposer que tous les marchés sont analysables ;
        ne pas demander au moteur d'analyser profondément tout
        l'univers en permanence ;
        permettre au radar de sélectionner les marchés qui méritent
        une analyse approfondie.
    Le gestionnaire reste indépendant de la récupération des prix.
    """
    def __init__(
        self,
        supported_symbols: Optional[Sequence[str]] = None,
        *,
        allow_future_markets: bool = True,
    ) -> None:
        initial_symbols = (
            supported_symbols
            if supported_symbols is not None
            else CURRENT_SUPPORTED_SYMBOLS
        )
        self.allow_future_markets = bool(
            allow_future_markets
        )
        self._markets: Dict[str, MarketInstrument] = {}
        for symbol in initial_symbols:
            self.ajouter_marche(symbol)
    # =========================================================================
    # NORMALISATION
    # =========================================================================
    @staticmethod
    def normaliser_symbole(symbol: Any) -> str:
        """
        Normalise les formes courantes :
            XAU/USD -> XAUUSD
            BTC/USD -> BTCUSD
            EUR/USD -> EURUSD
            GBP/USD -> GBPUSD
        """
        value = str(symbol or "").strip().upper()
        replacements = (
            ("/", ""),
            ("-", ""),
            ("_", ""),
            (" ", ""),
        )
        for old, new in replacements:
            value = value.replace(old, new)
        aliases = {
            "GOLD": "XAUUSD",
            "XAU": "XAUUSD",
            "BITCOIN": "BTCUSD",
            "BTC": "BTCUSD",
        }
        return aliases.get(value, value)
    # =========================================================================
    # AJOUT
    # =========================================================================
    def ajouter_marche(
        self,
        symbol: str,
        *,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MarketInstrument:
        """
        Ajoute un marché à l'univers.
        Aucun appel réseau n'est effectué.
        Cela signifie qu'ajouter un symbole ici ne garantit PAS que
        BiQuote sait réellement fournir ses données.
        Cette vérification appartient à la couche de données.
        """
        normalized = self.normaliser_symbole(symbol)
        profile = MARKET_PROFILES.get(
            normalized,
            {},
        )
        market = MarketInstrument(
            symbol=normalized,
            asset_class=str(
                profile.get(
                    "asset_class",
                    self._infer_asset_class(normalized),
                )
            ),
            base=profile.get("base"),
            quote=profile.get("quote"),
            name=profile.get("name"),
            enabled=bool(enabled),
            priority=int(
                profile.get(
                    "priority",
                    5,
                )
            ),
            metadata=dict(metadata or {}),
        )
        self._markets[normalized] = market
        return market
    # =========================================================================
    # RETRAIT
    # =========================================================================
    def retirer_marche(
        self,
        symbol: str,
    ) -> bool:
        normalized = self.normaliser_symbole(symbol)
        if normalized not in self._markets:
            return False
        del self._markets[normalized]
        return True
    # =========================================================================
    # ACTIVATION
    # =========================================================================
    def activer(
        self,
        symbol: str,
    ) -> bool:
        normalized = self.normaliser_symbole(symbol)
        market = self._markets.get(normalized)
        if market is None:
            return False
        market.enabled = True
        market.updated_at = self._now()
        return True
    # =========================================================================
    # DÉSACTIVATION
    # =========================================================================
    def desactiver(
        self,
        symbol: str,
    ) -> bool:
        normalized = self.normaliser_symbole(symbol)
        market = self._markets.get(normalized)
        if market is None:
            return False
        market.enabled = False
        market.updated_at = self._now()
        return True
    # =========================================================================
    # LISTES
    # =========================================================================
    def tous_les_marches(
        self,
    ) -> List[MarketInstrument]:
        return list(
            self._markets.values()
        )
    def marches_actifs(
        self,
    ) -> List[MarketInstrument]:
        return [
            market
            for market in self._markets.values()
            if market.enabled
        ]
    def symboles(
        self,
        *,
        active_only: bool = True,
    ) -> List[str]:
        markets = (
            self.marches_actifs()
            if active_only
            else self.tous_les_marches()
        )
        return [
            market.symbol
            for market in markets
        ]
    # =========================================================================
    # RECHERCHE
    # =========================================================================
    def obtenir(
        self,
        symbol: str,
    ) -> Optional[MarketInstrument]:
        normalized = self.normaliser_symbole(symbol)
        return self._markets.get(normalized)
    def contient(
        self,
        symbol: str,
    ) -> bool:
        return (
            self.normaliser_symbole(symbol)
            in self._markets
        )
    # =========================================================================
    # CLASSES D'ACTIFS
    # =========================================================================
    def par_classe(
        self,
        asset_class: str,
        *,
        active_only: bool = True,
    ) -> List[MarketInstrument]:
        wanted = str(
            asset_class or ""
        ).strip().upper()
        markets = (
            self.marches_actifs()
            if active_only
            else self.tous_les_marches()
        )
        return [
            market
            for market in markets
            if market.asset_class.upper() == wanted
        ]
    def forex(
        self,
        *,
        active_only: bool = True,
    ) -> List[MarketInstrument]:
        return self.par_classe(
            "FOREX",
            active_only=active_only,
        )
    def crypto(
        self,
        *,
        active_only: bool = True,
    ) -> List[MarketInstrument]:
        return self.par_classe(
            "CRYPTO",
            active_only=active_only,
        )
    def metaux(
        self,
        *,
        active_only: bool = True,
    ) -> List[MarketInstrument]:
        return self.par_classe(
            "METAL",
            active_only=active_only,
        )
    # =========================================================================
    # MISE À JOUR RADAR
    # =========================================================================
    def mettre_a_jour_radar(
        self,
        symbol: str,
        interest: float,
        *,
        attention: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        data_available: Optional[bool] = None,
    ) -> bool:
        """
        Reçoit uniquement les observations du radar.
        Le radar peut donc signaler :
            "ce marché devient intéressant"
        sans que l'univers décide lui-même de trader.
        """
        market = self.obtenir(symbol)
        if market is None:
            return False
        market.radar_interest = max(
            0.0,
            min(100.0, float(interest)),
        )
        if attention is not None:
            market.attention = str(
                attention
            ).upper()
        if tags is not None:
            market.tags = [
                str(tag)
                for tag in tags
            ]
        if data_available is not None:
            market.data_available = bool(
                data_available
            )
        market.updated_at = self._now()
        return True
    # =========================================================================
    # MARCHÉS À APPROFONDIR
    # =========================================================================
    def marches_a_approfondir(
        self,
        *,
        minimum_interest: float = 50.0,
        require_data: bool = False,
    ) -> List[MarketInstrument]:
        """
        Retourne les marchés qui méritent potentiellement une analyse
        approfondie.
        IMPORTANT :
        ceci n'est PAS une décision de trading.
        Le seuil d'intérêt concerne seulement l'allocation de
        l'attention informatique du moteur.
        """
        result: List[MarketInstrument] = []
        for market in self.marches_actifs():
            if require_data and market.data_available is not True:
                continue
            if (
                market.radar_interest
                >= float(minimum_interest)
            ):
                result.append(market)
        result.sort(
            key=lambda item: (
                -float(item.radar_interest),
                int(item.priority),
                item.symbol,
            )
        )
        return result
    # =========================================================================
    # ALLOCATION D'ATTENTION
    # =========================================================================
    def allocation_attention(
        self,
    ) -> List[Dict[str, Any]]:
        """
        Produit une vue de l'allocation actuelle de l'attention.
        Cette sortie permet au futur orchestrateur de savoir où
        concentrer l'analyse sans décider d'une position.
        """
        result: List[Dict[str, Any]] = []
        for market in self.marches_actifs():
            result.append(
                {
                    "symbol": market.symbol,
                    "asset_class": market.asset_class,
                    "radar_interest": round(
                        market.radar_interest,
                        2,
                    ),
                    "attention": market.attention,
                    "data_available": market.data_available,
                    "priority": market.priority,
                }
            )
        result.sort(
            key=lambda item: (
                -float(item["radar_interest"]),
                int(item["priority"]),
                item["symbol"],
            )
        )
        return result
    # =========================================================================
    # PROFIL
    # =========================================================================
    def profil(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        normalized = self.normaliser_symbole(
            symbol
        )
        profile = MARKET_PROFILES.get(
            normalized
        )
        if profile is None:
            return {}
        return dict(profile)
    # =========================================================================
    # CAPACITÉS ATTENDUES
    # =========================================================================
    def capacites_attendues(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Décrit ce que le moteur pourrait surveiller pour l'actif.
        Ce n'est PAS une déclaration de disponibilité de données.
        La disponibilité réelle devra être confirmée par la couche
        de données.
        """
        normalized = self.normaliser_symbole(
            symbol
        )
        profile = MARKET_PROFILES.get(
            normalized,
            {},
        )
        return {
            "symbol": normalized,
            "asset_class": profile.get(
                "asset_class",
                "UNKNOWN",
            ),
            "fundamental_groups": list(
                profile.get(
                    "fundamental_groups",
                    [],
                )
            ),
            "continuous_market": bool(
                profile.get(
                    "24h",
                    False,
                )
            ),
            "data_source_verified": False,
            "note": (
                "La disponibilité réelle doit être "
                "confirmée par la couche de données."
            ),
        }
    # =========================================================================
    # IMPORT D'UN UNIVERS EXTERNE
    # =========================================================================
    def importer(
        self,
        symbols: Iterable[str],
        *,
        enabled: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Prépare des marchés supplémentaires.
        Par défaut, les nouveaux marchés sont désactivés.
        Cela permet de préparer un univers beaucoup plus large sans
        l'activer automatiquement et sans supposer que BiQuote les
        supporte.
        """
        added: List[str] = []
        for symbol in symbols:
            normalized = self.normaliser_symbole(
                symbol
            )
            if not normalized:
                continue
            if (
                normalized not in self._markets
                and not self.allow_future_markets
            ):
                continue
            market = self.ajouter_marche(
                normalized,
                enabled=enabled,
                metadata=metadata,
            )
            added.append(
                market.symbol
            )
        return added
    # =========================================================================
    # EXPORT
    # =========================================================================
    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_universe": list(
                self.symboles(
                    active_only=True
                )
            ),
            "all_markets": [
                market.to_dict()
                for market in self.tous_les_marches()
            ],
            "counts": {
                "total": len(
                    self.tous_les_marches()
                ),
                "active": len(
                    self.marches_actifs()
                ),
                "forex": len(
                    self.forex()
                ),
                "crypto": len(
                    self.crypto()
                ),
                "metals": len(
                    self.metaux()
                ),
            },
            "dynamic_universe_ready": True,
            "data_source_managed_elsewhere": True,
            "decision_owner": "moteur2_decision.py",
            "informational_only": True,
            "blocking": False,
            "updated_at": self._now(),
        }
    # =========================================================================
    # RÉINITIALISATION
    # =========================================================================
    def reinitialiser_univers_actuel(
        self,
    ) -> None:
        """
        Revient à l'univers actuellement validé.
        Utile pour les tests et pour éviter qu'un futur import externe
        modifie définitivement l'univers de production.
        """
        self._markets.clear()
        for symbol in CURRENT_SUPPORTED_SYMBOLS:
            self.ajouter_marche(symbol)
    # =========================================================================
    # UTILITAIRES
    # =========================================================================
    @staticmethod
    def _infer_asset_class(
        symbol: str,
    ) -> str:
        if symbol.endswith("USD"):
            if symbol.startswith(
                (
                    "BTC",
                    "ETH",
                    "SOL",
                    "XRP",
                    "BNB",
                    "ADA",
                    "DOGE",
                    "AVAX",
                    "DOT",
                    "LTC",
                )
            ):
                return "CRYPTO"
            if symbol.startswith("XAU"):
                return "METAL"
            if len(symbol) == 6:
                return "FOREX"
        return "UNKNOWN"
    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()
# ============================================================================
# INSTANCE PAR DÉFAUT
# ============================================================================
_default_univers: Optional[Moteur2Univers] = None
def obtenir_univers() -> Moteur2Univers:
    """
    Retourne l'instance globale de l'univers.
    L'univers par défaut reste les quatre actifs actuels.
    """
    global _default_univers
    if _default_univers is None:
        _default_univers = Moteur2Univers(
            CURRENT_SUPPORTED_SYMBOLS
        )
    return _default_univers
def obtenir_symboles_actifs() -> List[str]:
    """
    Retourne les symboles actuellement actifs.
    """
    return obtenir_univers().symboles(
        active_only=True
    )
def obtenir_marches_a_approfondir(
    minimum_interest: float = 50.0,
) -> List[Dict[str, Any]]:
    """
    Fonction pratique pour le futur radar/orchestrateur.
    """
    markets = obtenir_univers().marches_a_approfondir(
        minimum_interest=minimum_interest
    )
    return [
        market.to_dict()
        for market in markets
    ]
# ============================================================================
# EXPORTS
# ============================================================================
__all__ = [
    "CURRENT_SUPPORTED_SYMBOLS",
    "FOREX_SYMBOLS",
    "CRYPTO_SYMBOLS",
    "METAL_SYMBOLS",
    "MARKET_PROFILES",
    "MarketInstrument",
    "Moteur2Univers",
    "obtenir_univers",
    "obtenir_symboles_actifs",
    "obtenir_marches_a_approfondir",
]