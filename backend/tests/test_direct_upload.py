"""Direct LAZ upload: presigned POST init + complete."""
import sys
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings

PUBLIC = "https://storage.example"
MAX = 500 * 1024 * 1024
HEAD_404 = ClientError({"Error": {"Code": "404", "Message": "nf"}}, "HeadObject")


@pytest.fixture
def env(monkeypatch, api_module):
    api = api_module
    api.limiter.enabled = False
    monkeypatch.setattr(settings, "MINIO_PUBLIC_BASE_URL", PUBLIC)
    monkeypatch.setattr(settings, "MINIO_ACCESS_KEY", "ak")
    monkeypatch.setattr(settings, "MINIO_SECRET_KEY", "sk")

    storage = MagicMock()
    storage.client.head_object.return_value = {"ContentLength": 1234}
    storage.client.download_file.side_effect = lambda b, k, p: open(p, "wb").close()
    monkeypatch.setitem(sys.modules, "app.services.storage",
                        MagicMock(storage_service=storage))

    orion = MagicMock()
    orion.get_job = AsyncMock(side_effect=RuntimeError("Orion request failed 404"))
    orion.create_processing_job = AsyncMock(side_effect=lambda **kw: f"urn:ngsi-ld:DataProcessingJob:{kw['job_id']}")
    orion.update_job = AsyncMock()
    monkeypatch.setattr(api, "get_orion_client", lambda t: orion)

    queue = MagicMock()
    queue.enqueue.return_value = MagicMock(id="rq1")
    monkeypatch.setattr(api, "get_redis_queue", lambda: queue)

    inspect = MagicMock()
    monkeypatch.setattr(api, "inspect_laz_crs", inspect)

    app = FastAPI()
    app.state.limiter = api.limiter
    app.include_router(api.router, prefix="/api/lidar")
    app.dependency_overrides[api.require_auth] = lambda: {"sub": "user-1"}
    app.dependency_overrides[api.get_tenant_id] = lambda: "acme"
    client = TestClient(app)
    return types_ns(api=api, storage=storage, orion=orion, queue=queue,
                    inspect=inspect, client=client)


class types_ns:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def init(env, **over):
    body = {"parcel_id": "p1", "filename": "a.laz", "size_bytes": 1000}
    body.update(over)
    return env.client.post("/api/lidar/uploads/init", json=body)


class TestInit:
    def test_ok_returns_signed_post_on_public_host(self, env):
        r = init(env)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["expires_in"] == 900
        assert urlsplit(d["url"]).netloc == "storage.example"
        assert d["url"].startswith(PUBLIC + "/lidar-source-tiles")
        key = f"user_uploads/acme/{d['upload_id']}/upload.laz"
        assert d["fields"]["key"] == key
        assert d["fields"]["x-amz-algorithm"] == "AWS4-HMAC-SHA256"
        assert "policy" in d["fields"]

    def test_policy_has_size_range_and_exact_key(self, env):
        import base64, json
        d = init(env).json()
        policy = json.loads(base64.b64decode(d["fields"]["policy"]))
        assert ["content-length-range", 1, MAX] in policy["conditions"]
        assert {"key": d["fields"]["key"]} in policy["conditions"]

    def test_las_extension_ok_case_insensitive(self, env):
        d = init(env, filename="A.LAS").json()
        assert d["fields"]["key"].endswith("/upload.las")

    @pytest.mark.parametrize("name", ["a.txt", "a", "a.zip", ""])
    def test_bad_extension_400(self, env, name):
        assert init(env, filename=name).status_code == 400

    def test_size_limit_exact(self, env):
        assert init(env, size_bytes=MAX).status_code == 200
        r = init(env, size_bytes=MAX + 1)
        assert r.status_code == 413
        assert r.json()["detail"] == "File too large. Maximum size is 500MB."

    @pytest.mark.parametrize("size", [0, -5])
    def test_nonpositive_size_422_or_400(self, env, size):
        assert init(env, size_bytes=size).status_code in (400, 422)

    def test_503_without_public_base(self, env, monkeypatch):
        monkeypatch.setattr(settings, "MINIO_PUBLIC_BASE_URL", None)
        r = init(env)
        assert r.status_code == 503
        assert r.json()["detail"] == "direct_upload_unavailable"


def complete(env, upload_id, **over):
    body = {"parcel_id": "p1"}
    body.update(over)
    return env.client.post(f"/api/lidar/uploads/{upload_id}/complete", json=body)


class TestComplete:
    def test_bad_uuid_400(self, env):
        assert complete(env, "not-a-uuid").status_code == 400

    def test_missing_object_404(self, env):
        env.storage.client.head_object.side_effect = HEAD_404
        r = complete(env, str(uuid4()))
        assert r.status_code == 404
        assert r.json()["detail"] == "upload_not_found"
        env.queue.enqueue.assert_not_called()

    def test_too_large_deletes_and_413(self, env):
        env.storage.client.head_object.return_value = {"ContentLength": MAX + 1}
        uid = str(uuid4())
        r = complete(env, uid)
        assert r.status_code == 413
        env.storage.client.delete_object.assert_called_once_with(
            Bucket="lidar-source-tiles", Key=f"user_uploads/acme/{uid}/upload.laz")
        env.queue.enqueue.assert_not_called()

    def test_invalid_crs_422_no_enqueue_object_kept(self, env):
        from app.services.geodesy_validator import GeodesyValidationError
        env.inspect.side_effect = GeodesyValidationError("CRS missing")
        r = complete(env, str(uuid4()))
        assert r.status_code == 422
        env.queue.enqueue.assert_not_called()
        env.orion.create_processing_job.assert_not_called()
        env.storage.client.delete_object.assert_not_called()

    def test_retry_with_source_crs_passes_override(self, env):
        r = complete(env, str(uuid4()), source_crs="EPSG:25830")
        assert r.status_code == 202, r.text
        assert env.inspect.call_args.kwargs["source_crs_override"] == "EPSG:25830"

    def test_ok_enqueues_with_rebuilt_key_and_job_id(self, env):
        uid = str(uuid4())
        r = complete(env, uid, tenant_id="evil", s3_key="user_uploads/evil/x/upload.laz",
                     config={"colorize_by": "rgb"}, has_rgb=False,
                     classification_mode="native")
        assert r.status_code == 202, r.text
        assert r.json()["job_id"] == uid and r.json()["status"] == "queued"
        key = f"user_uploads/acme/{uid}/upload.laz"
        env.storage.client.head_object.assert_called_with(Bucket="lidar-source-tiles", Key=key)
        args = env.queue.enqueue.call_args.args
        assert args[0] is env.api.process_uploaded_file
        assert args[1:4] == (f"urn:ngsi-ld:DataProcessingJob:{uid}", "acme", key)
        kw = env.orion.create_processing_job.call_args.kwargs
        assert kw["job_id"] == uid and kw["parcel_id"] == "p1"
        assert kw["config"]["uploaded_file_path"] == key
        assert kw["config"]["source"] == "user_upload"
        assert kw["config"]["has_rgb"] is False
        assert kw["config"]["classification_mode"] == "native"
        assert kw["config"]["colorize_by"] == "rgb"

    def test_second_complete_409_with_job_id(self, env):
        uid = str(uuid4())
        env.orion.get_job = AsyncMock(return_value={"id": f"urn:ngsi-ld:DataProcessingJob:{uid}"})
        r = complete(env, uid)
        assert r.status_code == 409
        assert r.json()["detail"]["job_id"] == uid
        env.queue.enqueue.assert_not_called()
