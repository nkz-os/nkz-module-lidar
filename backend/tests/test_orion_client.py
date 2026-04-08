from app.services.orion_client import OrionLDClient


def test_create_processing_job_builds_expected_entity(monkeypatch):
    captured = {}

    def fake_request(self, method, endpoint, json_data=None):
        captured["method"] = method
        captured["endpoint"] = endpoint
        captured["json"] = json_data
        return None

    monkeypatch.setattr(OrionLDClient, "_request", fake_request)
    client = OrionLDClient(tenant_id="tenant-a")
    entity_id = client.create_processing_job(
        job_id="job-1",
        parcel_id="parcel-1",
        geometry_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
        config={"detect_trees": True},
        user_id="user-1",
    )

    assert entity_id == "urn:ngsi-ld:DataProcessingJob:job-1"
    assert captured["method"] == "POST"
    assert captured["endpoint"] == "/ngsi-ld/v1/entities"
    assert captured["json"]["type"] == "DataProcessingJob"
    assert captured["json"]["refAgriParcel"]["object"] == "urn:ngsi-ld:AgriParcel:parcel-1"

