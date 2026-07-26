import json
import os
from fastapi.testclient import TestClient
from helios_api.main import app

client = TestClient(app)

OUT_DIR = "apps/web/public/api"

def save_json(path: str, data: dict):
    filepath = os.path.join(OUT_DIR, path)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def main():
    print("Exporting static API responses...")
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. Sites List
    print("Exporting /sites...")
    res = client.get("/sites")
    res.raise_for_status()
    sites_data = res.json()
    save_json("sites.json", sites_data)

    # 2. Site Details and Timelines
    for site in sites_data["items"]:
        site_id = site["id"]
        print(f"Exporting site {site_id}...")
        
        detail_res = client.get(f"/sites/{site_id}")
        detail_res.raise_for_status()
        save_json(f"sites/{site_id}.json", detail_res.json())

        timeline_res = client.get(f"/sites/{site_id}/timeline")
        timeline_res.raise_for_status()
        save_json(f"sites/{site_id}/timeline.json", timeline_res.json())

    # 3. Sources
    print("Exporting /sources...")
    sources_res = client.get("/sources")
    sources_res.raise_for_status()
    save_json("sources.json", sources_res.json())

    # 4. Analytics
    print("Exporting /analytics...")
    stages_res = client.get("/analytics/stages")
    stages_res.raise_for_status()
    save_json("analytics/stages.json", stages_res.json())

    prov_res = client.get("/analytics/provenance")
    prov_res.raise_for_status()
    save_json("analytics/provenance.json", prov_res.json())

    # 5. Map Data
    print("Exporting /map...")
    map_sites_res = client.get("/map/sites")
    map_sites_res.raise_for_status()
    save_json("map/sites.json", map_sites_res.json())

    map_infra_res = client.get("/map/infrastructure")
    map_infra_res.raise_for_status()
    save_json("map/infrastructure.json", map_infra_res.json())

    map_parcels_res = client.get("/map/parcels")
    map_parcels_res.raise_for_status()
    save_json("map/parcels.json", map_parcels_res.json())

    print("Done!")

if __name__ == "__main__":
    main()
