"""
Microgrid Utilities — PostGIS zone lookup helpers.
"""

import math

from app.database import get_supabase


def _fetch_supported_cities() -> list[dict]:
    db = get_supabase()
    result = (
        db.table("supported_cities")
        .select("*")
        .eq("pricing_enabled", True)
        .execute()
    )
    return result.data or []


def list_supported_cities() -> list[dict]:
    return _fetch_supported_cities()


def get_city_by_name(city_name: str) -> dict | None:
    for city in _fetch_supported_cities():
        if city["name"] == city_name:
            return city
    return None


def infer_city_from_coords(lat: float, lng: float) -> str:
    """Infer supported city from DB-backed city bounds."""
    for city in _fetch_supported_cities():
        if (
            city["lat_min"] <= lat <= city["lat_max"]
            and city["lng_min"] <= lng <= city["lng_max"]
        ):
            return city["name"]
    return "Coverage Pending"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def is_supported_city(city: str) -> bool:
    return any(item["name"] == city for item in _fetch_supported_cities())


def get_supported_city_by_coords(lat: float, lng: float) -> dict | None:
    for city in _fetch_supported_cities():
        if (
            city["lat_min"] <= lat <= city["lat_max"]
            and city["lng_min"] <= lng <= city["lng_max"]
        ):
            return city
    return None


def find_grid_by_coordinates(lat: float, lng: float) -> dict | None:
    """Find which microgrid contains the given coordinates using PostGIS."""
    db = get_supabase()
    city_meta = get_supported_city_by_coords(lat, lng)
    if not city_meta:
        return None

    try:
        result = db.rpc(
            "find_grid_by_point",
            {"p_lat": lat, "p_lng": lng},
        ).execute()
        if result.data and len(result.data) > 0:
            grid = result.data[0]
            if grid.get("city") == city_meta["name"]:
                return grid
    except Exception:
        pass

    # Fallback: find nearest grid within the inferred city only.
    result = (
        db.table("microgrids")
        .select("*")
        .eq("city", city_meta["name"])
        .limit(400)
        .execute()
    )
    if not result.data:
        return None

    # Find closest grid by great-circle distance.
    best = None
    best_dist = float("inf")
    for grid in result.data:
        dist = _haversine_km(lat, lng, grid["center_lat"], grid["center_lng"])
        if dist < best_dist:
            best_dist = dist
            best = grid

    lookup_radius = max(
        _haversine_km(
            city_meta["lat_min"],
            city_meta["lng_min"],
            city_meta["lat_max"],
            city_meta["lng_max"],
        )
        / 2,
        10,
    )
    if best is None or best_dist > lookup_radius:
        return None
    return best


def get_grid_by_id(grid_id: str) -> dict | None:
    """Get a specific microgrid by ID."""
    db = get_supabase()
    try:
        result = (
            db.table("microgrids")
            .select("*")
            .eq("id", grid_id)
            .limit(1)
            .execute()
        )
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except Exception:
        return None


def reconcile_worker_grid(worker: dict, persist: bool = True) -> dict | None:
    """
    Ensure a worker points at a currently supported microgrid.

    This heals stale worker records after grid bootstrap/schema refreshes by
    recomputing the grid from saved coordinates and optionally persisting the
    repaired grid/city back to the worker row.
    """
    current_grid_id = worker.get("grid_id")
    if current_grid_id:
        current = get_grid_by_id(str(current_grid_id))
        if current:
            if (
                persist
                and worker.get("id")
                and current.get("city")
                and worker.get("city") != current.get("city")
            ):
                try:
                    get_supabase().table("workers").update(
                        {"city": current["city"]}
                    ).eq("id", worker["id"]).execute()
                    worker["city"] = current["city"]
                except Exception:
                    pass
            return current

    lat = worker.get("zone_lat")
    lng = worker.get("zone_lng")
    if lat is None or lng is None:
        return None

    try:
        resolved = find_grid_by_coordinates(float(lat), float(lng))
    except Exception:
        resolved = None

    if not resolved:
        return None

    worker["grid_id"] = resolved["id"]
    if resolved.get("city"):
        worker["city"] = resolved["city"]

    if persist and worker.get("id"):
        try:
            get_supabase().table("workers").update(
                {
                    "grid_id": resolved["id"],
                    "city": resolved.get("city", worker.get("city")),
                }
            ).eq("id", worker["id"]).execute()
        except Exception:
            pass

    return resolved
