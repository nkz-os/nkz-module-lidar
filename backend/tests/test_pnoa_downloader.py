"""Tests for the CNIG PNOA downloader (flow + parsing, network mocked)."""
import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.pnoa_downloader import PNOADownloader, SERIES


@pytest.fixture
def dl():
    d = PNOADownloader()
    d._session_ready = True
    return d


class TestCentroid:
    def test_centroid_from_wkt_polygon(self, dl):
        lon, lat = dl._centroid_lonlat("POLYGON((-2.1 42.6, -2.0 42.6, -2.0 42.7, -2.1 42.7, -2.1 42.6))")
        assert lon is not None and lat is not None
        assert abs(lon - (-2.05)) < 1e-6
        assert abs(lat - 42.65) < 1e-6

    def test_empty_wkt_returns_none(self, dl):
        assert dl._centroid_lonlat("") == (None, None)


class TestSearchTiles:
    HTML = (
        '<tr><td>PNOA-2021-CAT-374-4596-H31-NPC02.LAZ</td>'
        '<td data-sec="12993309"></td></tr>'
    )

    def test_parses_sec_and_name(self, dl):
        resp = MagicMock(status_code=200, text=self.HTML)
        with patch.object(dl.session, "post", return_value=resp) as m:
            tiles = dl._search_tiles(1.5, 41.5, "LIDA3")
        assert tiles == [("12993309", "PNOA-2021-CAT-374-4596-H31-NPC02.LAZ")]
        # coordenadas must be a GeoJSON Point FeatureCollection
        data = m.call_args.kwargs["data"]
        assert data["codSerie"] == "LIDA3"
        assert '"Point"' in data["coordenadas"]
        assert "1.5" in data["coordenadas"]

    def test_empty_result(self, dl):
        resp = MagicMock(status_code=200, text="<tbody></tbody>")
        with patch.object(dl.session, "post", return_value=resp):
            assert dl._search_tiles(0.0, 0.0, "LIDA3") == []

    def test_http_error_returns_empty(self, dl):
        resp = MagicMock(status_code=403, text="forbidden")
        with patch.object(dl.session, "post", return_value=resp):
            assert dl._search_tiles(0.0, 0.0, "LIDA3") == []


class TestDownloadSec:
    def test_download_two_step_flow(self, dl, tmp_path):
        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"secuencialDescDir": "TOK1", "muestraLic": "NO"}
        file_resp = MagicMock(status_code=200)
        file_resp.headers = {"Content-Disposition": "attachment; filename=PNOA_1.LAZ"}
        file_resp.iter_content.return_value = iter([b"LASF" + b"\x00" * 500])

        with patch.object(dl.session, "post", side_effect=[token_resp, file_resp]) as m:
            path = dl._download_sec("123", "PNOA_1.LAZ", str(tmp_path))

        assert path is not None and os.path.exists(path)
        assert os.path.getsize(path) > 0
        # first POST = initDescargaDir, second = descargaDir
        assert m.call_args_list[0].kwargs["data"] == {"secuencial": "123"}
        assert m.call_args_list[1].kwargs["data"] == {"secDescDirLA": "TOK1"}

    def test_html_response_rejected(self, dl, tmp_path):
        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"secuencialDescDir": "TOK1"}
        file_resp = MagicMock(status_code=200)
        file_resp.headers = {"Content-Disposition": ""}
        file_resp.content = b"<html>error</html>"
        file_resp._consumed = True

        with patch.object(dl.session, "post", side_effect=[token_resp, file_resp]):
            assert dl._download_sec("123", "x.laz", str(tmp_path)) is None


class TestSeriesConfig:
    def test_lida3_first_with_attribution(self):
        assert SERIES[0][0] == "LIDA3"
        assert "cob3" in SERIES[0][1]
        assert "CC-BY 4.0" in SERIES[0][2]
