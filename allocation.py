"""Smart resource allocation: priority scoring + stock-limited distribution.

Priority score (0-100) = 45% request urgency + 30% location severity
                         + 25% people affected (relative to the largest request in the batch).
Within each resource, requests are served in score order until stock runs out.
"""
LEVEL = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def priority_score(urgency, severity, people, max_people):
    u = LEVEL.get(urgency, 2) / 4
    s = LEVEL.get(severity, 2) / 4
    p = people / max_people if max_people else 0
    return round(100 * (0.45 * u + 0.30 * s + 0.25 * p), 1)


def allocate(requests, stock, blocked=()):
    """requests: list of dicts (id, resource_id, resource_name, location_id, quantity,
    people_affected, urgency, severity). stock: {resource_id: available units}.
    blocked: location ids that cannot be reached. Returns (results, remaining_stock)."""
    max_people = max((r["people_affected"] for r in requests), default=0)
    scored = [{**r, "score": priority_score(r["urgency"], r["severity"], r["people_affected"], max_people)}
              for r in requests]
    scored.sort(key=lambda r: (-r["score"], r["id"]))

    remaining, ranks, results = dict(stock), {}, []
    for r in scored:
        rid = r["resource_id"]
        ranks[rid] = ranks.get(rid, 0) + 1
        left = remaining.get(rid, 0)
        head = f"Priority {r['score']}, rank {ranks[rid]} for {r['resource_name']}."
        if r["location_id"] in blocked:
            give, why = 0, f"{head} The route to this location is blocked, so nothing can be dispatched."
        else:
            give = min(r["quantity"], left)
            remaining[rid] = left - give
            if give == r["quantity"]:
                why = f"{head} Fully met."
            elif give > 0:
                why = f"{head} Only {give} of {r['quantity']} remained after higher-priority requests."
            else:
                why = f"{head} Stock ran out before this request's turn."
        results.append({**r, "rank": ranks[rid], "allocated": give,
                        "unmet": r["quantity"] - give, "reason": why})
    return results, remaining
