from __future__ import annotations

import sqlite3
import struct
from pathlib import Path
from typing import Any


class ArcomLookupError(RuntimeError):
    """Raised when the local ARCOM dataset is unavailable or invalid."""


class ArcomConcessionStore:
    def __init__(self, gpkg_path: str | Path):
        self.gpkg_path = Path(gpkg_path)

    def get_concession_for_point(self, *, lat: float, lon: float) -> dict[str, Any] | None:
        query = """
            SELECT
                c.fid,
                c.nam,
                c.com,
                c.eac,
                c.ttm,
                c.frm,
                c.tipo_mineral,
                c.rgm,
                c.ach,
                c.dpa_despro,
                c.dpa_descan,
                c.dpa_despar,
                c.geom
            FROM rtree_catastro_minero_geom AS r
            JOIN catastro_minero AS c
              ON c.fid = r.id
            WHERE r.minx <= ?
              AND r.maxx >= ?
              AND r.miny <= ?
              AND r.maxy >= ?
            ORDER BY CASE WHEN c.ach IS NULL THEN 1 ELSE 0 END, c.ach ASC, c.fid ASC
            LIMIT 64
        """
        rows = self._query_rows(query, (lon, lon, lat, lat))
        for row in rows:
            geometry = _decode_gpkg_geometry(row["geom"])
            if _point_in_geometry(lon, lat, geometry):
                return _serialize_concession(row, geometry=None)
        return None

    def get_concessions_for_bbox(
        self,
        *,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        limit: int = 120,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 250))
        query = """
            SELECT
                c.fid,
                c.nam,
                c.com,
                c.eac,
                c.ttm,
                c.frm,
                c.tipo_mineral,
                c.rgm,
                c.ach,
                c.dpa_despro,
                c.dpa_descan,
                c.dpa_despar,
                c.geom
            FROM rtree_catastro_minero_geom AS r
            JOIN catastro_minero AS c
              ON c.fid = r.id
            WHERE r.minx <= ?
              AND r.maxx >= ?
              AND r.miny <= ?
              AND r.maxy >= ?
            ORDER BY c.fid ASC
            LIMIT ?
        """
        rows = self._query_rows(query, (max_lon, min_lon, max_lat, min_lat, safe_limit))
        features = []
        for row in rows:
            geometry = _decode_gpkg_geometry(row["geom"])
            features.append(
                {
                    "type": "Feature",
                    "id": row["fid"],
                    "properties": _serialize_concession(row, geometry=None),
                    "geometry": geometry,
                }
            )

        return {
            "type": "FeatureCollection",
            "features": features,
            "meta": {
                "limit": safe_limit,
                "returned": len(features),
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "source": str(self.gpkg_path),
            },
        }

    def _query_rows(self, query: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        if not self.gpkg_path.exists():
            raise ArcomLookupError(f"ARCOM GeoPackage no encontrado: {self.gpkg_path}")

        try:
            connection = sqlite3.connect(str(self.gpkg_path))
            connection.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise ArcomLookupError(f"No se pudo abrir el GeoPackage ARCOM: {exc}") from exc

        try:
            cursor = connection.execute(query, params)
            return cursor.fetchall()
        except sqlite3.Error as exc:
            raise ArcomLookupError(f"No se pudo consultar el GeoPackage ARCOM: {exc}") from exc
        finally:
            connection.close()


def _serialize_concession(row: sqlite3.Row, geometry: dict[str, Any] | None) -> dict[str, Any]:
    payload = {
        "fid": row["fid"],
        "codigo_catastral": row["nam"],
        "nombre_concesion": row["com"],
        "estado_actual": row["eac"],
        "empresa": (row["ttm"] or "").strip() or None,
        "fase_recurso_mineral": row["frm"],
        "tipo_mineral": row["tipo_mineral"],
        "regimen": row["rgm"],
        "superficie_ha": row["ach"],
        "provincia": row["dpa_despro"],
        "canton": row["dpa_descan"],
        "parroquia": row["dpa_despar"],
    }
    if geometry is not None:
        payload["geometry"] = geometry
    return payload


def _decode_gpkg_geometry(blob: bytes | memoryview | bytearray | None) -> dict[str, Any]:
    raw = bytes(blob or b"")
    if len(raw) < 8 or raw[:2] != b"GP":
        raise ArcomLookupError("Geometría GeoPackage inválida.")

    flags = raw[3]
    envelope_code = (flags >> 1) & 0b111
    envelope_size = {
        0: 0,
        1: 32,
        2: 48,
        3: 48,
        4: 64,
    }.get(envelope_code, 0)
    wkb = raw[8 + envelope_size :]
    geometry, offset = _parse_wkb_geometry(wkb, 0)
    if offset > len(wkb):
        raise ArcomLookupError("No se pudo interpretar la geometría WKB.")
    return geometry


def _parse_wkb_geometry(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    if offset + 5 > len(data):
        raise ArcomLookupError("WKB incompleto.")

    byte_order = data[offset]
    endian = "<" if byte_order == 1 else ">"
    geom_type = struct.unpack_from(f"{endian}I", data, offset + 1)[0]
    base_type = geom_type % 1000
    cursor = offset + 5

    if base_type == 3:
        return _parse_wkb_polygon(data, cursor, endian)
    if base_type == 6:
        return _parse_wkb_multipolygon(data, cursor, endian)

    raise ArcomLookupError(f"Tipo geométrico WKB no soportado: {geom_type}")


def _parse_wkb_polygon(data: bytes, offset: int, endian: str) -> tuple[dict[str, Any], int]:
    if offset + 4 > len(data):
        raise ArcomLookupError("WKB polígono incompleto.")
    ring_count = struct.unpack_from(f"{endian}I", data, offset)[0]
    cursor = offset + 4
    rings: list[list[list[float]]] = []

    for _ in range(ring_count):
        if cursor + 4 > len(data):
            raise ArcomLookupError("Anillo WKB incompleto.")
        point_count = struct.unpack_from(f"{endian}I", data, cursor)[0]
        cursor += 4
        ring: list[list[float]] = []
        for _ in range(point_count):
            if cursor + 16 > len(data):
                raise ArcomLookupError("Coordenada WKB incompleta.")
            x, y = struct.unpack_from(f"{endian}dd", data, cursor)
            cursor += 16
            ring.append([x, y])
        rings.append(ring)

    return {"type": "Polygon", "coordinates": rings}, cursor


def _parse_wkb_multipolygon(data: bytes, offset: int, endian: str) -> tuple[dict[str, Any], int]:
    if offset + 4 > len(data):
        raise ArcomLookupError("WKB multipolígono incompleto.")
    polygon_count = struct.unpack_from(f"{endian}I", data, offset)[0]
    cursor = offset + 4
    polygons: list[list[list[list[float]]]] = []

    for _ in range(polygon_count):
        polygon, cursor = _parse_wkb_geometry(data, cursor)
        if polygon.get("type") != "Polygon":
            raise ArcomLookupError("Multipolígono con geometría hija inválida.")
        polygons.append(polygon["coordinates"])

    return {"type": "MultiPolygon", "coordinates": polygons}, cursor


def _point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    geom_type = str(geometry.get("type") or "").strip()
    coordinates = geometry.get("coordinates")

    if geom_type == "Polygon":
        return _point_in_polygon(lon, lat, coordinates)
    if geom_type == "MultiPolygon":
        return any(_point_in_polygon(lon, lat, polygon) for polygon in (coordinates or []))
    return False


def _point_in_polygon(lon: float, lat: float, rings: list[list[list[float]]] | None) -> bool:
    if not rings:
        return False
    outer_ring = rings[0]
    if not _point_in_ring(lon, lat, outer_ring):
        return False
    for hole in rings[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _point_in_ring(lon: float, lat: float, ring: list[list[float]] | None) -> bool:
    if not ring or len(ring) < 3:
        return False

    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside
