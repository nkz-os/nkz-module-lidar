"""CNIG manual-download flow: downloader wall detection, pipeline, API, worker."""
import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from app.services.pnoa_downloader import (
    BASE_URL,
    ManualDownloadRequired,
    PNOADownloader,
)

POINT_WKT = "POLYGON((-2.1 42.6, -2.0 42.6, -2.0 42.7, -2.1 42.7, -2.1 42.6))"
LINK_URL = "https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=111"


@pytest.fixture
def dl():
    d = PNOADownloader()
    d._session_ready = True
    return d


def _search_resp(sec, name=None):
    html = f'<td data-sec="{sec}"></td>'
    if name:
        html = f"<td>{name}</td>" + html
    return MagicMock(status_code=200, text=html)


def _walled_post(url, **kwargs):
    if url.endswith("archivosSerie"):
        if kwargs["data"]["codSerie"] == "LIDA3":
            return _search_resp("111")  # cob3: no name given
        return _search_resp("222", "PNOA-2019-XX-H31.LAZ")
    if url.endswith("initDescargaDir"):
        r = MagicMock(status_code=200)
        r.json.return_value = {"secuencialDescDir": "TOK"}
        return r
    return MagicMock(status_code=403)  # descargaDir behind the captcha


class TestDownloaderWall:
    def test_403_raises_with_exact_links(self, dl, tmp_path):
        with patch.object(dl.session, "post", side_effect=_walled_post):
            with pytest.raises(ManualDownloadRequired) as ei:
                dl.download(POINT_WKT, str(tmp_path))
        assert ei.value.links == [
            {"series": "cob3", "sec": "111", "name": None,
             "url": f"{BASE_URL}/detalleArchivo?sec=111"},
            {"series": "cob2", "sec": "222", "name": "PNOA-2019-XX-H31.LAZ",
             "url": f"{BASE_URL}/detalleArchivo?sec=222"},
        ]

    def test_html_wall_raises(self, dl, tmp_path):
        def post(url, **kwargs):
            if url.endswith("descargaDir"):
                r = MagicMock(status_code=200)
                r.headers = {"Content-Disposition": ""}
                r.content = b"<HTML>captcha</HTML>"
                r._consumed = False
                return r
            return _walled_post(url, **kwargs)

        with patch.object(dl.session, "post", side_effect=post):
            with pytest.raises(ManualDownloadRequired):
                dl.download(POINT_WKT, str(tmp_path))

    def test_no_tiles_returns_none(self, dl, tmp_path):
        resp = MagicMock(status_code=200, text="<tbody></tbody>")
        with patch.object(dl.session, "post", return_value=resp):
            assert dl.download(POINT_WKT, str(tmp_path)) is None

    def test_tiles_but_network_error_returns_none(self, dl, tmp_path):
        import requests

        def post(url, **kwargs):
            if url.endswith("archivosSerie"):
                return _search_resp("111")
            raise requests.ConnectionError("boom")

        with patch.object(dl.session, "post", side_effect=post):
            assert dl.download(POINT_WKT, str(tmp_path)) is None


def _import_with_stubs(monkeypatch, *names):
    """Import heavy-dependency modules, stubbing native libs that are absent."""
    for lib in ("pdal", "laspy", "rasterio", "rasterio.mask", "rasterio.warp",
                "rasterio.transform", "rasterio.features"):
        try:
            importlib.import_module(lib)
        except Exception:
            monkeypatch.setitem(sys.modules, lib, MagicMock())
    # Importing the real storage service opens a MinIO connection; rq is a
    # runtime-only dependency. Neither is needed by these tests.
    monkeypatch.setitem(sys.modules, "app.services.storage", MagicMock())
    monkeypatch.delitem(sys.modules, "app.services.tile_cache", raising=False)
    try:
        importlib.import_module("rq")
    except Exception:
        monkeypatch.setitem(sys.modules, "rq", MagicMock())
    for n in list(sys.modules):
        if n == "app.main" or n.startswith("app.api") or n in names:
            monkeypatch.delitem(sys.modules, n, raising=False)
    if "app.api.lidar" in names:
        importlib.import_module("app.main")  # app.api.lidar needs app.main.limiter
    mods = [importlib.import_module(n) for n in names]
    # do not leak stub-bound modules into other tests
    for n in list(sys.modules):
        if n == "app.main" or n.startswith("app.api") or n in names:
            monkeypatch.delitem(sys.modules, n, raising=False)
    return mods


@pytest.fixture(scope="module")
def api_module():
    # Imported once: the module registers Prometheus metrics at import time.
    with pytest.MonkeyPatch.context() as mp:
        (api,) = _import_with_stubs(mp, "app.api.lidar")
    return api


class TestPipeline:
    def test_phase_a_propagates_and_skips_tile_cache(self, monkeypatch, tmp_path):
        (pl,) = _import_with_stubs(monkeypatch, "app.services.lidar_pipeline")
        pipe = pl.LidarPipeline.__new__(pl.LidarPipeline)
        pipe.work_dir = str(tmp_path)
        links = [{"series": "cob3", "sec": "p1", "name": None, "url": LINK_URL}]
        fake = MagicMock()
        fake.download.side_effect = ManualDownloadRequired(links)
        cache = MagicMock()
        monkeypatch.setattr(pl, "tile_cache", cache)
        with patch("app.services.pnoa_downloader.get_pnoa_downloader", return_value=fake):
            with pytest.raises(ManualDownloadRequired):
                pipe.phase_a_ingest("https://datos.ign.es/lidar/+42_-03/lidar.laz", POINT_WKT)
        cache.get_or_download_tile.assert_not_called()

    def test_process_records_code_and_links(self, monkeypatch):
        (pl,) = _import_with_stubs(monkeypatch, "app.services.lidar_pipeline")
        pipe = pl.LidarPipeline.__new__(pl.LidarPipeline)
        pipe.job_id = "urn:ngsi-ld:DataProcessingJob:j1"
        pipe.tenant_id = "acme"
        pipe.work_dir = None
        links = [{"series": "cob3", "sec": "p1", "name": None, "url": LINK_URL}]
        client = MagicMock()
        monkeypatch.setattr(pl, "get_orion_client", lambda t: client)
        monkeypatch.setattr(pipe, "update_job_status", lambda *a, **k: None)
        monkeypatch.setattr(pipe, "_cleanup", lambda: None)
        monkeypatch.setattr(
            pipe, "phase_a_ingest",
            MagicMock(side_effect=ManualDownloadRequired(links)),
        )
        with pytest.raises(ManualDownloadRequired):
            pipe.process("https://x/lidar.laz", POINT_WKT, {})
        kwargs = client.update_job_sync.call_args.kwargs
        assert kwargs["status"] == "failed"
        assert kwargs["statusMessage"] == "manual_download_required"
        assert kwargs["manualDownloadLinks"] == links


def _job(links_key, links):
    return {
        "status": {"value": "failed"},
        "progress": {"value": 0},
        "statusMessage": {"value": "manual_download_required"},
        links_key: {"type": "Property", "value": links},
    }


class TestApi:
    GOOD = {"series": "cob3", "sec": "p1", "name": None, "url": LINK_URL}
    BAD = {"series": "cob3", "sec": "p2", "name": "x", "url": "https://evil.example/x"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", [
        "manualDownloadLinks",
        "https://nkz-os.org/ns/manualDownloadLinks",
        "nkz:manualDownloadLinks",
    ])
    async def test_status_exposes_links_all_forms(self, monkeypatch, api_module, key):
        api = api_module
        client = MagicMock()

        async def get_job(_id):
            return _job(key, [self.GOOD, self.BAD])

        client.get_job = get_job
        monkeypatch.setattr(api, "get_orion_client", lambda t: client)
        res = await api.get_job_status("j1", current_user={}, tenant_id="acme")
        assert res.error_code == "manual_download_required"
        assert [l.sec for l in res.manual_download_links] == ["p1"]
        assert res.manual_download_links[0].url == LINK_URL

    @pytest.mark.asyncio
    async def test_plain_failure_has_no_code(self, monkeypatch, api_module):
        api = api_module
        client = MagicMock()

        async def get_job(_id):
            return {"status": {"value": "failed"}, "statusMessage": {"value": "Pipeline failed"}}

        client.get_job = get_job
        monkeypatch.setattr(api, "get_orion_client", lambda t: client)
        res = await api.get_job_status("j1", current_user={}, tenant_id="acme")
        assert res.error_code is None and res.manual_download_links is None


class TestWorker:
    def _job(self):
        j = MagicMock()
        j.id = "rq1"
        j.meta = {"job_entity_id": "urn:ngsi-ld:DataProcessingJob:j1", "tenant_id": "acme"}
        j.args = ()
        return j

    def test_sync_does_not_overwrite_manual_download(self, monkeypatch):
        from app import worker
        client = MagicMock()
        client.get_job_sync.return_value = {
            "statusMessage": {"type": "Property", "value": "manual_download_required"}}
        monkeypatch.setattr("app.services.orion_client.get_orion_client", lambda t: client)
        worker._sync_orion_failure(self._job(), "ManualDownloadRequired: x")
        client.update_job_sync.assert_not_called()

    def test_sync_still_marks_other_failures(self, monkeypatch):
        from app import worker
        client = MagicMock()
        client.get_job_sync.return_value = {
            "statusMessage": {"type": "Property", "value": "Processing"}}
        monkeypatch.setattr("app.services.orion_client.get_orion_client", lambda t: client)
        worker._sync_orion_failure(self._job(), "ValueError: x")
        assert client.update_job_sync.call_args.kwargs["statusMessage"] == "Worker failure"
