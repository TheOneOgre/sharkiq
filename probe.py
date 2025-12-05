#!/usr/bin/env python3
"""
Probe SharkNinja Azure endpoints to find the Ayla/CloudCore URLs.

This version can also obtain an Auth0 access token for you via:
  - existing AUTH0_ACCESS_TOKEN env var (preferred)
  - AUTH0_REFRESH_TOKEN env var
  - username/password (ROPC / password-realm)
"""

import base64
import json
import os
import time
from typing import Dict, Iterable, List, Tuple

import requests

# ---------------------------------------------------------------------------
# Auth0 config (hardcoded defaults; change to your own values)
# ---------------------------------------------------------------------------
AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID", "wsguxrqm77mq4LtrTrwg8ZJUxmSrexGi")
AUTH0_SCOPE = os.environ.get("AUTH0_SCOPE", "openid profile email offline_access")
# If the APK reveals a specific audience, set it here; else leave None
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE") or None
# Realm for password-realm grant; typical Auth0 default is "Username-Password-Authentication"
AUTH0_REALM = os.environ.get("AUTH0_REALM", "Username-Password-Authentication")

# Region/env flags from AuthenticationViewModel
CLOUD_ENV = os.environ.get("CLOUD_ENV", "prod")  # "prod" or "dev"
REGION_CODE = os.environ.get("REGION_CODE", "NA")  # "NA" or "EU"
FORCE_EU = os.environ.get("FORCE_EU", "").lower() == "true"
FORCE_NA = os.environ.get("FORCE_NA", "").lower() == "true"
AUTH0_DOMAIN_OVERRIDE = os.environ.get("AUTH0_DOMAIN")  # use to hardcode e.g. https://login.sharkninja.com

# Credential inputs (optional; env vars are safer than literals)
AUTH0_USERNAME = os.environ.get("AUTH0_USERNAME", "dogg123456789@gmail.com")
AUTH0_PASSWORD = os.environ.get("AUTH0_PASSWORD", "Trta7A1Jq56$FKef!ys0IPoqfS8b8v")
AUTH0_REFRESH_TOKEN = os.environ.get("AUTH0_REFRESH_TOKEN")

# ---------------------------------------------------------------------------
# Probe targets
# ---------------------------------------------------------------------------
BASE_URLS = [
    "https://sharkninja-prd-cus-001.azure-api.net",
    "https://sharkninja.azure-api.net",
]

PATH_PREFIXES = [
    "",
    "/icm",
    "/icm/b2c",
    "/icm/b2c/SharkNinja-US-Site",
    "/icm/b2c/SharkNinja-US-Site/sharkus",
    "/mobile",
    "/mobile/v1",
    "/app",
]

CONFIG_PATHS = [
    "/config",
    "/user/config",
    "/user/profile",
    "/iot/config",
    "/cloudcore/config",
    "/cloudcore",
    "/cloud/config",
    "/mobile/config",
    "/env/config",
    "/app-config",
    "/environment",
    "/featureflag",
    "",
]

KEYWORDS = [
    "ayla",
    "aylanetworks",
    "ads-field",
    "user-field",
    "device_url",
    "cloudcore",
    "39a9391a",
    "shark-android-field-id",       # AYLA_APPID
    "shark-android-field-wv43mbdx", # AYLA_SECRET fragment
    "app-shark-",                   # template prefix
    "appside deeplinkenv",
    "countryregionselectionserver",
]

REQUEST_TIMEOUT = 8
SLEEP_BETWEEN_CALLS = 0.2


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def decode_base64url(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def decode_jwt(token: str) -> Tuple[Dict, Dict]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Token does not look like a JWT")
    header = json.loads(decode_base64url(parts[0]).decode("utf-8"))
    payload = json.loads(decode_base64url(parts[1]).decode("utf-8"))
    return header, payload


def build_auth0_domain() -> str:
    """Mirror AuthenticationViewModel.a0() domain selection."""
    if AUTH0_DOMAIN_OVERRIDE:
        return AUTH0_DOMAIN_OVERRIDE.rstrip("/")

    use_dev = CLOUD_ENV.lower() == "dev"
    if use_dev:
        return "https://login-dev.sharkninja.com"
    if FORCE_EU:
        return "https://logineu.sharkninja.com"
    if FORCE_NA:
        return "https://login.sharkninja.com"

    rc = REGION_CODE.upper()
    if rc in ("NA", "NORTHAMERICA", "US"):
        return "https://login.sharkninja.com"
    if rc in ("EU", "EUROPE"):
        return "https://logineu.sharkninja.com"
    return "https://login.sharkninja.com"


def oidc_discover(domain: str) -> Dict:
    url = domain.rstrip("/") + "/.well-known/openid-configuration"
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    try:
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def token_endpoint_from_discovery(domain: str) -> str:
    oidc = oidc_discover(domain)
    te = oidc.get("token_endpoint") if oidc else None
    if te:
        return te
    return domain.rstrip("/") + "/oauth/token"


def fetch_with_refresh(token_endpoint: str, refresh_token: str) -> Dict:
    data = {
        "grant_type": "refresh_token",
        "client_id": AUTH0_CLIENT_ID,
        "refresh_token": refresh_token,
        "scope": AUTH0_SCOPE,
    }
    if AUTH0_AUDIENCE:
        data["audience"] = AUTH0_AUDIENCE
    r = requests.post(token_endpoint, data=data, timeout=REQUEST_TIMEOUT)
    try:
        return r.json()
    except Exception:
        return {"raw": r.text, "status": r.status_code}


def fetch_with_password(token_endpoint: str, username: str, password: str) -> Dict:
    """
    Try ROPC. If AUTH0_REALM is set, use password-realm grant; otherwise plain password grant.
    """
    data = {
        "client_id": AUTH0_CLIENT_ID,
        "username": username,
        "password": password,
        "scope": AUTH0_SCOPE,
    }
    if AUTH0_AUDIENCE:
        data["audience"] = AUTH0_AUDIENCE

    if AUTH0_REALM:
        data["grant_type"] = "http://auth0.com/oauth/grant-type/password-realm"
        data["realm"] = AUTH0_REALM
    else:
        data["grant_type"] = "password"

    print("[+] Requesting password grant (password hidden)")
    r = requests.post(token_endpoint, data=data, timeout=REQUEST_TIMEOUT)
    try:
        return r.json()
    except Exception:
        return {"raw": r.text, "status": r.status_code}


def acquire_access_token() -> Tuple[str | None, Dict]:
    """
    Priority:
      1) AUTH0_ACCESS_TOKEN env
      2) AUTH0_REFRESH_TOKEN env -> refresh
      3) AUTH0_USERNAME/PASSWORD env -> password grant
    Returns (access_token, full_response_json)
    """
    direct = os.environ.get("AUTH0_ACCESS_TOKEN")
    if direct:
        return direct, {"source": "env"}

    domain = build_auth0_domain()
    token_endpoint = token_endpoint_from_discovery(domain)

    if AUTH0_REFRESH_TOKEN:
        j = fetch_with_refresh(token_endpoint, AUTH0_REFRESH_TOKEN)
        return j.get("access_token"), j

    if AUTH0_USERNAME and AUTH0_PASSWORD:
        j = fetch_with_password(token_endpoint, AUTH0_USERNAME, AUTH0_PASSWORD)
        return j.get("access_token"), j

    return None, {}


# ---------------------------------------------------------------------------
# Probing helpers
# ---------------------------------------------------------------------------
def build_targets() -> Iterable[str]:
    for base in BASE_URLS:
        for prefix in PATH_PREFIXES:
            for cfg in CONFIG_PATHS:
                url = "/".join([base.rstrip("/"), prefix.strip("/"), cfg.strip("/")]).rstrip("/")
                yield url


def search_hits(body: str) -> List[str]:
    body_lower = body.lower()
    return [kw for kw in KEYWORDS if kw in body_lower]


def probe_endpoint(url: str, token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "cloudcore-discovery/1.2",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        return False, [], f"Request failed: {exc}", 0
    hits = search_hits(resp.text or "")
    ok = resp.status_code < 500 and bool(hits)
    return ok, hits, resp.text or "", resp.status_code


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    token, token_json = acquire_access_token()
    if not token:
        print("No access token available. Set one of:")
        print("  - AUTH0_ACCESS_TOKEN")
        print("  - AUTH0_REFRESH_TOKEN (with AUTH0_CLIENT_ID)")
        print("  - AUTH0_USERNAME + AUTH0_PASSWORD [+ AUTH0_REALM]")
        return

    print("[+] Access token acquired (source:", token_json.get("source", "oauth/token"), ")")

    # Decode JWT for clues; skip if it is not a JWT
    try:
        header, payload = decode_jwt(token)
        print("=== JWT Header ===")
        print(json.dumps(header, indent=2))
        print("\n=== JWT Payload ===")
        print(json.dumps(payload, indent=2))
    except Exception as exc:
        print(f"JWT decode failed (may be opaque token): {exc}")

    print("\n=== Probing endpoints ===")
    targets = list(build_targets())
    print(f"Total targets: {len(targets)}")

    hits_found = 0
    for idx, url in enumerate(targets, 1):
        ok, hits, body, status = probe_endpoint(url, token)
        if ok:
            hits_found += 1
            print(f"\nHIT [{status}] {url}")
            print(f"Matched keywords: {', '.join(hits)}")
            print(f"Snippet: {(body[:800] or '').replace(chr(10), ' ')}")
        time.sleep(SLEEP_BETWEEN_CALLS)

    if hits_found == 0:
        print("\nNo hits found. Consider expanding paths/keywords or enabling verbose misses.")


if __name__ == "__main__":
    main()
