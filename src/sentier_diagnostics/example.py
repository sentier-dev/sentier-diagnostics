"""A made-up chain with every class and every verdict in it. Nobody's data.

Five states of ten made-up items in three indicators:

    published   what the publisher released (rounded to four significant digits)
    repro       step 0: the same database computed again by us
    fix-1       a person's fix of two fertiliser amounts
    rebuilt     the same state built again on another machine (nothing explains it)
    mapping-2   a changed mapping, whose reach a program worked out

What it must show, at least once each:

    agrees            most values in every step
    within noise      Oats, water use, in mapping-2: less than the rebuild differs
    differs           Wheat, climate change, in fix-1: down 10 %
    beyond 10x        Tomato, water use, in mapping-2: 25 times as much
    zero reference    Machine hour, toxicity, in mapping-2: from 0 to a result
    zero result       Heat, climate change, in mapping-2: from a result to 0
    sign change       Compost, climate change, in mapping-2: from a credit to a burden
    near zero         Rice, toxicity: both results far below the floor of their unit
    missing           Rye, water use, in the published results; Rye, climate, in mapping-2;
                      Barley, water use, in the rebuilt state, so that its whole
                      difference cannot be split among the steps (not attributable)

    as claimed        Wheat, climate, fix-1; Tomato, water, mapping-2
    off claim         Rice, climate, fix-1: down 50 %, further than the claim's 30 %
    not claimed       Barley, climate, fix-1; Tomato, toxicity, step 0
    claimed, not moved  Maize, water, mapping-2: the claim says it must move
    within noise      Oats, water, mapping-2
    not judged        Rye: missing; Rice, toxicity: near zero

Two results below zero that go further below zero (Compost, toxicity, mapping-2) went
down: the page colours them as down.
"""

from __future__ import annotations

from . import breakdown, chain, claims, rule

CLIMATE, WATER, TOX = "x:climate", "x:water", "x:tox"
INDICATORS = [
    (CLIMATE, "Climate change", "Climate", "kg CO2 eq"),
    (WATER, "Water use", "Water", "m3"),
    (TOX, "Human toxicity", "Toxicity", "CTUh"),
]
ITEMS = {
    "p01": ("Wheat", "kg", "FR", "crops"),
    "p02": ("Maize", "kg", "FR", "crops"),
    "p03": ("Barley", "kg", "DE", "crops"),
    "p04": ("Oats", "kg", "DE", "crops"),
    "p05": ("Rice", "kg", "IT", "crops"),
    "p06": ("Rye", "kg", "PL", "crops"),
    "p07": ("Heat from wood chips", "MJ", "CH", "energy"),
    "p08": ("Compost, used as fertiliser", "kg", "CH", "waste"),
    "p09": ("Machine hour, harvesting", "h", "CH", "services"),
    "p10": ("Tomato, greenhouse", "kg", "NL", "crops"),
}
PUBLISHED = {
    CLIMATE: {"p01": 0.5200, "p02": 0.4100, "p03": 0.4800, "p04": 0.4500, "p05": 1.900,
              "p06": 0.4300, "p07": 0.03000, "p08": -0.5000, "p09": 42.00, "p10": 1.300},
    WATER: {"p01": 1.200, "p02": 2.500, "p03": 1.100, "p04": 1.000, "p05": 3.400,
            "p06": None, "p07": 0.0004000, "p08": 0.05000, "p09": 0.9000, "p10": 0.02000},
    TOX: {"p01": 2.000e-7, "p02": 1.800e-7, "p03": 1.900e-7, "p04": 1.700e-7, "p05": 1.000e-12,
          "p06": 2.100e-7, "p07": 3.000e-9, "p08": -2.000e-6, "p09": 0.0, "p10": 2.100e-7},
}  # fmt: skip


def _with(base, **changes):
    """A copy of a set of results with some values changed: `{indicator: {item: value}}`."""
    found = {key: dict(column) for key, column in base.items()}
    for key, column in changes.items():
        found[{"climate": CLIMATE, "water": WATER, "tox": TOX}[key]].update(column)
    return found


# step 0: computed again; differs from the published results by their rounding, except
# Tomato's toxicity (an import difference nobody claimed) and Rye's water use, which the
# publisher did not release
REPRO = _with(
    PUBLISHED,
    climate={"p01": 0.520013, "p03": 0.479990, "p09": 42.00042},
    water={"p06": 1.150, "p02": 2.500025},
    tox={"p10": 2.300e-7, "p01": 2.0000002e-7},
)
# fix-1: wheat 10 % lower, rice 50 % lower, barley 20 % higher
FIX_1 = _with(REPRO, climate={"p01": 0.468012, "p05": 0.95, "p03": 0.575988})
# rebuilt elsewhere: oats' water use 2.5 % higher, the rest at solver noise; barley's water
# use failed to compute
REBUILT = _with(FIX_1, water={"p04": 1.025, "p01": 1.2000001, "p03": None})
# mapping-2
MAPPING_2 = _with(
    REBUILT,
    climate={"p07": 0.0, "p08": 0.2, "p06": None},
    water={"p04": 1.0455, "p10": 0.5, "p03": 1.3},
    tox={"p09": 4.0e-7, "p08": -4.0e-6, "p05": 3.0e-12},
)
VALUES = {
    "published": PUBLISHED,
    "repro": REPRO,
    "fix-1": FIX_1,
    "rebuilt": REBUILT,
    "mapping-2": MAPPING_2,
}


def steps() -> list[dict]:
    # noise beyond the floors the chain counts with: those of its first state
    units = {item: about[1] for item, about in ITEMS.items()}
    floors = rule.floors_of(PUBLISHED, units)
    noise = {
        key: chain.noise_of(FIX_1[key], REBUILT[key],
                            floor={item: floors[(key, unit)][0] for item, unit in units.items()})  # fmt: skip
        for key in FIX_1
    }
    return [
        chain.step(
            "step-0",
            "Reproduction",
            kind="reproduction",
            about="The released data computed again with the same method.",
            claim=claims.claim(
                "Nothing moves beyond the rounding of the published results.",
                by=claims.origin("code", "reproduction rule"),
            ),
            tolerance=chain.tolerance(5e-4, "published rounding", "four significant digits"),
        ),
        chain.step(
            "fix-1",
            "Fertiliser amounts of two cereals",
            kind="fix",
            about="The nitrogen amounts of wheat and rice were per hectare, not per kilogram.",
            link="https://example.org/findings/fix-1",
            claim=claims.claim(
                "Wheat and rice go down in climate change, by 30 % at most. Nothing else moves.",
                [claims.scope([CLIMATE], {"p01", "p05"}, "down", 0.3, claims.MUST)],
                by=claims.origin("person", "A. Author"),
            ),
        ),
        chain.step(
            "rebuilt",
            "Built again on another machine",
            kind="rebuild",
            explained=False,
            about="The same state, built on a second machine.",
        ),
        chain.step(
            "mapping-2",
            "Mapping change 2",
            kind="mapping",
            about="Five items take another background dataset.",
            claim=claims.claim(
                "Items whose supply chain reaches the changed links may move in water use; "
                "maize must.",
                [
                    claims.scope([WATER], {"p02", "p04", "p07", "p10"}, expect=claims.MAY),
                    claims.scope([WATER], {"p02"}, "up", 0.5, claims.MUST),
                ],
                by=claims.origin("code", "reach of the changed links"),
            ),
            noise=chain.noise(("fix-1", "rebuilt"), noise, "One pair of builds of one state."),
        ),
    ]


def explanations() -> list[dict]:
    return [
        chain.explanation(
            "The fertiliser amounts were per hectare; divided by the yield they are per "
            "kilogram, which lowers the nitrogen field emissions of both cereals.",
            claims.origin("person", "A. Author"),
            step="fix-1",
            indicator=CLIMATE,
            doc="docs/findings/fix-1.md",
        ),
        chain.explanation(
            "The toxicity results of rice lie far below one hundredth of the median result "
            "of the items measured per kilogram: they are counted as near zero.",
            claims.origin("code", "floor rule"),
            indicator=TOX,
            item="p05",
        ),
        chain.explanation(
            "The new mapping links tomatoes to a greenhouse heated with fresh water from a "
            "well, which multiplies the water use.",
            claims.origin("model", model="example-model-1", run_by="example maintainers (agent-run)"),
            step="mapping-2",
            indicator=WATER,
            item="p10",
            not_checked="Nobody compared the greenhouse's water balance with a second source.",
        ),
        chain.explanation(
            "Compost's toxicity result fell to almost nothing in the reproduction. The recipe, "
            "the background datasets and the method were compared; none of them explains it.",
            claims.origin("person", "B. Reviewer"),
            step="step-0",
            indicator=TOX,
            item="p08",
            finding="none found",
        ),
    ]


def build(**more) -> dict:
    """The made-up chain, counted and checked."""
    return _made(chain.build, **more)


def build_local() -> tuple[dict, dict]:
    """The same chain as a local file that lists the six worst products, and its full matrix
    of all ten: what a project keeps on its own machine."""
    return _made(chain.build_with_matrix, audience="local", listed=6)


def _made(builder, **more):
    return builder(
        "A made-up chain: published results to the current build",
        about="Made-up results of ten items in three indicators. Nobody's data.",
        indicators=INDICATORS,
        states=[
            chain.state("published", "Published", kind="published",
                        about="What the publisher released.", identity={"release": "1.0"},
                        join={"compared": 10, "unmatched": 1, "ambiguous": 0,
                              "note": "One published row names no item of the build."}),
            chain.state("repro", "Recomputed", identity={"commit": "0000001"}),
            chain.state("fix-1", "With fix 1", identity={"commit": "0000002"}),
            chain.state("rebuilt", "Rebuilt", identity={"commit": "0000002", "machine": "second"}),
            chain.state("mapping-2", "With mapping 2", identity={"commit": "0000003"}),
        ],  # fmt: skip
        steps=steps(),
        values=VALUES,
        units={k: v[1] for k, v in ITEMS.items()},
        names={k: {"name": v[0], "place": v[2], "group": v[3]} for k, v in ITEMS.items()},
        item_word=("product", "products"),
        explanations=[e for e in explanations() if more.get("tier") != "counts" or e["about"]["item"] is None],
        breakdowns={"p01": {"fix-1": "p01-fix-1.json"}},
        notes=["A made-up example: nobody's data."],
        **{"audience": "public", **more},
    )


def wheat_breakdown() -> dict:
    """What wheat's climate change result is made of, before and after fix 1."""
    parts = [
        ("Nitrogen fertiliser, production", "background process", 0.110, 0.099),
        ("Dinitrogen monoxide, field", "elementary flow", 0.180, 0.1280120),
        ("Diesel, burned in machinery", "background process", 0.090, 0.090),
        ("Seed", "background process", 0.050, 0.050),
        ("Drying", "background process", 0.040, 0.040),
        ("Transport to the mill", "background process", 0.030, 0.030),
        ("Ammonia, field", "elementary flow", 0.0, 0.010),
        ("Pesticides", "background process", 0.020013, 0.021),
    ]
    return breakdown.build("p01", "repro", "fix-1", {CLIMATE: ("kg CO2 eq", parts)}, top=5)
