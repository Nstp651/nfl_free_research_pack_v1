"""NFL Receptions V5.1.1 downstream player-first selection reference.

No network calls, P_model computation, tracker writes, or market discovery.
Inputs are an INTERNAL normalized contract, not an unmodified Worker response.
An adapter must validate exact freeze/evidence binding, quote provenance, freshness,
and complete board coverage before calling select().
"""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING, InvalidOperation

POLICY = "NFL_RECEPTIONS_PLAYER_FIRST_1.1"
CLASSES = {
    "ELITE TARGET EARNER",
    "PRIMARY TARGET EARNER",
    "SECONDARY HIGH-VOLUME TARGET",
    "ROLE-SPECIFIC TARGET EARNER",
}


def D(x):
    if isinstance(x, bool):
        raise ValueError("boolean numeric input")
    v = Decimal(str(x))
    if not v.is_finite():
        raise ValueError("nonfinite input")
    return v


def eligible(player):
    required = (
        "position", "include", "receiver_class", "role", "pathway_usable",
        "evidence_score", "availability_score", "role_score", "confidence",
        "fragility", "evidence_ids",
    )
    if any(k not in player for k in required):
        return False
    return (
        player["position"] in {"WR", "TE", "RB"}
        and player["include"] == "INCLUDE"
        and player["receiver_class"] in CLASSES
        and player["role"] in {"STABLE", "VERIFIED_EXPANSION"}
        and player["pathway_usable"] is True
        and bool(player["evidence_ids"])
        and D(player["evidence_score"]) >= 11
        and D(player["evidence_score"]) <= 16
        and D(player["availability_score"]) == 2
        and D(player["role_score"]) == 2
        and player["confidence"] in {"HIGH", "MEDIUM"}
        and player["fragility"] in {"LOW", "MODERATE"}
    )


def threshold_fragility(row, player):
    return row.get("threshold_fragility") or player["fragility"]


def metrics(row):
    p, odds = D(row["p"]), D(row["odds"])
    return p, p - (Decimal(1) / odds), p * odds - Decimal(1)


def edge_band(edge):
    edge = D(edge)
    if edge >= D(".07"):
        return "PREMIUM"
    if edge >= D(".04"):
        return "STRONG"
    if edge >= D(".02"):
        return "PLAYABLE"
    if edge > 0:
        return "THIN"
    return "NONPOSITIVE"


def core_path(row, player):
    """Return the qualifying CORE path, or None.

    STANDARD_CORE: normal actionable reception line, p>=30%.
    SUPPORTED_LOWER_HIT: 20-30% line allowed only with stronger value and
    top reliability. This is deliberately not a tail exception: p<20% can
    never select the player.
    """
    if not eligible(player):
        return None
    p, edge, roi = metrics(row)
    frag = threshold_fragility(row, player)
    if frag not in {"LOW", "MODERATE"}:
        return None

    if p >= D(".30") and edge >= D(".02") and roi >= D(".05"):
        return "STANDARD_CORE"

    if (
        D(".20") <= p < D(".30")
        and edge >= D(".03")
        and roi >= D(".10")
        and player["confidence"] == "HIGH"
        and player["fragility"] == "LOW"
        and row.get("threshold_fragility") == "LOW"
    ):
        return "SUPPORTED_LOWER_HIT"

    return None


def rung_tier(row, player):
    """Classify an optional higher rung independently of other higher rungs."""
    if not eligible(player):
        return None
    p, edge, roi = metrics(row)
    tfrag = row.get("threshold_fragility")
    if tfrag not in {"LOW", "MODERATE"}:
        return None

    if p >= D(".20") and edge >= D(".02") and roi >= D(".05"):
        return "LADDER"

    if (
        D(".12") <= p < D(".20")
        and edge >= D(".03")
        and roi >= D(".10")
        and player["confidence"] == "HIGH"
        and player["fragility"] == "LOW"
        and tfrag == "LOW"
    ):
        return "STRETCH"

    return None


def passes(row, player, tier):
    """Compatibility helper for tests/adapters."""
    if tier == "CORE":
        return core_path(row, player) is not None
    return rung_tier(row, player) == tier


def _band_rank(edge):
    return {"PREMIUM": 0, "STRONG": 1, "PLAYABLE": 2, "THIN": 3, "NONPOSITIVE": 4}[edge_band(edge)]


def _frag_rank(value):
    return {"LOW": 0, "MODERATE": 1, "HIGH": 2}.get(value, 3)


def _conf_rank(value):
    return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(value, 3)


def core_order(row, players):
    player = players[row["player_id"]]
    p, edge, roi = metrics(row)
    path = core_path(row, player)
    path_rank = 0 if path == "STANDARD_CORE" else 1
    return (
        _band_rank(edge),
        path_rank,
        -edge,
        -p,
        _frag_rank(threshold_fragility(row, player)),
        _conf_rank(player["confidence"]),
        -roi,
        -D(row["quote_time"]),
        row["k"],
        row["book"],
        row["player_id"],
    )


def rung_order(row, players):
    player = players[row["player_id"]]
    p, edge, roi = metrics(row)
    return (
        _band_rank(edge),
        -edge,
        -p,
        _frag_rank(threshold_fragility(row, player)),
        _conf_rank(player["confidence"]),
        -roi,
        -D(row["quote_time"]),
        row["k"],
        row["book"],
        row["player_id"],
    )


def requirements(p, tier):
    p = D(p)
    if tier == "CORE":
        if p >= D(".30"):
            return D(".02"), D(".05")
        if p >= D(".20"):
            return D(".03"), D(".10")
        return None
    if tier == "LADDER":
        return (D(".02"), D(".05")) if p >= D(".20") else None
    if tier == "STRETCH":
        return (D(".03"), D(".10")) if p >= D(".12") else None
    raise ValueError("unknown tier")


def minimum_price(p, tier):
    p = D(p)
    req = requirements(p, tier)
    if req is None:
        return None
    min_edge, min_roi = req
    if p <= min_edge:
        return None
    raw = max(Decimal(1) / (p - min_edge), (Decimal(1) + min_roi) / p)
    return str(raw.quantize(Decimal(".01"), rounding=ROUND_CEILING))


def select(data):
    """Execute V5.1.1 on a normalized complete post-freeze board.

    players: ID-keyed pre-market eligibility records.
    rows: exact quotes with player_id,k,p,odds,book,quote_time,market,verified;
          optional threshold_fragility.
    wrapper: integrity_verified=True, complete_board=True, frozen=True,
             research_permission=True, run_id, freeze_receipt, now.
    """
    data = deepcopy(data)
    if (
        any(data.get(k) is not True for k in ("integrity_verified", "complete_board", "frozen"))
        or not data.get("run_id")
        or not data.get("freeze_receipt")
    ):
        raise ValueError("SELECTION INPUT INCOMPLETE")

    players = data["players"]
    now = D(data["now"])
    quotes = {}
    excluded = []
    canonical = {}

    for n, row in enumerate(data["rows"]):
        try:
            pid = row["player_id"]
            k = row["k"]
            p = D(row["p"])
            odds = D(row["odds"])
            qt = D(row["quote_time"])
            if (
                pid not in players
                or isinstance(k, bool)
                or not isinstance(k, int)
                or k < 1
                or not D("0") <= p <= D("1")
                or odds <= 1
                or not row.get("book")
                or row.get("verified") is not True
                or row.get("market") not in {"standard", "alternate"}
            ):
                raise ValueError("INVALID IDENTITY / MARKET / VALUE")

            key = (pid, k)
            if key in canonical and canonical[key] != p:
                raise RuntimeError("FROZEN PROBABILITY CONFLICT")
            canonical[key] = p

            age = now - qt
            if age < 0 or age > 1800:
                raise ValueError("PRICE NOT CURRENT")

            quote_rank = (-odds, -qt, 0 if row["market"] == "standard" else 1, row["book"])
            if key not in quotes or quote_rank < quotes[key][0]:
                quotes[key] = (quote_rank, row)
        except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
            excluded.append({"row_index": n, "reason": str(exc)})

    # Artifact conflicts are hard failures, not low-ranked rows.
    for pid in players:
        ladder = sorted((k, p) for (i, k), p in canonical.items() if i == pid)
        if any(ladder[j][1] < ladder[j + 1][1] for j in range(len(ladder) - 1)):
            raise RuntimeError("FROZEN LADDER INVERSION")

    rows = [v[1] for v in quotes.values()]
    dominated = {
        (r["player_id"], r["k"])
        for r in rows
        if any(
            q["player_id"] == r["player_id"]
            and q["k"] < r["k"]
            and D(q["odds"]) >= D(r["odds"])
            for q in rows
        )
    }

    def usable(row):
        return (row["player_id"], row["k"]) not in dominated

    anchors = {}
    if data.get("research_permission") is True:
        for row in rows:
            pid = row["player_id"]
            if usable(row) and core_path(row, players[pid]) is not None:
                if pid not in anchors or core_order(row, players) < core_order(anchors[pid], players):
                    anchors[pid] = row

    ranked = sorted(anchors.values(), key=lambda r: core_order(r, players))
    result = {
        "policy": POLICY,
        "run_id": data["run_id"],
        "freeze_receipt": data["freeze_receipt"],
        "decision": "NO BET",
        "selected_player": None,
        "recommendations": [],
        "anchors": ranked,
        "excluded": excluded,
        "dominated": sorted(dominated),
        "ladder": [],
    }
    if not ranked:
        return result

    core = ranked[0]
    pid = core["player_id"]
    player = players[pid]
    ladder = sorted((r for r in rows if r["player_id"] == pid), key=lambda r: r["k"])

    recommendations = [
        dict(
            core,
            tier="CORE",
            core_path=core_path(core, player),
            edge_band=edge_band(metrics(core)[1]),
            minimum_price=minimum_price(core["p"], "CORE"),
        )
    ]

    higher = [r for r in ladder if usable(r) and r["k"] > core["k"]]
    ladder_candidates = sorted(
        (r for r in higher if rung_tier(r, player) == "LADDER"),
        key=lambda r: rung_order(r, players),
    )
    stretch_candidates = sorted(
        (r for r in higher if rung_tier(r, player) == "STRETCH"),
        key=lambda r: rung_order(r, players),
    )

    # Independent rung evaluation: a stretch does not require an intermediate ladder rung.
    if ladder_candidates:
        r = ladder_candidates[0]
        recommendations.append(
            dict(r, tier="LADDER", edge_band=edge_band(metrics(r)[1]), minimum_price=minimum_price(r["p"], "LADDER"))
        )
    if stretch_candidates:
        r = stretch_candidates[0]
        recommendations.append(
            dict(r, tier="STRETCH", edge_band=edge_band(metrics(r)[1]), minimum_price=minimum_price(r["p"], "STRETCH"))
        )

    result.update(
        decision="BET",
        selected_player=pid,
        ladder=ladder,
        recommendations=recommendations,
    )
    return result
