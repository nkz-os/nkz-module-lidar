"""Extract the AgriParcel reference from a normalized NGSI-LD entity.

The platform @context maps both ``hasAgriParcel`` (SDM) and ``refAgriParcel``
(legacy) to the same IRI, and Orion-LD compacts the relationship to
``refAgriParcel`` when entities are read back with the platform context.  Code
that reads a job/asset relationship must therefore check BOTH keys — reading
only ``hasAgriParcel`` returns None, which silently produced DigitalAssets with
an empty ``hasAgriParcel`` reference that the parcel-reconcile backstop then
treated as orphans and deleted (bug #1, 2026-09-02).
"""

from __future__ import annotations

_PARCEL_REF_KEYS = ("hasAgriParcel", "refAgriParcel")


def extract_parcel_ref(entity: dict) -> str:
    """Return the AgriParcel URN referenced by the entity, or "" if none."""
    for key in _PARCEL_REF_KEYS:
        rel = entity.get(key)
        if isinstance(rel, dict):
            obj = rel.get("object")
            if obj:
                return obj
        elif rel:
            return rel
    return ""
