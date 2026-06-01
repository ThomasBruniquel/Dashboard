"""
Carbon footprint estimator for the GVA -> DOH group flight.

Emission factors follow the ICAO Carbon Emissions Calculator methodology,
using per-seat area multipliers for cabin class.
"""

GVA_DOH_KM = 5_170  # Great circle distance, km, one way

# kg CO2 per passenger per km (one-way, ICAO-aligned)
EMISSION_FACTORS = {
    "economy":  0.150,
    "business": 0.450,   # 3x economy (seat area factor)
    "first":    0.900,   # 6x economy
}

# Typical mix for a luxury executive event
DEFAULT_CLASS_MIX = {"economy": 0.40, "business": 0.55, "first": 0.05}


def compute_carbon_footprint(passengers: int, class_mix: dict | None = None) -> dict:
    """
    Estimate CO2 emissions for the GVA -> DOH group, one way.

    Returns total kg/tonnes, per-person average, and equivalent trees-per-year
    needed to offset (1 tree absorbs ~22 kg CO2/year).
    """
    if class_mix is None:
        class_mix = DEFAULT_CLASS_MIX

    weighted_factor = sum(
        class_mix.get(cls, 0.0) * EMISSION_FACTORS.get(cls, 0.0)
        for cls in EMISSION_FACTORS
    )

    per_person_kg   = weighted_factor * GVA_DOH_KM
    total_kg        = per_person_kg * passengers
    trees_to_offset = int(total_kg / 22)

    return {
        "per_person_kg":    round(per_person_kg),
        "per_person_tonnes": round(per_person_kg / 1000, 2),
        "total_kg":         round(total_kg),
        "total_tonnes":     round(total_kg / 1000, 1),
        "trees_to_offset":  trees_to_offset,
        "distance_km":      GVA_DOH_KM,
        "passengers":       passengers,
        "class_mix":        class_mix,
        "emission_factors": EMISSION_FACTORS,
        "method":           "ICAO Carbon Emissions Calculator (cabin-class weighted)",
        "note":             "One-way GVA -> DOH. Double for round trip.",
    }
