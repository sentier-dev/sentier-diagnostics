"""The format of a diagnostics file, `sentier-diagnostics/1`, and its check.

A file is data from a run, so it is checked before anything shows it. `errors(data)`
returns everything wrong with it; an empty list means a page can show it. The check
refuses a key the format does not name, a text that is too long or holds a control
character, a number that is not finite, an id the file does not hold, and a list that is
too long. It then works the classes, directions, bands and verdicts of every listed item
out again from the item's own results and the file's rule, and refuses a file whose
written answers differ: a writer that counts differently cannot pass. It checks that the
counts add up, and that no item that had to be listed is missing without being counted
as not listed.

A file of another major version is refused with that reason. The reader refuses every key
it does not know, so any change to the keys is a new major version (SPEC 4.1).

Parts of the shape check are adapted from `before_after.py` of sentier-bafu (MIT,
Copyright (c) 2026 sentier.dev); see NOTICE.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path

from . import claims, rule

FORMAT = "sentier-diagnostics/1"
FAMILY = "sentier-diagnostics/"
TIERS = ("items", "counts")
AUDIENCES = ("public", "local")
FINDINGS = ("reason", "none found")
MISSING_SIDES = ("before", "after", "both")
JOIN_KEYS = {"compared", "unmatched", "ambiguous", "note"}
STATE_KINDS = ("published", "build")
TOLERANCE_BASES = ("default", "declared", "measured", "published rounding")
FLOOR_BASES = ("median", "declared", "none")
ORIGIN_KINDS = ("person", "code", "model")
TOTAL = "total"
#: Keys a file may leave out; each is null where it says nothing.
OPTIONAL_KEYS = {"matrix", "indicator"}

#: The largest file a page reads: it holds the whole file.
MAX_BYTES = 12 * 1024 * 1024
#: A claim's lists are bounded by the chain they name (`items_count.all`) and by MAX_BYTES,
#: not by a count of their own: a chain may hold more items than a file lists.
MAX_INDICATORS, MAX_STATES, MAX_ITEMS, MAX_SCOPE = 100, 30, 5000, 50
MAX_EXPLANATIONS, MAX_NOTES, MAX_IDENTITY = 500, 20, 12
MAX_ID, MAX_LABEL, MAX_WORD, MAX_TEXT, MAX_LONG = 100, 80, 40, 600, 2000
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.json")

KEYS = {
    "format", "tier", "audience", "title", "about", "item", "indicators", "rule", "states", "steps",
    "counts", "attribution", "items", "items_count", "explanations", "notes", "made_by",
}  # fmt: skip
INDICATOR_KEYS = {"id", "name", "short", "unit"}
RULE_KEYS = {"floor_factor", "floors_from", "beyond", "total_tolerance", "floors"}
#: Left out only by a file made before noise belonged to a state: such a file judges the
#: whole way without noise.
RULE_OPTIONAL = {"total_noise"}
FLOOR_KEYS = {"indicator", "unit", "value", "basis", "n"}
STATE_KEYS = {"id", "label", "about", "kind", "identity", "join"}
#: Carried by every built state of a file made since noise belongs to a state (SPEC section
#: 5.3); never by the published results, which have no builds and are exact.
STATE_OPTIONAL = {"noise"}
NOISE_KEYS = {"measured", "between", "by", "note"}
STEP_KEYS = {"id", "from", "to", "label", "about", "kind", "explained", "link", "claim",
             "tolerance", "noise"}  # fmt: skip
CLAIM_KEYS = {"text", "by", "reach", "scope"}
SCOPE_KEYS = {"indicators", "items", "direction", "largest", "expect"}
ORIGIN_KEYS = {"kind", "name", "model", "run_by"}
BLOCK_KEYS = {"pairs", "classes", "missing", "directions", "bands", "verdicts", "closer", "further"}
ITEM_KEYS = {"id", "name", "place", "group", "unit", "values", "classes", "directions",
             "bands", "verdicts", "breakdowns"}  # fmt: skip
COUNT_KEYS = {"all", "qualifying", "listed", "not_listed"}
ATTRIBUTION_KEYS = {"dominant", "not_attributable", "spread", "unexplained_moved"}
EXPLANATION_KEYS = {"about", "finding", "text", "by", "source", "not_checked"}

#: The verdicts a pair of each class can have.
ALLOWED_VERDICTS = {
    rule.MISSING: {claims.NOT_JUDGED, claims.OPEN},
    rule.NEAR_ZERO: {claims.NOT_JUDGED, claims.OPEN},
    rule.AGREES: {claims.UNCHANGED, claims.NOT_MOVED},
    rule.WITHIN_NOISE: {claims.NOISE, claims.NOT_MOVED},
    **{kind: {claims.AS_CLAIMED, claims.OFF_CLAIM, claims.NOT_CLAIMED} for kind in rule.MOVES},
}


# ------------------------------------------------------------------------ reading


def load_json(path) -> object:
    """A JSON file, read strictly: `NaN` and `Infinity` are refused, and so is a key written
    twice in one object (the last would win silently). Raises ValueError naming the file.

    >>> import tempfile, pathlib
    >>> where = pathlib.Path(tempfile.mkdtemp()) / "twice.json"
    >>> _ = where.write_text('{"a": 1, "a": 2}')
    >>> load_json(where)  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ValueError: ...twice.json: cannot be read (the key 'a' is written twice in one object)
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_refuse_constant,
                          object_pairs_hook=_refuse_twice)  # fmt: skip
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, _Twice) as error:
        raise ValueError(f"{path}: cannot be read ({error})") from None


class _Twice(ValueError):
    pass


def _refuse_twice(pairs):
    found = {}
    for key, value in pairs:
        if key in found:
            raise _Twice(f"the key {key!r} is written twice in one object")
        found[key] = value
    return found


def _refuse_constant(constant):
    raise json.JSONDecodeError(f"{constant} is not a number a file may hold", constant, 0)


# ------------------------------------------------------------------------ small checks


def is_text(value, limit: int = MAX_TEXT) -> bool:
    """A text a page can show: not empty, not too long, no control character and no half of
    a character (a lone surrogate, which cannot be written as UTF-8).

    >>> is_text("Wheat"), is_text("a\\nb"), is_text("half \\ud800"), is_text(" ")
    (True, False, False, False)
    """
    return text_fault(value, limit) is None


def text_fault(value, limit: int = MAX_TEXT) -> str | None:
    """What keeps a value from being a text a page can show, said with its limit; None for a
    text.

    >>> text_fault("Wheat"), text_fault("x" * 80, 80), text_fault("x" * 81, 80), text_fault(" "), text_fault(3)
    (None, None, 'is longer than 80 characters (81)', 'is empty', 'is not a text')
    """
    if not isinstance(value, str):
        return "is not a text"
    if not value.strip():
        return "is empty"
    if len(value) > limit:
        return f"is longer than {limit} characters ({len(value)})"
    if any(unicodedata.category(c) == "Cc" for c in value):
        return "holds a control character, such as a line break or a tab"
    if any(unicodedata.category(c) == "Cs" for c in value):
        return "holds half of a character (a lone surrogate)"
    return None


def text_errors(where: str, one: Mapping, limits: Mapping[str, int], optional=(), prefix: str = "") -> list[str]:
    """A sentence for each field of `one` that is not a text within its limit; a field named in
    `optional` may also be null.

    >>> text_errors("step 'a'", {"label": "x" * 90, "about": None}, {"label": 80, "about": 600}, optional={"about"})
    ["step 'a': `label` is longer than 80 characters (90)"]
    """
    return [
        f"{where + ': ' if where else ''}`{prefix}{name}` {fault}"
        for name, limit in limits.items()
        if not (name in optional and one[name] is None) and (fault := text_fault(one[name], limit))
    ]


#: A word that says a state was approved: SPEC 8 allows no approval of any kind in a file,
#: and a state's free `identity` table is no way round it. A stem is looked for anywhere in
#: a key, its separators taken out (`reviewed_by`, `peerReviewed`, `sign-off`); a short word
#: only as a word of its own (`ok`, not `token`). A stem can catch a key that is no approval
#: (`preview`); such a key is refused, and the state can name it otherwise. A word that sits
#: inside an ordinary one is a word of its own only (`ratified`, inside `stratified`). The
#: list deters; it cannot be complete, and values, which are free names, are not read.
APPROVAL_STEMS = re.compile(
    r"status|accept|approv|reject|review|verif|valid|certif|confirm|endors|audit|sign(ed)?off|signat|authori[sz]"
    r"|vetted|vetting|acknowledg|attest|cleared|sanction|verdict|decision|decided|granted"
)
APPROVAL_WORDS = frozenset(
    {"ok", "okay", "lgtm", "qa", "pass", "passed", "passes", "ack", "acked", "checked", "signed", "agreed", "pending",
     "ratified", "vet"}  # fmt: skip
)


def _approval(key: str) -> bool:
    """Whether a key of a state's identity says an approval. Keys are printable ASCII (the
    check of a state refuses any other), so no word hides behind a lookalike letter or an
    invisible one.

    >>> [_approval(k) for k in ("commit", "reviewed_by", "peerReviewed", "sign-off", "OK", "token", "solver")]
    [False, True, True, True, True, False, False]
    """
    words = re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", key).lower())
    return bool(APPROVAL_STEMS.search("".join(words))) or any(w in APPROVAL_WORDS for w in words)


def is_optional(value, limit: int = MAX_TEXT) -> bool:
    return value is None or is_text(value, limit)


def is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_share(value) -> bool:
    return rule.is_value(value) and value >= 0


def indicator_word(data: Mapping) -> dict:
    """What the file calls an indicator, {one, many}: its own word, or "indicator".

    >>> indicator_word({"indicator": {"one": "impact category", "many": "impact categories"}})["many"]
    'impact categories'
    >>> indicator_word({})["one"]
    'indicator'
    """
    return data.get("indicator") or {"one": "indicator", "many": "indicators"}


def first_step(data: Mapping) -> int:
    """The number of the first step: 0 where the chain starts from the published results (that
    step checks they are reproduced), 1 otherwise.

    >>> first_step({"states": [{"kind": "published"}]}), first_step({"states": [{"kind": "build"}]})
    (0, 1)
    """
    return 0 if data["states"][0]["kind"] == "published" else 1


def is_link(value) -> bool:
    return value is None or (is_text(value, 500) and value.startswith("https://"))


def origin_errors(found, where: str) -> list[str]:
    """Who wrote a claim or an explanation."""
    if not isinstance(found, dict) or set(found) != ORIGIN_KEYS:
        return [f"{where}: `by` is not {{kind, name, model, run_by}}"]
    if found["kind"] not in ORIGIN_KINDS:
        return [f"{where}: `by.kind` is not one of {', '.join(ORIGIN_KINDS)}"]
    texts = text_errors(where, found, dict.fromkeys(("name", "model", "run_by"), MAX_LABEL), ORIGIN_KEYS, "by.")
    if texts:
        return texts
    if found["kind"] in ("person", "code") and found["name"] is None:
        return [f"{where}: a {found['kind']} is named (`by.name`)"]
    if found["kind"] == "model" and (found["model"] is None or found["run_by"] is None):
        return [f"{where}: a text by a model names the model and who ran it"]
    return []


# ------------------------------------------------------------------------ the parts


def _indicators(data, found) -> list[str]:
    indicators = data.get("indicators")
    if not isinstance(indicators, list) or not 0 < len(indicators) <= MAX_INDICATORS:
        found.append(f"`indicators` is not a list of 1 to {MAX_INDICATORS}")
        return []
    ids = []
    for one in indicators:
        if not isinstance(one, dict) or set(one) != INDICATOR_KEYS:
            found.append("an indicator is not {id, name, short, unit}")
            return []
        if text_fault(one["id"], MAX_ID):
            found.append(f"an indicator's `id` {text_fault(one['id'], MAX_ID)}")
            return []
        where = f"indicator {one['id']!r}"
        if text_fault(one["name"], MAX_ID):
            found += text_errors(where, one, {"name": MAX_ID})
            return []
        found += text_errors(where, one, {"short": MAX_WORD, "unit": MAX_WORD}, {"short", "unit"})
        ids.append(one["id"])
    if len(set(ids)) != len(ids):
        found.append("two indicators have the same id")
        return []
    return ids


def _states(data, found, indicators) -> list[str]:
    states = data.get("states")
    if not isinstance(states, list) or not 2 <= len(states) <= MAX_STATES:
        found.append(f"`states` is not a list of 2 to {MAX_STATES}")
        return []
    ids = []
    for k, one in enumerate(states):
        if (
            not isinstance(one, dict)
            or not STATE_KEYS <= set(one) <= STATE_KEYS | STATE_OPTIONAL
        ):
            found.append(f"a state is not {{{', '.join(sorted(STATE_KEYS))}}}, with `noise`")
            return []
        if text_fault(one["id"], MAX_ID):
            found.append(f"a state's `id` {text_fault(one['id'], MAX_ID)}")
            return []
        where = f"state {one['id']!r}"
        found += text_errors(where, one, {"label": MAX_LABEL, "about": MAX_TEXT}, {"about"})
        if one["kind"] not in STATE_KINDS:
            found.append(f"{where}: `kind` is not one of {', '.join(STATE_KINDS)}")
        elif one["kind"] == "published" and k != 0:
            found.append(f"{where}: only the first state can be the published results")
        if "noise" in one:
            if one["kind"] == "published":
                found.append(f"{where}: the published results have no builds and carry no noise: they are exact")
                return []
            shape = noise_errors(one["noise"], where, indicators)
            if shape:
                found += shape
                return []
        identity = one["identity"]
        if not isinstance(identity, dict) or len(identity) > MAX_IDENTITY:
            found.append(f"{where}: `identity` is not a table of at most {MAX_IDENTITY} entries")
        elif any(text_fault(k2, MAX_WORD) or text_fault(v, 200) for k2, v in identity.items()):
            found += [f"{where}: the key {k2!r} of `identity` {text_fault(k2, MAX_WORD)}"
                      for k2 in identity if text_fault(k2, MAX_WORD)]  # fmt: skip
            found += text_errors(where, identity, {k2: 200 for k2 in identity if not text_fault(k2, MAX_WORD)}, (), "identity.")
        elif not all(k2.isascii() and k2.isprintable() for k2 in identity):
            found.append(f"{where}: a key of `identity` is printable ASCII, so that no word hides in it")
        elif any(_approval(k2) for k2 in identity):
            found.append(f"{where}: `identity` names what makes a state, never a status or an approval (SPEC 8)")
        join = one["join"]
        if join is not None and not (
            isinstance(join, dict)
            and set(join) == JOIN_KEYS
            and all(is_count(join[k2]) for k2 in ("compared", "unmatched", "ambiguous"))
        ):
            found.append(f"{where}: `join` is not {{compared, unmatched, ambiguous, note}}")
        elif join is not None:
            found += text_errors(where, join, {"note": MAX_TEXT}, {"note"}, "join.")
        ids.append(one["id"])
    if len(set(ids)) != len(ids):
        found.append("two states have the same id")
        return []
    if len({"noise" in one for one in states if one["kind"] != "published"}) > 1:
        found.append("some built states carry their noise and some do not: all do, or none (a file made before noise belonged to a state)")
        return []
    return ids


def claim_errors(found_claim, where, indicators, tier) -> list[str]:
    """Everything wrong with a claim: its shape first, then whether its `reach` is the size of
    its lists."""
    found = _claim_shape(found_claim, where, indicators, tier)
    if found:
        return found
    size = claims.reach_of(found_claim["scope"])
    if size is not None and found_claim["reach"] != size:
        found.append(f"{where}: the reach of a claim is {found_claim['reach']}, and its lists name {size} items")
    if found_claim["reach"] is not None and claims.lists_nothing(found_claim["scope"]):
        found.append(f"{where}: the reach of a claim is {found_claim['reach']}, and no entry of it lists items")
    return found


def _claim_shape(found_claim, where, indicators, tier) -> list[str]:
    """What keeps a claim from being read: a page or the validator cannot judge with it."""
    if not isinstance(found_claim, dict) or set(found_claim) != CLAIM_KEYS:
        return [f"{where}: `claim` is not {{text, by, reach, scope}}"]
    found = []
    if text_fault(found_claim["text"]):
        found.append(f"{where}: a claim says what it claims, and its `text` {text_fault(found_claim['text'])}")
    if found_claim["by"] is not None:
        found += origin_errors(found_claim["by"], where)
    if found_claim["reach"] is not None and not is_count(found_claim["reach"]):
        found.append(f"{where}: the reach of a claim is not a count")
    entries = found_claim["scope"]
    if not isinstance(entries, list) or len(entries) > MAX_SCOPE:
        return [*found, f"{where}: the scope of a claim is not a list of at most {MAX_SCOPE}"]
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != SCOPE_KEYS:
            return [*found, f"{where}: a scope entry is not {{{', '.join(sorted(SCOPE_KEYS))}}}"]
        named, items = entry["indicators"], entry["items"]
        if named != "*" and not (
            isinstance(named, list) and all(isinstance(i, str) for i in named) and set(named) <= set(indicators)
        ):
            found.append(f"{where}: a scope's indicators are not '*' or ids the file holds")
        if items not in ("*", None):
            if tier == "counts":
                found.append(f"{where}: a file of counts lists no item in a claim")
            elif not (
                isinstance(items, list)
                and all(is_text(i, MAX_ID) for i in items)
                and len(set(items)) == len(items)
            ):
                found.append(f"{where}: the items of a scope are not a list of distinct ids, each a text of at most {MAX_ID} characters")
        if entry["direction"] not in claims.WAYS:
            found.append(f"{where}: a scope's direction is not one of {', '.join(claims.WAYS)}")
        if entry["largest"] is not None and not is_share(entry["largest"]):
            found.append(f"{where}: a scope's largest move is not a share")
        if entry["expect"] not in claims.EXPECTS:
            found.append(f"{where}: a scope says whether its values must or may move")
    return found


def _steps(data, found, states, indicators, tier) -> list[dict]:
    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) != max(0, len(states) - 1):
        found.append("`steps` is not a list of one step fewer than the states")
        return []
    ids = []
    for k, one in enumerate(steps):
        if not isinstance(one, dict) or set(one) != STEP_KEYS:
            found.append(f"a step is not {{{', '.join(sorted(STEP_KEYS))}}}")
            return []
        if text_fault(one["id"], MAX_ID):
            found.append(f"a step's `id` {text_fault(one['id'], MAX_ID)}")
            return []
        where = f"step {one['id']!r}"
        if one["id"] == TOTAL:
            found.append(f"{where}: `total` names the whole way and is no step's id")
        if (one["from"], one["to"]) != (states[k], states[k + 1]):
            found.append(f"{where}: it does not lead from state {states[k]!r} to {states[k + 1]!r}")
        found += text_errors(where, one, {"label": MAX_LABEL, "about": MAX_TEXT, "kind": MAX_WORD}, {"about"})
        if not isinstance(one["explained"], bool):
            found.append(f"{where}: a step says whether a cause explains it (`explained`: true or false)")
        if not is_link(one["link"]):
            found.append(f"{where}: `link` is not an https address of at most 500 characters")
        if one["claim"] is not None:
            shape = _claim_shape(one["claim"], where, indicators, tier)
            if shape:  # nothing can be judged against a claim that cannot be read
                found += shape
                return []
            found += claim_errors(one["claim"], where, indicators, tier)
        said = one["tolerance"]
        if not (
            isinstance(said, dict)
            and set(said) == {"value", "basis", "note"}
            and is_share(said["value"])
            and said["basis"] in TOLERANCE_BASES
        ):
            found.append(f"{where}: `tolerance` is not {{value, basis, note}}")
            return []
        note = text_errors(where, said, {"note": MAX_TEXT}, {"note"}, "tolerance.")
        if note:
            found += note
            return []
        if states_carry_noise(data):
            # the step's noise is its two states', the larger per indicator (SPEC section 5.3)
            if one["noise"] != noise_of_states(data["states"][k], data["states"][k + 1]):
                found.append(f"{where}: `noise` is not the sum of the noise of its two states, per indicator")
                return []
        else:
            shape = noise_errors(one["noise"], where, indicators)
            if shape:
                found += shape
                return []
        ids.append(one["id"])
    if len(set(ids)) != len(ids):
        found.append("two steps have the same id")
        return []
    return steps


def noise_errors(noise, where: str, indicators) -> list[str]:
    """What is wrong with a measured noise: of a state, or of a step in a file made before noise
    belonged to a state. Measured noise names its two builds and a size per indicator; noise
    that was not measured has neither."""
    if not (
        isinstance(noise, dict)
        and set(noise) == NOISE_KEYS
        and isinstance(noise["measured"], bool)
    ):
        return [f"{where}: `noise` is not {{measured, between, by, note}}"]
    note = text_errors(where, noise, {"note": MAX_TEXT}, {"note"}, "noise.")
    if note:
        return note
    if noise["measured"]:
        if not (
            isinstance(noise["between"], list)
            and len(noise["between"]) == 2
            and isinstance(noise["by"], dict)
            and set(noise["by"]) <= set(indicators)
            and all(is_share(v) for v in noise["by"].values())
        ):
            return [f"{where}: measured noise names the two builds and a size per indicator"]
        if any(text_fault(n, MAX_LABEL) for n in noise["between"]):
            return [f"{where}: a build that `noise.between` names {text_fault(n, MAX_LABEL)}"
                    for n in noise["between"] if text_fault(n, MAX_LABEL)]  # fmt: skip
    elif noise["between"] is not None or noise["by"] is not None:
        return [f"{where}: noise that was not measured has no builds and no sizes"]
    return []


def states_carry_noise(data: Mapping) -> bool:
    """Whether the file says the noise of each built state (SPEC section 5.3). A file made before
    noise belonged to a state says a noise per step only, and never which state it was measured
    on. The published results carry none in either: they are exact.

    >>> built = {"kind": "build", "noise": {}}
    >>> states_carry_noise({"states": [{"kind": "published"}, built]}), states_carry_noise({"states": [{"kind": "build"}] * 2})
    (True, False)
    """
    return all("noise" in one for one in data["states"] if one["kind"] != "published")


def noise_of_states(first: Mapping, last: Mapping) -> dict:
    """The noise two states are compared with: per indicator, the sum of the noise of the two
    (SPEC section 5.3). Two builds of a state differ by its noise, so rebuilding both ends moves
    their difference by up to the sum of theirs. The pair holds the results of those two states
    only, so the noise of any state between them is not in it. The published results are exact
    and add nothing; a built state that did not measure an indicator adds nothing to it, and the
    page says at how many ends the noise was measured. An indicator measured at no end is left
    out: not measured, which is not the same as two identical builds. The noise of a step, in a
    file whose states carry their noise.

    >>> built = lambda by: {"kind": "build", "noise": {"measured": by is not None, "between": by and ["x", "y"], "by": by, "note": None}}
    >>> noise_of_states(built({"a": 1e-9}), built({"a": 3e-9, "b": 2e-9}))["by"]
    {'a': 4e-09, 'b': 2e-09}
    >>> noise_of_states({"kind": "published"}, built({"a": 0.0}))
    {'measured': True, 'between': None, 'by': {'a': 0.0}, 'note': None}
    >>> noise_of_states({"kind": "published"}, built(None))["measured"]
    False
    """
    measured = [one["noise"] for one in (first, last) if one["kind"] != "published" and one["noise"]["measured"]]
    if not measured:
        return {"measured": False, "between": None, "by": None, "note": None}
    by: dict[str, float] = {}
    for said in measured:
        for indicator, value in said["by"].items():
            by[indicator] = by.get(indicator, 0.0) + value
    return {"measured": True, "between": None, "by": by, "note": None}


def ends_known(first: Mapping, last: Mapping, indicator: str) -> int:
    """At how many of the two ends the noise of `indicator` is known: an end is known where it
    is the published results (exact) or a build that measured it.

    >>> built = lambda by: {"kind": "build", "noise": {"measured": by is not None, "between": None, "by": by, "note": None}}
    >>> ends_known({"kind": "published"}, built({"a": 0.1}), "a"), ends_known(built(None), built({"a": 0.1}), "a")
    (2, 1)
    """
    return sum(
        1 for one in (first, last)
        if one["kind"] == "published" or (one["noise"]["measured"] and indicator in one["noise"]["by"])
    )  # fmt: skip


def pair_noise(data: Mapping, first: int, last: int) -> dict[str, float]:
    """The noise per indicator that the states at places `first` and `last` are compared with:
    that of the two states (`noise_of_states`); nothing in a file whose states carry no noise,
    which never says which state its noise belongs to."""
    if not states_carry_noise(data):
        return {}
    return noise_of_states(data["states"][first], data["states"][last])["by"] or {}


def total_noise_level(data: Mapping, indicator: str) -> float | None:
    """The noise the whole way is judged with in one indicator: that of its first and last
    state; None where neither measured it, or the file was made before noise belonged to a
    state."""
    return (data["rule"].get("total_noise") or {}).get(indicator)


def _rule(data, found, indicators, states, steps) -> dict | None:
    said = data.get("rule")
    if not isinstance(said, dict) or not RULE_KEYS <= set(said) <= RULE_KEYS | RULE_OPTIONAL:
        found.append(f"`rule` is not {{{', '.join(sorted(RULE_KEYS))}}}, with `total_noise`")
        return None
    if not is_share(said["floor_factor"]):
        found.append("`rule`: the floor factor is not a share")
    if said["floors_from"] != states[0]:
        found.append("`rule`: the floors come from the first state")
    if said["beyond"] != rule.BEYOND_FACTOR:
        found.append(f"`rule.beyond` is {rule.BEYOND_FACTOR:g}: one rule for every file")
    if not is_share(said["total_tolerance"]):
        found.append("`rule.total_tolerance` is not a share")
        return None
    if steps and said["total_tolerance"] != max(s["tolerance"]["value"] for s in steps):
        found.append("`rule.total_tolerance` is not the largest tolerance of the steps")
    if "total_noise" in said:
        given = said["total_noise"]
        if not (isinstance(given, dict) and set(given) <= set(indicators)
                and all(is_share(v) for v in given.values())):  # fmt: skip
            found.append("`rule.total_noise` is not a share per indicator")
            return None
        if not states_carry_noise(data):
            found.append("`rule.total_noise` is the noise of the first and last state, and this file's states carry none")
        elif given != pair_noise(data, 0, len(data["states"]) - 1):
            found.append("`rule.total_noise` is not the sum of the noise of the first and last state, per indicator")
    elif states and states_carry_noise(data):
        found.append("`rule.total_noise` is required where the states carry their noise")
    floors = said["floors"]
    if not isinstance(floors, list):
        found.append("`rule.floors` is not a list")
        return None
    table = {}
    for one in floors:
        if not (
            isinstance(one, dict)
            and set(one) == FLOOR_KEYS
            and one["indicator"] in indicators
            and is_share(one["value"])
            and one["basis"] in FLOOR_BASES
            and is_count(one["n"])
        ):
            found.append("a floor is not {indicator, unit, value, basis, n} of a known indicator")
            return None
        unit = text_errors(f"the floor of {one['indicator']!r}", one, {"unit": MAX_WORD}, {"unit"})
        if unit:
            found += unit
            return None
        key = (one["indicator"], one["unit"])
        if key in table:
            found.append(f"two floors for {one['indicator']!r} in unit {one['unit']!r}")
        basis, n, value = one["basis"], one["n"], one["value"]
        if (basis == "none" and (n or value)) or (basis == "median" and not n) or (basis == "declared" and n):
            found.append(
                f"the floor of {one['indicator']!r} in unit {one['unit']!r}: basis {basis!r} with "
                f"{n} results and the value {value!r} (a median is taken from results, none is 0 from "
                "none, a declared floor from none)"
            )
        table[key] = value
    return table


def _block(block, where, step) -> list[str]:
    if not isinstance(block, dict) or set(block) != BLOCK_KEYS:
        return [f"{where}: counts are not {{{', '.join(sorted(BLOCK_KEYS))}}}"]
    found = []
    if not is_count(block["pairs"]):
        return [f"{where}: `pairs` is not a count"]
    classes, bands, verdicts = block["classes"], block["bands"], block["verdicts"]
    if not (isinstance(classes, dict) and set(classes) == set(rule.CLASSES)
            and all(map(is_count, classes.values()))):  # fmt: skip
        return [f"{where}: `classes` is not a count for each class"]
    if sum(classes.values()) != block["pairs"]:
        found.append(f"{where}: the classes do not add up to the pairs")
    missing = block["missing"]
    if not (isinstance(missing, dict) and set(missing) == set(MISSING_SIDES)
            and all(map(is_count, missing.values()))):  # fmt: skip
        return [*found, f"{where}: `missing` is not a count for before, after and both"]
    if sum(missing.values()) != classes[rule.MISSING]:
        found.append(f"{where}: missing before, after and on both sides do not add up to missing")
    if not (isinstance(bands, dict) and set(bands) == set(rule.BANDS)
            and all(map(is_count, bands.values()))):  # fmt: skip
        return [*found, f"{where}: `bands` is not a count for each band"]
    if sum(bands.values()) != classes[rule.DIFFERS] + classes[rule.BEYOND]:
        found.append(f"{where}: the bands do not add up to what differs and what is beyond 10x")
    ways = block["directions"]
    if not (isinstance(ways, dict) and set(ways) == set(rule.DIRECTIONS)
            and all(map(is_count, ways.values()))):  # fmt: skip
        return [*found, f"{where}: `directions` is not a count for up and for down"]
    if sum(ways.values()) != sum(classes[k] for k in rule.MOVES):
        found.append(f"{where}: up and down do not add up to what moved")
    for way in rule.DIRECTIONS:
        banded = sum(n for name, n in bands.items() if name.startswith(way + ","))
        if banded > ways[way]:
            found.append(f"{where}: more bands {way} than values that went {way}")
    has_claim = step is not None and step["claim"] is not None
    if has_claim:
        if not (isinstance(verdicts, dict) and set(verdicts) == set(claims.VERDICTS)
                and all(map(is_count, verdicts.values()))):  # fmt: skip
            return [*found, f"{where}: `verdicts` is not a count for each verdict"]
        if sum(verdicts.values()) != block["pairs"]:
            found.append(f"{where}: the verdicts do not add up to the pairs")
    elif verdicts is not None:
        found.append(f"{where}: verdicts without a claim")
    for key in ("closer", "further"):
        if block[key] is not None and not is_count(block[key]):
            found.append(f"{where}: `{key}` is not a count")
    moved = sum(classes[k] for k in rule.MOVES)
    if is_count(block["closer"]) and is_count(block["further"]):
        if block["closer"] + block["further"] > moved:
            found.append(f"{where}: more came closer or went further than moved")
    return found


def _counts(data, found, indicators, steps, total_pairs):
    counts = data.get("counts")
    if not isinstance(counts, dict) or set(counts) != {"steps", TOTAL}:
        found.append("`counts` is not {steps, total}")
        return {}
    by_step = counts["steps"]
    if not isinstance(by_step, dict) or set(by_step) != {s["id"] for s in steps}:
        found.append("`counts.steps` does not hold every step")
        return {}
    published_first = data["states"][0]["kind"] == "published"
    blocks = {}
    for k, one in enumerate([*steps, None]):
        key = one["id"] if one else TOTAL
        table = by_step[key] if one else counts[TOTAL]
        if not isinstance(table, dict) or set(table) != set(indicators):
            found.append(f"counts of {key!r} do not hold every indicator")
            return {}
        # closer and further: only for a step after step 0, and only from published results
        counted_closer = published_first and one is not None and k > 0
        for indicator in indicators:
            where = f"counts of {key!r} in {indicator!r}"
            errors = _block(table[indicator], where, one)
            found += errors
            if errors:
                continue
            if table[indicator]["pairs"] != total_pairs:
                found.append(f"{where}: not every item is counted")
            if counted_closer != (table[indicator]["closer"] is not None) or counted_closer != (
                table[indicator]["further"] is not None
            ):
                found.append(
                    f"{where}: `closer` and `further` are counted for a step after step 0 from "
                    "published results, and are null everywhere else"
                )
            blocks[(key, indicator)] = table[indicator]
    return blocks


def _attribution(data, found, indicators, steps, blocks):
    said = data.get("attribution")
    if not isinstance(said, dict) or set(said) != set(indicators):
        found.append("`attribution` does not hold every indicator")
        return
    for indicator in indicators:
        one = said[indicator]
        where = f"attribution in {indicator!r}"
        if not (
            isinstance(one, dict)
            and set(one) == ATTRIBUTION_KEYS
            and isinstance(one["dominant"], dict)
            and set(one["dominant"]) == {s["id"] for s in steps}
            and all(map(is_count, one["dominant"].values()))
            and all(is_count(one[k]) for k in ("not_attributable", "spread", "unexplained_moved"))
        ):
            found.append(f"{where}: not {{dominant per step, not_attributable, spread, unexplained_moved}}")
            continue
        block = blocks.get((TOTAL, indicator))
        if block:
            moved = sum(block["classes"][k] for k in rule.MOVES)
            if sum(one["dominant"].values()) + one["not_attributable"] + one["spread"] != moved:
                found.append(f"{where}: does not account for every item whose total moved")


def _items(data, found, indicators, states, steps, floors, tier, blocks):
    listed = data.get("items")
    said = data.get("items_count")
    if not (isinstance(said, dict) and set(said) == COUNT_KEYS and all(map(is_count, said.values()))):
        found.append("`items_count` is not {all, qualifying, listed, not_listed} in counts")
        return []
    if said["qualifying"] != said["listed"] + said["not_listed"] or said["qualifying"] > said["all"]:
        found.append("`items_count`: the items listed and not listed are not those worth a look")
    if not isinstance(listed, list) or len(listed) > MAX_ITEMS or len(listed) != said["listed"]:
        found.append(f"`items` is not a list of the {said['listed']} items said to be listed, "
                     f"and of at most {MAX_ITEMS}")  # fmt: skip
        return []
    if tier == "counts" and listed:
        found.append("a file of counts holds no item")
        return []
    nsteps = len(steps)
    claims_by_step = [_in_hand(s["claim"]) for s in steps]
    any_claim = any(claims_by_step)
    published_first = data["states"][0]["kind"] == "published"
    seen, previous_key = set(), None
    # what the listed items hold, counted as the blocks count it: every part of a block that
    # only a pair worth a look can add to (`_LOUD`), and the attribution
    tally: dict[tuple[str, str], dict] = {}
    attributed = {
        i: {"dominant": dict.fromkeys((s["id"] for s in steps), 0), "not_attributable": 0, "spread": 0,
            "unexplained_moved": 0}
        for i in indicators
    }  # fmt: skip
    for item in listed:
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            found.append(f"an item is not {{{', '.join(sorted(ITEM_KEYS))}}}")
            return []
        if text_fault(item["id"], MAX_ID):
            found.append(f"an item's `id` {text_fault(item['id'], MAX_ID)}")
            return []
        where = f"item {item['id']!r}"
        if item["id"] in seen:
            found.append(f"{where} is listed twice")
        seen.add(item["id"])
        found += text_errors(where, item, {"name": 300})
        texts = text_errors(where, item, {"place": 60, "group": MAX_LABEL, "unit": MAX_WORD}, {"place", "group", "unit"})
        if texts:
            found += texts
            return []
        tables = [item[k] for k in ("values", "classes", "directions", "bands")]
        if not all(isinstance(t, dict) and set(t) == set(indicators) for t in tables):
            found.append(f"{where}: results, classes, directions and bands are given for every indicator")
            return []
        if any_claim != isinstance(item["verdicts"], dict) or (
            any_claim and set(item["verdicts"]) != set(indicators)
        ):
            found.append(f"{where}: verdicts are given for every indicator where, and only where, a step has a claim")
            return []
        breakdowns = item["breakdowns"]
        if breakdowns is not None and not (
            isinstance(breakdowns, dict)
            and set(breakdowns) <= {s["id"] for s in steps} | {TOTAL}
            and all(isinstance(f, str) and FILE_NAME.fullmatch(f) for f in breakdowns.values())
        ):
            found.append(f"{where}: `breakdowns` names a step it does not know or a file that is a path")
        worth, keys = False, []
        for indicator in indicators:
            values = item["values"][indicator]
            kinds, ways, bands = (item[k][indicator] for k in ("classes", "directions", "bands"))
            if not (isinstance(values, list) and len(values) == len(states)
                    and all(v is None or rule.is_value(v) for v in values)):  # fmt: skip
                found.append(f"{where}, {indicator}: the results are not one finite number or null per state")
                return []
            if not all(isinstance(x, list) and len(x) == nsteps + 1 for x in (kinds, ways, bands)):
                found.append(f"{where}, {indicator}: classes, directions and bands are one per step and the total")
                return []
            floor = floors.get((indicator, item["unit"]))
            if floor is None:
                found.append(f"{where}, {indicator}: the file holds no floor for unit {item['unit']!r}")
                return []
            verdicts = item["verdicts"][indicator] if any_claim else None
            if any_claim and not (isinstance(verdicts, list) and len(verdicts) == nsteps):
                found.append(f"{where}, {indicator}: verdicts are one per step")
                return []
            for k in [*range(nsteps), None]:
                at = nsteps if k is None else k
                name = TOTAL if k is None else steps[k]["id"]
                before, after = (values[0], values[-1]) if k is None else (values[k], values[k + 1])
                if k is None:
                    tol, level = data["rule"]["total_tolerance"], total_noise_level(data, indicator)
                else:
                    tol = steps[k]["tolerance"]["value"]
                    noise = steps[k]["noise"]
                    level = (noise["by"] or {}).get(indicator) if noise["measured"] else None
                expected = rule.judge(before, after, floor=floor, tolerance=tol, noise=level)
                if (kinds[at], ways[at], bands[at]) != expected:
                    found.append(
                        f"{where}, {indicator}, {name}: written as {kinds[at]!r}/{ways[at]!r}/"
                        f"{bands[at]!r}, the rule gives {expected[0]!r}/{expected[1]!r}/{expected[2]!r}"
                    )
                    return []
                one = tally.setdefault((name, indicator), {})
                kind = kinds[at]
                if kind not in rule.QUIET:
                    _add(one, ("classes", kind))
                if kind == rule.MISSING:
                    _add(one, ("missing", "both" if before is None and after is None
                               else "before" if before is None else "after"))  # fmt: skip
                if ways[at]:
                    _add(one, ("directions", ways[at]))
                if bands[at]:
                    _add(one, ("bands", bands[at]))
                if published_first and k not in (None, 0) and kind in rule.MOVES and values[0] is not None:
                    was, now = abs(before - values[0]), abs(after - values[0])
                    one.setdefault(("closer",), 0)
                    one.setdefault(("further",), 0)
                    one[("closer",)] += now < was
                    one[("further",)] += now > was
                keys.append(rule.severity(before, after, kind))
                worth = worth or kind not in rule.QUIET
                if k is None or not any_claim:
                    continue
                said_verdict = verdicts[k]
                step_claim = claims_by_step[k]
                if step_claim is None:
                    if said_verdict is not None:
                        found.append(f"{where}, {indicator}, {name}: a verdict without a claim")
                    continue
                if not isinstance(said_verdict, str) or said_verdict not in ALLOWED_VERDICTS[kinds[at]]:
                    found.append(f"{where}, {indicator}, {name}: {kinds[at]!r} cannot be {said_verdict!r}")
                    return []
                worth = worth or said_verdict in claims.TO_LOOK_AT
                if claims.judgeable(step_claim):
                    covering = [
                        e for e in claims.entries_for(step_claim, indicator)
                        if claims.covers(e, item["id"], indicator)
                    ]  # fmt: skip
                    again = claims.verdict(kinds[at], before, after, ways[at], covering)
                    if again != said_verdict:
                        found.append(f"{where}, {indicator}, {name}: written {said_verdict!r}, the claim gives {again!r}")
                        return []
                if said_verdict in _LOUD_VERDICTS:
                    _add(one, ("verdicts", said_verdict))
            # attribution of this item in this indicator, as `chain.build` makes it
            if kinds[nsteps] in rule.MOVES:
                if any(v is None for v in values):
                    attributed[indicator]["not_attributable"] += 1
                else:
                    carrier = rule.largest_step(values, kinds[:nsteps])
                    if carrier is None:
                        attributed[indicator]["spread"] += 1
                    else:
                        attributed[indicator]["dominant"][steps[carrier]["id"]] += 1
            if any(not steps[j]["explained"] and kinds[j] in rule.MOVES for j in range(nsteps)):
                attributed[indicator]["unexplained_moved"] += 1
        if not worth:
            found.append(f"{where}: listed, though nothing in it is worth a look")
        key = (min(keys), item["id"])
        if previous_key is not None and key < previous_key:
            found.append(f"{where}: the items are not listed the worst first")
        previous_key = key
    # Only a pair worth a look adds to these parts of a block, and every item with such a pair
    # is worth a look. So nothing listed can be more than was counted, and with nothing left
    # out (`not_listed` 0) the listed items hold exactly what was counted.
    exact = said["not_listed"] == 0
    left_out = f"{said['not_listed']} said not to be listed"
    for (name, indicator), block in blocks.items():
        one = tally.get((name, indicator), {})
        parts = [("classes", k) for k in rule.CLASSES if k not in rule.QUIET]
        parts += [("missing", k) for k in MISSING_SIDES] + [("directions", k) for k in rule.DIRECTIONS]
        parts += [("bands", k) for k in rule.BANDS]
        if block["verdicts"] is not None:
            parts += [("verdicts", k) for k in claims.VERDICTS if k in _LOUD_VERDICTS]
        if block["closer"] is not None:
            parts += [("closer",), ("further",)]
        for part in parts:
            counted = block[part[0]] if len(part) == 1 else block[part[0]][part[1]]
            if not is_count(counted):
                continue  # `_counts` has said what is wrong with it
            n = one.get(part, 0)
            if n > counted or (exact and n != counted):
                found.append(
                    f"counts of {name!r} in {indicator!r}: {counted} {' '.join(map(str, part))!r}, "
                    f"{n} in the listed items, {left_out}"
                )
    said_attribution = data.get("attribution")
    for indicator in indicators:
        one = said_attribution.get(indicator) if isinstance(said_attribution, dict) else None
        if not (isinstance(one, dict) and isinstance(one.get("dominant"), dict)):
            continue  # `_attribution` has said what is wrong with it
        mine = attributed[indicator]
        pairs = [(f"dominant {s}", mine["dominant"][s], one["dominant"].get(s)) for s in mine["dominant"]]
        pairs += [(k, mine[k], one.get(k)) for k in ("not_attributable", "spread", "unexplained_moved")]
        for label, n, counted in pairs:
            if not is_count(counted):
                continue
            if n > counted or (exact and n != counted):
                found.append(f"attribution in {indicator!r}: {counted} {label}, {n} in the listed items, {left_out}")
    return [i["id"] for i in listed]


#: The verdicts only a pair worth a look can have.
_LOUD_VERDICTS = frozenset({claims.AS_CLAIMED, *claims.TO_LOOK_AT})


def _add(tally: dict, key: tuple) -> None:
    tally[key] = tally.get(key, 0) + 1


def _explanations(data, found, indicators, steps, items, tier):
    said = data.get("explanations")
    if not isinstance(said, list) or len(said) > MAX_EXPLANATIONS:
        found.append(f"`explanations` is not a list of at most {MAX_EXPLANATIONS}")
        return
    step_ids = {s["id"] for s in steps} | {TOTAL}
    for k, one in enumerate(said):
        where = f"explanation {k + 1}"
        if not isinstance(one, dict) or set(one) != EXPLANATION_KEYS:
            found.append(f"{where}: not {{{', '.join(sorted(EXPLANATION_KEYS))}}}")
            continue
        about = one["about"]
        if not (isinstance(about, dict) and set(about) == {"step", "indicator", "item"}):
            found.append(f"{where}: `about` is not {{step, indicator, item}}")
            continue
        if not all(is_optional(v, MAX_ID) for v in about.values()):
            found.append(f"{where}: `about` names a step, an indicator and an item by their ids, or null")
            found += text_errors(where, about, dict.fromkeys(about, MAX_ID), set(about), "about.")
            continue
        if all(v is None for v in about.values()):
            found.append(f"{where}: it is about something: a step, an indicator or an item")
        if about["step"] is not None and about["step"] not in step_ids:
            found.append(f"{where}: about a step the file does not hold")
        if about["indicator"] is not None and about["indicator"] not in indicators:
            found.append(f"{where}: about an indicator the file does not hold")
        if about["item"] is not None:
            if tier == "counts":
                found.append(f"{where}: a file of counts explains no single item")
            elif about["item"] not in items:
                found.append(f"{where}: about an item the file does not list")
        if one["finding"] not in FINDINGS:
            found.append(f"{where}: `finding` is not one of {', '.join(FINDINGS)}")
        found += text_errors(where, one, {"text": MAX_LONG})
        if one["by"] is None:
            found.append(f"{where}: every explanation says who wrote it (`by`)")
        else:
            found += origin_errors(one["by"], where)
        source = one["source"]
        if source is not None and not (
            isinstance(source, dict)
            and set(source) == {"link", "doc"}
            and is_link(source["link"])
        ):
            found.append(f"{where}: `source` is not {{link, doc}}")
        elif source is not None:
            found += text_errors(where, source, {"doc": 200}, {"doc"}, "source.")
        found += text_errors(where, one, {"not_checked": MAX_TEXT}, {"not_checked"})


# ------------------------------------------------------------------------ the whole file


#: How a fault begins where the check met a value it could not read and had to stop. The
#: check names the place of every wrong value it knows of; this is the backstop for the
#: rest, so that `errors` never raises (a test feeds every node values of other types).
STOPPED = "the check stopped at a value it cannot read"


def errors(data) -> list[str]:
    """Everything wrong with a diagnostics file; nothing when a page can show it. Never
    raises: a value of the wrong type is a fault like any other."""
    found: list[str] = []
    try:
        return _errors(data, found)
    except Exception as error:  # noqa: BLE001 - the backstop of a check that must not raise
        return [*found, f"{STOPPED} ({type(error).__name__}: {str(error)[:200]})"]


def _errors(data, found: list[str]) -> list[str]:
    if not isinstance(data, Mapping):
        return ["not a diagnostics file: not an object"]
    said = data.get("format")
    if said != FORMAT:
        if isinstance(said, str) and said.startswith(FAMILY):
            return [f"format {said!r}: this reader knows {FORMAT} only"]
        return [f"not a diagnostics file of format {FORMAT}"]
    found += [f"a key this format does not know: {key}" for key in sorted(set(data) - KEYS - OPTIONAL_KEYS)]
    found += [f"a key this format requires: {key}" for key in sorted(KEYS - set(data))]
    if found:
        return found
    tier = data["tier"]
    if tier not in TIERS:
        return [f"`tier` is not one of {', '.join(TIERS)}"]
    if data["audience"] not in AUDIENCES:
        return [f"`audience` is not one of {', '.join(AUDIENCES)}"]
    found += text_errors("", data, {"title": 120, "about": MAX_TEXT, "made_by": 60}, {"about"})
    item = data["item"]
    if not (isinstance(item, dict) and set(item) == {"one", "many"}):
        found.append("`item` is not {one, many}")
    else:
        found += text_errors("", item, {"one": 30, "many": 30}, (), "item.")
    word = data.get("indicator")
    if word is not None and not (isinstance(word, dict) and set(word) == {"one", "many"}):
        found.append("`indicator` is not {one, many}, or null")
    elif word is not None:
        found += text_errors("", word, {"one": 30, "many": 30}, (), "indicator.")
    notes = data["notes"]
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        found.append(f"`notes` is not a list of at most {MAX_NOTES} texts")
    else:
        found += [f"note {k + 1} {text_fault(note)}" for k, note in enumerate(notes) if text_fault(note)]
    indicators = _indicators(data, found)
    states = _states(data, found, indicators)
    if not indicators or not states:
        return found
    steps = _steps(data, found, states, indicators, tier)
    if not steps:
        return found
    floors = _rule(data, found, indicators, states, steps)
    count = data["items_count"]
    total_pairs = count.get("all") if isinstance(count, dict) else None
    _reach(found, steps, total_pairs)
    blocks = _counts(data, found, indicators, steps, total_pairs)
    if floors is None or not blocks:
        return found
    _attribution(data, found, indicators, steps, blocks)
    items = _items(data, found, indicators, states, steps, floors, tier, blocks)
    _explanations(data, found, indicators, steps, set(items), tier)
    _matrix(data, found)
    return found


def _reach(found, steps, total) -> None:
    """A claim names items of its chain, so it reaches no more items than the chain holds:
    this bounds its lists, and where they stay private, the size it says they have."""
    if not is_count(total):
        return  # `_items` says why the count cannot be read
    for one in steps:
        reach = (one["claim"] or {}).get("reach")
        if is_count(reach) and reach > total:
            found.append(f"step {one['id']!r}: its claim reaches {reach} items, and the chain holds {total}")


def smaller_by(data) -> str:
    """What makes a file smaller: fewer listed items and, where a claim lists items, leaving
    its lists out. Reads a file that may not be well formed."""
    steps = data.get("steps") if isinstance(data, Mapping) else None
    listing = any(
        isinstance(entry, Mapping) and isinstance(entry.get("items"), list)
        for one in (steps if isinstance(steps, list) else ())
        if isinstance(one, Mapping) and isinstance(one.get("claim"), Mapping)
        for entry in (one["claim"].get("scope") if isinstance(one["claim"].get("scope"), list) else ())
    )
    return "list fewer items (`listed`)" + (", or leave the claims' lists out (`claim_lists`)" if listing else "")


def _in_hand(found_claim):
    """A claim with each of its lists as a set, so that whether an entry covers an item is
    one look-up: a list may name as many items as the chain holds."""
    if not found_claim:
        return found_claim
    return found_claim | {"scope": [
        entry | {"items": frozenset(entry["items"])} if isinstance(entry["items"], list) else entry
        for entry in found_claim["scope"]
    ]}  # fmt: skip


def _matrix(data, found) -> None:
    """A matrix holds every item with its results: only a local file of items may name one."""
    named = data.get("matrix")
    if named is None:
        return
    if not (isinstance(named, dict) and set(named) == {"file", "items"} and isinstance(named["file"], str)
            and FILE_NAME.fullmatch(named["file"]) and is_count(named["items"])):  # fmt: skip
        found.append("`matrix` is not {file, items} with a file name, or null")
        return
    if data["tier"] != "items" or data["audience"] != "local":
        found.append("only a local file of items names a matrix: a public file keeps the listed items only")
    count = data["items_count"]
    if isinstance(count, dict) and named["items"] != count.get("all"):
        found.append(f"`matrix` says {named['items']} items, the file counts {count.get('all')}")
