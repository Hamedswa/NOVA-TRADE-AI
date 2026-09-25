import asyncio

from moteur2 import Moteur2
from moteur2_cycle_opportunite import Moteur2CycleOpportunite
from moteur2_evidence import Moteur2Evidence
from moteur2_regime import Moteur2Regime


def test_engine_owns_new_layers():
    engine = Moteur2.__new__(Moteur2)
    engine.regime = Moteur2Regime()
    engine.cycle_opportunite = Moteur2CycleOpportunite()
    engine.evidence = Moteur2Evidence()
    assert isinstance(engine.regime, Moteur2Regime)
    assert isinstance(engine.cycle_opportunite, Moteur2CycleOpportunite)
    assert isinstance(engine.evidence, Moteur2Evidence)


def test_opportunity_cycle_does_not_decide():
    cycle = Moteur2CycleOpportunite()
    result = cycle.observe(
        {
            "symbol": "BTCUSD",
            "opportunity_id": "OPP-TEST-1",
            "opportunity_type": "CONTINUATION",
            "direction": "BUY",
            "strength": 80,
            "evidence": ["H4 directionnel", "H1 convergent"],
        },
        regime={
            "regime": "TENDANCE",
            "direction": "HAUSSIER",
            "strength": 80,
            "primary_alignment": "COHERENT",
        },
        evidence=[
            {"type": "SUPPORTIVE", "source": "H4"},
            {"type": "SUPPORTIVE", "source": "H1"},
        ],
    )
    assert result["state"] in {
        "DEVELOPING",
        "MATURE",
        "ACTIONABLE",
    }
    assert "decision" not in result
    assert "BUY" not in result
    assert "SELL" not in result


def test_evidence_is_descriptive_only():
    result = Moteur2Evidence().analyser(
        symbol="EURUSD",
        intelligence={"direction": "BUY"},
        contexte={"directional_bias": "BUY"},
        opportunites={
            "opportunity_id": "OPP-1",
            "direction": "BUY",
            "strength": 70,
        },
    )
    assert result["decision_owner"] == "moteur2_decision.py"
    assert "decision" not in result
