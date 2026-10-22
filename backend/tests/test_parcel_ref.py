"""Tests for parcel reference extraction (handles hasAgriParcel + refAgriParcel)."""
from app.services.parcel_ref import extract_parcel_ref


def test_reads_sdm_hasagriparcel():
    e = {"hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:p1"}}
    assert extract_parcel_ref(e) == "urn:ngsi-ld:AgriParcel:p1"


def test_reads_legacy_refagriparcel():
    """Orion compacts hasAgriParcel to refAgriParcel under the platform context."""
    e = {"refAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:p1"}}
    assert extract_parcel_ref(e) == "urn:ngsi-ld:AgriParcel:p1"


def test_hasagriparcel_preferred_when_both():
    e = {
        "hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:a"},
        "refAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:b"},
    }
    assert extract_parcel_ref(e) == "urn:ngsi-ld:AgriParcel:a"


def test_string_value_accepted():
    assert extract_parcel_ref({"refAgriParcel": "urn:ngsi-ld:AgriParcel:p1"}) == "urn:ngsi-ld:AgriParcel:p1"


def test_missing_returns_empty():
    assert extract_parcel_ref({"id": "x"}) == ""
    assert extract_parcel_ref({}) == ""


def test_object_without_object_field():
    assert extract_parcel_ref({"hasAgriParcel": {"type": "Relationship"}}) == ""
