"""Synchronous Orion-LD client used by API and worker."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OrionLDClient:
    CONTEXT = [
        "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "https://smartdatamodels.org/context.jsonld",
    ]

    def __init__(self, tenant_id: Optional[str] = None):
        self.base_url = settings.ORION_URL.rstrip("/")
        self.tenant_id = tenant_id
        self.headers = {
            "Accept": "application/ld+json",
        }
        if tenant_id:
            self.headers["NGSILD-Tenant"] = tenant_id
        if settings.ORION_CONTEXT_URL:
            self.headers["Link"] = f'<{settings.ORION_CONTEXT_URL}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'

    def _request(self, method: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        
        req_headers = dict(self.headers)
        if json_data and "@context" in json_data:
            req_headers["Content-Type"] = "application/ld+json"
            if "Link" in req_headers:
                del req_headers["Link"]
        elif json_data:
            req_headers["Content-Type"] = "application/json"

        with httpx.Client(timeout=30.0) as client:
            resp = client.request(method, url, json=json_data, headers=req_headers)
        if resp.status_code not in (200, 201, 204):
            raise RuntimeError(f"Orion request failed {resp.status_code}: {resp.text}")
        if resp.content:
            return resp.json()
        return None

    @staticmethod
    def _parcel_urn(parcel_id: str) -> str:
        return parcel_id if parcel_id.startswith("urn:") else f"urn:ngsi-ld:AgriParcel:{parcel_id}"

    def create_processing_job(self, job_id: str, parcel_id: str, geometry_wkt: Optional[str], config: Dict[str, Any], user_id: str) -> str:
        entity_id = f"urn:ngsi-ld:DataProcessingJob:{job_id}"
        entity = {
            "@context": self.CONTEXT,
            "id": entity_id,
            "type": "DataProcessingJob",
            "jobType": {"type": "Property", "value": "lidar"},
            "status": {"type": "Property", "value": "queued"},
            "progress": {"type": "Property", "value": 0},
            "statusMessage": {"type": "Property", "value": "queued"},
            "requestedBy": {"type": "Property", "value": user_id},
            "refAgriParcel": {"type": "Relationship", "object": self._parcel_urn(parcel_id)},
            "parcelGeometryWKT": {"type": "Property", "value": geometry_wkt or ""},
            "config": {"type": "Property", "value": config or {}},
            "createdAt": {"type": "Property", "value": datetime.utcnow().isoformat() + "Z"},
        }
        self._request("POST", "/ngsi-ld/v1/entities", entity)
        return entity_id

    def update_job(self, entity_id: str, **updates: Any) -> None:
        payload: Dict[str, Any] = {"@context": self.CONTEXT}
        for k, v in updates.items():
            payload[k] = {"type": "Property", "value": v}
        self._request("POST", f"/ngsi-ld/v1/entities/{quote(entity_id, safe='')}/attrs", payload)

    def get_job(self, entity_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/ngsi-ld/v1/entities/{quote(entity_id, safe='')}")

    def list_jobs(self, limit: int, offset: int) -> List[Dict[str, Any]]:
        return self._request(
            "GET",
            f"/ngsi-ld/v1/entities?type=DataProcessingJob&q=jobType==lidar&limit={limit}&offset={offset}",
        ) or []

    def create_digital_asset(self, asset_id: str, parcel_id: str, tileset_url: str, source: str, point_count: int, tree_count: int) -> str:
        entity_id = f"urn:ngsi-ld:DigitalAsset:{asset_id}"
        entity = {
            "@context": self.CONTEXT,
            "id": entity_id,
            "type": "DigitalAsset",
            "assetCategory": {"type": "Property", "value": "LiDAR"},
            "resourceURL": {"type": "Property", "value": tileset_url},
            "source": {"type": "Property", "value": source},
            "pointCount": {"type": "Property", "value": point_count},
            "treeCount": {"type": "Property", "value": tree_count},
            "processingStatus": {"type": "Property", "value": "completed"},
            "dateObserved": {"type": "Property", "value": datetime.utcnow().isoformat() + "Z"},
            "refAgriParcel": {"type": "Relationship", "object": self._parcel_urn(parcel_id)},
        }
        self._request("POST", "/ngsi-ld/v1/entities", entity)
        return entity_id

    def list_assets(self, parcel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        q = "assetCategory==LiDAR"
        if parcel_id:
            q += f";refAgriParcel=={self._parcel_urn(parcel_id)}"
        return self._request("GET", f"/ngsi-ld/v1/entities?type=DigitalAsset&q={q}&limit=1000") or []

    def get_asset(self, entity_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/ngsi-ld/v1/entities/{quote(entity_id, safe='')}")

    def delete_asset(self, entity_id: str) -> None:
        self._request("DELETE", f"/ngsi-ld/v1/entities/{quote(entity_id, safe='')}")


def get_orion_client(tenant_id: Optional[str] = None) -> OrionLDClient:
    return OrionLDClient(tenant_id=tenant_id)
