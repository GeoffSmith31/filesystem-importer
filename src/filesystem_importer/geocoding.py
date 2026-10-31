
"""Forward geocoding of directory location names using Nominatim."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from filesystem_importer.settings import AppSettings
from filesystem_importer.app_logging import get_logger
from filesystem_importer.geocoding_rate_limit import geocoding_rate_limiter
from filesystem_importer.location_cache import LocationCache

logger = get_logger(__name__)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
REQUEST_TIMEOUT_SECONDS = 10

# Nominatim requires an identifiable User-Agent.
# Replace the contact placeholder with a real project contact before use.
USER_AGENT = "FilesystemImporter/0.1 (contact: REPLACE-WITH-CONTACT)"

_default_cache = LocationCache()

_settings: AppSettings | None = None


def configure_geocoding(settings: AppSettings) -> None:
    """Provide application settings to the geocoding module."""
    global _settings
    _settings = settings
    logger.info("Geocoding settings configured.")

def is_locally_plausible_location(name: str) -> bool:
    """Reject empty names and names containing only digits/punctuation."""
    if not name or not name.strip():
        return False

    return any(character.isalpha() for character in name)


def _query_nominatim(
    location_name: str,
    *,
    timeout: float,
    user_agent: str,
) -> bool | None:
    """Return True for a result, False for no result, or None on failure."""
    parameters = urlencode(
        {
            "q": location_name.strip(),
            "format": "jsonv2",
            "limit": 1,
        }
    )
    url = f"{NOMINATIM_SEARCH_URL}?{parameters}"
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
        method="GET",
    )

    logger.debug("Sending Nominatim location query for %r.", location_name)

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()

        results = json.loads(payload.decode("utf-8"))

        if not isinstance(results, list):
            logger.warning(
                "Nominatim returned an unexpected response for %r.",
                location_name,
            )
            return None

        if results:
            logger.info("Nominatim found a match for location %r.", location_name)
            return True

        logger.info("Nominatim found no match for location %r.", location_name)
        return False

    except HTTPError as exc:
        # Includes 403 and 429. These are service failures, not no-match results.
        logger.warning(
            "Nominatim HTTP error for location %r: HTTP %s.",
            location_name,
            exc.code,
        )
        return None

    except (URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "Nominatim request failed for location %r: %s.",
            location_name,
            exc,
        )
        return None

    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning(
            "Could not decode Nominatim response for location %r: %s.",
            location_name,
            exc,
        )
        return None



def check_location(
    location_name: str,
    *,
    cache: LocationCache | None = None,
    rate_limiter=geocoding_rate_limiter,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> bool | None:
    """Check whether a location name is recognised by Nominatim.

    Returns:
        True: a result was found.
        False: the request succeeded but found no result, or the name
            failed local plausibility checks.
        None: the service could not provide a reliable answer.

    Only definitive True/False results are cached.
    Local rejections and service failures are not cached.
    """
    name = location_name.strip() if location_name else ""

    if not is_locally_plausible_location(name):
        logger.debug(
            "Rejected location %r locally; no HTTP request needed.",
            location_name,
        )
        return False

    if _settings is None:
        logger.warning(
            "Geocoding settings have not been configured."
        )
        return None

    user_agent = _settings.user_agent
    if not user_agent:
        logger.warning(
            "No geocoding User-Agent is available."
        )
        return None

    location_cache = cache if cache is not None else _default_cache

    cached_result = location_cache.lookup(name)
    if cached_result is not None:
        logger.debug(
            "Using cached location result for %r: %s.",
            name,
            "valid" if cached_result else "invalid",
        )
        return cached_result

    # Reserve a request slot immediately before making the HTTP request.
    rate_limiter.wait_for_slot()

    result = _query_nominatim(
        name,
        timeout=timeout,
        user_agent=user_agent,
    )

    if result is None:
        logger.info(
            "Location %r remains unverified because the geocoding service "
            "was unavailable. The failure was not cached.",
            name,
        )
        return None

    location_cache.store(name, valid=result)
    return result
    
def reverse_geocode(
    latitude: float,
    longitude: float,
    *,
    rate_limiter=geocoding_rate_limiter,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> str | None:
    """Resolve GPS coordinates to the most specific available place name.

    Returns:
        A location name, or None if the location could not be resolved.
    """

    if _settings is None:
        logger.warning("Geocoding settings have not been configured.")
        return None

    user_agent = _settings.user_agent
    if not user_agent:
        logger.warning("No geocoding User-Agent is available.")
        return None

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid GPS coordinates: latitude=%r, longitude=%r.",
            latitude,
            longitude,
        )
        return None

    if (
        not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        logger.warning(
            "GPS coordinates out of range: latitude=%s, longitude=%s.",
            latitude,
            longitude,
        )
        return None

    parameters = urlencode(
        {
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
        }
    )

    url = f"{NOMINATIM_REVERSE_URL}?{parameters}"

    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
        method="GET",
    )

    logger.debug(
        "Sending Nominatim reverse query for latitude=%s, longitude=%s.",
        latitude,
        longitude,
    )

    # Reserve a request slot immediately before making the HTTP request.
    rate_limiter.wait_for_slot()

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()

        result = json.loads(payload.decode("utf-8"))

    except HTTPError as exc:
        logger.warning(
            "Nominatim reverse HTTP error: HTTP %s.",
            exc.code,
        )
        return None

    except (URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "Nominatim reverse request failed: %s.",
            exc,
        )
        return None

    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning(
            "Could not decode Nominatim reverse response: %s.",
            exc,
        )
        return None

    if not isinstance(result, dict):
        logger.warning("Nominatim returned an unexpected reverse response.")
        return None

    address = result.get("address")

    if not isinstance(address, dict):
        logger.info(
            "Nominatim returned no address for latitude=%s, longitude=%s.",
            latitude,
            longitude,
        )
        return None

    # Select the most specific available place name.
    for address_type in (
        "village",
        "town",
        "suburb",
        "city",
        "state",
        "country",
    ):
        location_name = address.get(address_type)

        if isinstance(location_name, str) and location_name.strip():
            location_name = location_name.strip()

            logger.info(
                "Reverse geocoding resolved coordinates to %s: %s.",
                address_type,
                location_name,
            )
            return location_name

    logger.info(
        "Nominatim returned no usable place name for latitude=%s, "
        "longitude=%s.",
        latitude,
        longitude,
    )
    return None

def location_validate(location_name: str) -> bool | None:
    """Validate a location name using the configured geocoding service.

    Returns:
        True: the location was recognised.
        False: the location was not recognised.
        None: the location could not be verified.
    """
    return check_location(location_name)
