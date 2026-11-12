"""Conservative EPG enrichment proposals; never overwrite a B1G provider EPG.

SportsLiveInfo cannot know an IPTV account's actual channel, hidden-category
choices or a user's manual EPG mapping. This module only evaluates programme
evidence and returns a suggested DISPLAY overlay. B1G makes the final
account-scoped choice locally. No EPG programme text is public by default.
"""
from datetime import datetime, timedelta, timezone
import re

GENERIC = re.compile(
    r"^(?:live (?:football|sport|sports|rugby|cricket|tennis|boxing)|"
    r"sporting event|live event|to be announced|tba|no information|"
    r"programme information|sans titre|a definir|à définir)$", re.I,
)


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("Missing programme time")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Missing timezone")
    return stamp.astimezone(timezone.utc)


def suggest_programme_enrichment(provider_programme, candidate_programme, event, *,
                                 expected_channel, territory,
                                 user_override=False, hidden=False):
    """Suggest a more informative title only if independent evidence is strong.

    Never mutates input dictionaries. Returned overlays are not approved for
    third-party public republication merely by passing this validator.
    """
    if user_override or hidden or not all(isinstance(row, dict) for row in
                                          (provider_programme, candidate_programme, event)):
        return None
    original = str(provider_programme.get("title") or "").strip()
    replacement = str(candidate_programme.get("title") or "").strip()
    if not GENERIC.fullmatch(original) or not replacement or GENERIC.fullmatch(replacement):
        return None
    if event.get("transmission") in ("highlights", "replay", "delayed"):
        return None
    if not event.get("broadcast_verified") or event.get("broadcast_verification_rule") != "approved_v1":
        return None
    if not re.fullmatch(r"[A-Z]{2}", territory or "") or not expected_channel:
        return None
    if provider_programme.get("canonical_channel_id") != expected_channel:
        return None
    if candidate_programme.get("canonical_channel_id") != expected_channel:
        return None
    proof = any(
        isinstance(row, dict)
        and row.get("canonical_channel_id") == expected_channel
        and row.get("territory") == territory
        and row.get("transmission") == "live"
        and row.get("evidence") == "verified_programme"
        for row in event.get("broadcasts", [])
    )
    if not proof:
        return None
    if candidate_programme.get("canonical_event_id") != event.get("id"):
        return None
    try:
        a, b = _utc(provider_programme["start_utc"]), _utc(provider_programme["end_utc"])
        c, d = _utc(candidate_programme["start_utc"]), _utc(candidate_programme["end_utc"])
        start = _utc(event["start_utc"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if b <= a or d <= c or min(b, d) - max(a, c) < timedelta(minutes=20):
        return None
    if not (a - timedelta(minutes=10) <= start <= b + timedelta(minutes=10)):
        return None
    if not (c - timedelta(minutes=10) <= start <= d + timedelta(minutes=10)):
        return None
    return {
        "status": "suggestion_only",
        "canonical_event_id": event["id"],
        "canonical_channel_id": expected_channel,
        "territory": territory,
        "display_title": replacement[:240],
        "original_title": original[:240],
        "source_id": candidate_programme.get("source_id"),
        "reason": "Verified same-event/live-broadcast evidence on a compatible channel and interval",
    }
