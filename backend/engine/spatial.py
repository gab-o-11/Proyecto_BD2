"""Puntos 2D y distancias; Haversine usa latitud/longitud en grados y devuelve metros."""

import math

EARTH_RADIUS_METERS = 6_371_000.0


def point(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("POINT requiere dos coordenadas numéricas")
    try:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
            raise ValueError
        coordinates = tuple(float(v) for v in value)
        if not all(math.isfinite(v) for v in coordinates):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("POINT requiere dos coordenadas numéricas finitas")
    return coordinates


def distance(left, right, metric="haversine"):
    left, right = point(left), point(right)
    if metric == "euclidean":
        result = math.hypot(left[0] - right[0], left[1] - right[1])
        if not math.isfinite(result):
            raise ValueError("la distancia Euclidiana excede el rango numérico")
        return result
    if metric != "haversine":
        raise ValueError(f"métrica desconocida '{metric}'")
    if any(not (-90 <= lat <= 90 and -180 <= lon <= 180) for lat, lon in (left, right)):
        raise ValueError("Haversine requiere latitud entre -90 y 90 y longitud entre -180 y 180")
    lat1, lon1 = map(math.radians, left)
    lat2, lon2 = map(math.radians, right)
    hav = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, max(0.0, hav))))
