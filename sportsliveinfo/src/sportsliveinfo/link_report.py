"""Diagnostics for broadcast links: the binds dry run and the link-coverage (gap reason) histogram.

Both read events that already carry ``broadcast_candidates`` / ``broadcast_gap`` (the materialised ``sports`` snapshot
or the events of a feed build). They count and list ids only: no programme text, no guide names, no times. The
binds dry run shows what switching ``binds_rule`` from "legacy" to "narrow" does *before* it is on (and keeps showing
it afterwards, so a regression is visible in the health asset).
"""
from collections import Counter

from . import linking

DEMOTED_LIST_LIMIT = 40


def _candidates(event, private):
    if not private and event.get("broadcast_status") == "guide_listing_match":
        return []            # the public feed never carries these links (feed._broadcast_links)
    return [c for c in linking.rank_candidates(event.get("broadcast_candidates") or [], event)
            if c.get("canonical_channel_id")]


def _reason(event, candidate):
    if not linking.is_curated_candidate(candidate):
        return "not_curated_channel"
    return "foreign_market"


def dry_run_binds(events, *, private=True, titles=False, own_epg=True):
    """Compare ``binds`` under the legacy and the narrow rule for every link of ``events``.

    Returns plain data: totals, binds counts under each rule, true->false (demoted) and false->true counts, the
    demoted count per channel market, and a capped list of demoted links."""
    totals = Counter()
    demoted_by_market, reasons, demoted = Counter(), Counter(), []
    events_with_binding = {"legacy": 0, "narrow": 0}
    for event in events:
        had = {"legacy": False, "narrow": False}
        for candidate in _candidates(event, private):
            corroborated = linking.guide_corroborated(event, candidate, own_epg)
            legacy = linking.link_binds(event, candidate, corroborated, "legacy")
            narrow = linking.link_binds(event, candidate, corroborated, "narrow")
            totals["links"] += 1
            totals["binds_legacy"] += legacy
            totals["binds_narrow"] += narrow
            had["legacy"] |= legacy
            had["narrow"] |= narrow
            if legacy and not narrow:
                market = linking.channel_market(candidate["canonical_channel_id"]) or "unknown"
                demoted_by_market[market] += 1
                reasons[_reason(event, candidate)] += 1
                if len(demoted) < DEMOTED_LIST_LIMIT:
                    row = {"event_id": str(event.get("id")), "channel": str(candidate["canonical_channel_id"]),
                           "market": market, "confidence": "high", "guides": len(candidate.get("epg_sources") or []),
                           "reason": _reason(event, candidate)}
                    if titles:
                        row["title"] = str(event.get("title") or "")[:120]
                    demoted.append(row)
            elif narrow and not legacy:
                totals["false_to_true"] += 1
        for rule in had:
            events_with_binding[rule] += had[rule]
        totals["events"] += 1
    true_to_false = sum(demoted_by_market.values())
    return {"from": "legacy", "to": "narrow", "events": totals["events"], "links": totals["links"],
            "binds_legacy": totals["binds_legacy"], "binds_narrow": totals["binds_narrow"],
            "true_to_false": true_to_false, "false_to_true": totals["false_to_true"],
            "true_to_false_by_market": dict(sorted(demoted_by_market.items())),
            "true_to_false_by_reason": dict(sorted(reasons.items())),
            "events_with_binding": events_with_binding,
            "demoted": demoted, "demoted_truncated": true_to_false > len(demoted)}


def _row(events, private):
    counts = Counter()
    for event in events:
        counts["events"] += 1
        candidates = _candidates(event, private)
        if candidates:
            counts["linked"] += 1
            counts["corroborated"] += any(linking.guide_corroborated(event, c) for c in candidates)
        else:
            counts["gap:" + str(event.get("broadcast_gap") or "unknown")] += 1
    out = {"events": counts["events"], "linked": counts["linked"], "corroborated": counts["corroborated"],
           "gaps": {key[4:]: n for key, n in sorted(counts.items()) if key.startswith("gap:")}}
    return out


def link_coverage(events, *, private=True, tier_of=None):
    """Gap-reason histogram: how many events are linked, how many are not and why (``broadcast_gap``), overall and
    per tier. ``unknown`` means the event carries no gap reason (no guide pass recorded it)."""
    tier_of = tier_of or (lambda event: event.get("tier") or "core")
    events = [e for e in events if e.get("origin") != "guide_listing"]
    report = _row(events, private)
    report["by_tier"] = {tier: _row([e for e in events if tier_of(e) == tier], private)
                         for tier in ("core", "extra")}
    return report
