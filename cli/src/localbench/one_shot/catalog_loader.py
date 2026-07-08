from __future__ import annotations

import httpx

from localbench.one_shot.catalog import CatalogResolutionError


class HttpCatalogLoader:
    def load(self, *, requested_model: str, site: str) -> dict[str, object]:
        url = f"{site.rstrip('/')}/data/models/{requested_model}.json"
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            value = response.json()
        if not isinstance(value, dict):
            raise CatalogResolutionError("model catalog response must be a JSON object")
        if "models" in value:
            return {str(key): item for key, item in value.items()}
        return {"models": [value]}
