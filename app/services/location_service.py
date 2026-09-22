"""Nearby shops: read coordinates safely and work out distances.

No map service is used. A shop stores a latitude and longitude; the customer's
position comes from their browser ("Use my location") or typed coordinates. The
distance between two points on Earth is calculated with the haversine formula.
"""
import math

EARTH_RADIUS_KM = 6371.0088
RADIUS_OPTIONS = (1, 2, 5, 10, 25)   # kilometres offered on the page
DEFAULT_RADIUS = 5


class LocationError(ValueError):
    """Bad coordinates. The text is a friendly message for the person."""


def haversine_km(lat1, lng1, lat2, lng2):
    """Straight-line ("as the crow flies") distance in kilometres between two points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def parse_coordinates(lat_text, lng_text):
    """Return (latitude, longitude) as floats, or (None, None) if both are blank.

    Raises LocationError if only one is given, they are not numbers, or they are
    outside the valid range (latitude -90..90, longitude -180..180).
    """
    lat_text = (lat_text or "").strip()
    lng_text = (lng_text or "").strip()
    if not lat_text and not lng_text:
        return None, None
    if not lat_text or not lng_text:
        raise LocationError("Please give both latitude and longitude, or leave both empty.")
    try:
        lat, lng = float(lat_text), float(lng_text)
    except ValueError:
        raise LocationError("Latitude and longitude must be numbers, like 17.385 and 78.4867.")
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise LocationError("Latitude and longitude must be real numbers.")
    if not -90 <= lat <= 90:
        raise LocationError("Latitude must be between -90 and 90.")
    if not -180 <= lng <= 180:
        raise LocationError("Longitude must be between -180 and 180.")
    return round(lat, 6), round(lng, 6)


def parse_radius(text):
    """One of RADIUS_OPTIONS; anything else falls back to the default."""
    try:
        value = int((text or "").strip())
    except ValueError:
        return DEFAULT_RADIUS
    return value if value in RADIUS_OPTIONS else DEFAULT_RADIUS


def shops_near(shops, lat, lng, radius_km):
    """Shops within radius_km of the point, nearest first.

    Returns (rows, without_location): rows is [(shop, distance_km), ...];
    without_location counts shops that have no coordinates (they can't be placed).
    """
    rows, without_location = [], 0
    for shop in shops:
        if not shop.has_location:
            without_location += 1
            continue
        distance = haversine_km(lat, lng, shop.latitude, shop.longitude)
        if distance <= radius_km:
            rows.append((shop, distance))
    rows.sort(key=lambda row: (row[1], row[0].name.lower()))
    return rows, without_location


def format_distance(km):
    """'350 m' for short distances, '2.4 km' otherwise."""
    if km < 1:
        return f"{round(km * 1000 / 10) * 10:.0f} m"
    return f"{km:.1f} km"
