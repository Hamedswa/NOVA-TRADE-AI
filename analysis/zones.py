from core.models import Direction, Zone


def price_inside_zone(
    price: float,
    zone: Zone,
) -> bool:
    return zone.contains(price)


def calculate_zone_quality(
    zone: Zone,
) -> float:
    """
    Qualité intrinsèque de la zone.

    H1       = 40%
    M15      = 30%
    Structure = 10%
    Liquidity = 10%
    OB        = 5%
    FVG       = 5%

    Total = 100
    """

    score = 0.0

    score += (
        max(0.0, min(100.0, zone.h1_strength))
        * 0.40
    )

    score += (
        max(0.0, min(100.0, zone.m15_strength))
        * 0.30
    )

    if zone.structure_confirmed:
        score += 10

    if zone.liquidity_nearby:
        score += 10

    if zone.order_block:
        score += 5

    if zone.fvg:
        score += 5

    return round(
        min(100.0, score),
        2
    )


def merge_overlapping_zones(
    zones: list[Zone],
) -> list[Zone]:

    if not zones:
        return []

    ordered = sorted(
        zones,
        key=lambda z: (
            z.low,
            z.high,
        ),
    )

    merged = [ordered[0]]

    for zone in ordered[1:]:

        previous = merged[-1]

        if zone.low <= previous.high:

            merged[-1] = Zone(
                direction=previous.direction,

                timeframe=(
                    f"{previous.timeframe}+"
                    f"{zone.timeframe}"
                ),

                low=min(
                    previous.low,
                    zone.low,
                ),

                high=max(
                    previous.high,
                    zone.high,
                ),

                h1_strength=max(
                    previous.h1_strength,
                    zone.h1_strength,
                ),

                m15_strength=max(
                    previous.m15_strength,
                    zone.m15_strength,
                ),

                kind=(
                    f"{previous.kind}+"
                    f"{zone.kind}"
                ),

                structure_confirmed=(
                    previous.structure_confirmed
                    or zone.structure_confirmed
                ),

                liquidity_nearby=(
                    previous.liquidity_nearby
                    or zone.liquidity_nearby
                ),

                order_block=(
                    previous.order_block
                    or zone.order_block
                ),

                fvg=(
                    previous.fvg
                    or zone.fvg
                ),

                created_at=(
                    previous.created_at
                    or zone.created_at
                ),
            )

        else:
            merged.append(zone)

    return merged