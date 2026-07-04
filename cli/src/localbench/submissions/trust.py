from __future__ import annotations

from localbench._types import JsonObject


def offline_trust_state() -> JsonObject:
    return {
        "trust_label": "community_re_scored",
        "publishable": False,
        "publishable_reasons": ["offline_ticket_not_account_bound"],
    }
