#!/usr/bin/env python3
"""
Descarga el Catastro Minero Nacional (ARCOM) desde el servidor oficial
geovisorm.controlrecursosyenergia.gob.ec y genera arcom_catastro.gpkg.

Uso:
    python download_arcom.py

Requiere:
    pip install requests
    ogr2ogr (gdal)
"""

import csv
import json
import os
import subprocess
import time
from pathlib import Path

import requests


LAYER_URL = os.getenv(
    "ARCOM_LAYER_URL",
    "https://geovisorm.controlrecursosyenergia.gob.ec"
    "/arcgis/rest/services/Concesiones/CatastroMineroNacional_PSAD56/MapServer/0",
).strip()
QUERY_URL = f"{LAYER_URL}/query"

OUT_DIR = Path(os.getenv("ARCOM_OUT_DIR", str(Path(__file__).parent))).expanduser()
OUT_GEOJSON = OUT_DIR / "arcom_catastro.geojson"
OUT_GPKG = OUT_DIR / "arcom_catastro.gpkg"
OUT_CSV = OUT_DIR / "arcom_catastro_atributos.csv"
OUT_REPORT = OUT_DIR / "arcom_descarga_reporte.json"
OUT_MISSING = OUT_DIR / "arcom_ids_faltantes.txt"

LAYER_NAME = os.getenv("ARCOM_LAYER_NAME", "catastro_minero").strip() or "catastro_minero"
BATCH_SIZE = max(1, int(os.getenv("ARCOM_BATCH_SIZE", "500")))
MAX_RETRIES = max(1, int(os.getenv("ARCOM_MAX_RETRIES", "5")))
SLEEP_SECONDS = max(float(os.getenv("ARCOM_SLEEP_SECONDS", "0.4")), 0.0)
REQUEST_TIMEOUT_SEC = max(float(os.getenv("ARCOM_REQUEST_TIMEOUT_SEC", "180")), 1.0)


def request_json(session, method, url, params):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if method == "GET":
                resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
            else:
                resp = session.post(url, data=params, timeout=REQUEST_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        except Exception as exc:
            last_error = str(exc)
            print(f"  Intento {attempt}/{MAX_RETRIES} falló: {last_error}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"Consulta fallida tras {MAX_RETRIES} intentos: {last_error}")


def chunks(values, size):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def save_geojson(features):
    OUT_GEOJSON.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def save_csv(features):
    if not features:
        return
    fieldnames = sorted(
        {key for f in features for key in f.get("properties", {}).keys()}
    )
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for f in features:
            writer.writerow(f.get("properties", {}))


def create_gpkg():
    if OUT_GPKG.exists():
        OUT_GPKG.unlink()
    cmd = [
        "ogr2ogr",
        "-f", "GPKG",
        str(OUT_GPKG),
        str(OUT_GEOJSON),
        "-nln", LAYER_NAME,
        "-nlt", "PROMOTE_TO_MULTI",
        "-lco", "GEOMETRY_NAME=geom",
    ]
    print("\nGenerando GeoPackage...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("ogr2ogr falló al generar el .gpkg")
    size_mb = OUT_GPKG.stat().st_size / 1024 / 1024
    print(f"GeoPackage listo: {OUT_GPKG}  ({size_mb:.2f} MB)")


def esri_feature_to_geojson(feature, out_sr=4326):
    """Convierte una feature ArcGIS REST (anillos en PSAD56→outSR=4326) a GeoJSON."""
    attrs = feature.get("attributes", {})
    geom  = feature.get("geometry")

    if geom is None:
        geo_json = None
    elif "rings" in geom:
        rings = geom["rings"]
        if len(rings) == 1:
            geo_json = {"type": "Polygon", "coordinates": rings}
        else:
            geo_json = {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
    elif "x" in geom:
        geo_json = {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
    else:
        geo_json = None

    return {
        "type": "Feature",
        "id": attrs.get("objectid"),
        "properties": attrs,
        "geometry": geo_json,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    print("Leyendo metadatos del servicio ARCOM...")
    meta = request_json(session, "GET", LAYER_URL, {"f": "json"})
    geom_type = meta.get("geometryType")
    max_count = meta.get("maxRecordCount")
    caps      = meta.get("capabilities", "")
    fields    = [f["name"] for f in meta.get("fields", [])]
    print(f"  Tipo geometría  : {geom_type}")
    print(f"  MaxRecordCount  : {max_count}")
    print(f"  Capabilities    : {caps}")
    print(f"  Campos          : {len(fields)} → {fields}")

    print("\nContando registros en servidor...")
    count_data     = request_json(session, "POST", QUERY_URL,
                                  {"where": "1=1", "returnCountOnly": "true", "f": "json"})
    expected_count = int(count_data["count"])
    print(f"  Total esperado  : {expected_count}")

    print("\nDescargando lista de IDs...")
    ids_data   = request_json(session, "POST", QUERY_URL,
                              {"where": "1=1", "returnIdsOnly": "true", "f": "json"})
    object_ids = sorted(set(ids_data.get("objectIds", [])))
    print(f"  IDs recibidos   : {len(object_ids)}")

    features_by_id = {}
    total_batches  = (len(object_ids) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num, batch_ids in enumerate(chunks(object_ids, BATCH_SIZE), start=1):
        print(f"\nBloque {batch_num}/{total_batches}  (IDs {batch_ids[0]}–{batch_ids[-1]})")
        data = request_json(
            session, "POST", QUERY_URL,
            {
                "objectIds": ",".join(map(str, batch_ids)),
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            },
        )
        raw_features = data.get("features", [])
        print(f"  Registros bloque: {len(raw_features)}")

        for raw in raw_features:
            fid = raw.get("attributes", {}).get("objectid")
            if fid is None:
                raise RuntimeError("Feature sin objectid.")
            features_by_id[int(fid)] = esri_feature_to_geojson(raw)

        save_geojson([features_by_id[k] for k in sorted(features_by_id)])
        print(f"  Acumulado único : {len(features_by_id)}")
        time.sleep(SLEEP_SECONDS)

    all_features = [features_by_id[k] for k in sorted(features_by_id)]
    missing_ids  = sorted(set(object_ids) - set(features_by_id))

    save_geojson(all_features)
    save_csv(all_features)

    if missing_ids:
        OUT_MISSING.write_text("\n".join(map(str, missing_ids)), encoding="utf-8")
        print(f"\nATENCION: {len(missing_ids)} IDs faltantes → {OUT_MISSING}")
    elif OUT_MISSING.exists():
        OUT_MISSING.unlink()

    create_gpkg()

    report = {
        "layer_url": LAYER_URL,
        "expected_count_server": expected_count,
        "ids_received": len(object_ids),
        "downloaded_unique_features": len(all_features),
        "missing_count": len(missing_ids),
        "fields": fields,
        "geometry_type": geom_type,
        "gpkg_file": str(OUT_GPKG),
        "gpkg_size_mb": round(OUT_GPKG.stat().st_size / 1024 / 1024, 2),
        "geojson_size_mb": round(OUT_GEOJSON.stat().st_size / 1024 / 1024, 2),
    }
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 40)
    print("DESCARGA TERMINADA")
    print("=" * 40)
    print(f"Fuente           : {LAYER_URL}")
    print(f"Esperados        : {expected_count}")
    print(f"Descargados      : {len(all_features)}")
    print(f"Faltantes        : {len(missing_ids)}")
    print(f"GeoPackage       : {OUT_GPKG}")

    if len(all_features) == expected_count and not missing_ids:
        print("\nOK: descarga completa y sin faltantes.")
    else:
        print("\nADVERTENCIA: descarga incompleta, revisa el reporte.")


if __name__ == "__main__":
    main()
