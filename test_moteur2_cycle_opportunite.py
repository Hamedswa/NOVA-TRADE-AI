from moteur2_cycle_opportunite import (
    Moteur2CycleOpportunite,
    OpportunityState,
)


def test_opportunity_matures_without_becoming_a_signal():
    engine = Moteur2CycleOpportunite()

    result = engine.observe(
        {
            "symbol": "EURUSD",
            "opportunity_id": "OPP-1",
            "opportunity_type": "CONTINUATION",
            "direction": "HAUSSIER",
            "strength": 80,
            "evidence": ["H4 cohérent", "H1 cohérent"],
        },
        regime={
            "regime": "TENDANCE_HAUSSIERE",
            "direction": "HAUSSIER",
            "strength": 80,
            "primary_alignment": "COHERENT",
        },
        confirmation={"status": "CONFIRMED"},
    )

    assert result["state"] == OpportunityState.ACTIONABLE.value
    assert "decision" not in result
    assert "BUY" not in result
    assert "SELL" not in result


def test_developing_opportunity_does_not_jump_to_actionable():
    engine = Moteur2CycleOpportunite()

    result = engine.observe(
        {
            "symbol": "BTCUSD",
            "opportunity_id": "OPP-2",
            "opportunity_type": "REACTION_ZONE",
            "direction": "HAUSSIER",
            "strength": 30,
            "evidence": ["zone détectée"],
        }
    )

    assert result["state"] == OpportunityState.DEVELOPING.value


def test_invalid_transition_is_rejected():
    engine = Moteur2CycleOpportunite()
    result = engine.observe({
        "symbol": "XAUUSD",
        "opportunity_id": "OPP-3",
        "opportunity_type": "CONTINUATION",
        "direction": "BAISSIER",
        "strength": 50,
        "evidence": ["observation"],
    })

    try:
        engine.transition(
            result["opportunity_id"],
            OpportunityState.PUBLISHED.value,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Transition directe vers PUBLISHED interdite")
