import requests

# Pulled from sharkiqlib/const.py (NA/prod)
AUTH0_TOKEN_URL = "https://login.sharkninja.com/oauth/token"
AUTH0_CLIENT_ID = "wsguxrqm77mq4LtrTrwg8ZJUxmSrexGi"
AUTH0_SCOPES = "openid profile email offline_access"

AYLA_TOKEN_SIGN_IN = "https://user-sharkue1.aylanetworks.com/api/v1/token_sign_in"
DEVICE_HOST = "https://ads-sharkue1.aylanetworks.com"

# These are the Ayla app_id/secret that the Shark app uses to exchange the Auth0 id_token
SHARK_APP_ID = "ios_shark_prod-3A-id"
SHARK_APP_SECRET = "ios_shark_prod-74tFWGNg34LQCmR0m45SsThqrqs"

EMAIL = "dogg123456789@gmail.com"
PASSWORD = "Trta7A1Jq56$FKef!ys0IPoqfS8b8v"


def auth0_password_get_id_token(username: str, password: str) -> str:
    """
    Auth0 Resource Owner Password grant to fetch an id_token (no audience).
    The Shark app then passes this id_token to Ayla /token_sign_in.
    """
    payload = {
        "grant_type": "password",
        "client_id": AUTH0_CLIENT_ID,
        "username": username,
        "password": password,
        "scope": AUTH0_SCOPES,
    }
    headers = {"Content-Type": "application/json"}
    r = requests.post(AUTH0_TOKEN_URL, json=payload, headers=headers, timeout=15)
    print("auth0 status", r.status_code, r.text[:400])
    r.raise_for_status()
    data = r.json()
    if "id_token" not in data:
        raise RuntimeError("Auth0 response missing id_token")
    return data["id_token"]


def ayla_token_sign_in(id_token: str) -> tuple[str, str | None]:
    """
    Exchange Auth0 id_token for Ayla access_token via /api/v1/token_sign_in.
    """
    body = {
        "app_id": SHARK_APP_ID,
        "app_secret": SHARK_APP_SECRET,
        "token": id_token,
    }
    headers = {"Content-Type": "application/json"}
    r = requests.post(AYLA_TOKEN_SIGN_IN, json=body, headers=headers, timeout=15)
    print("token_sign_in status", r.status_code, r.text[:400])
    r.raise_for_status()
    j = r.json()
    return j["access_token"], j.get("refresh_token")


def ayla_list_devices(access_token: str):
    url = DEVICE_HOST + "/apiv1/devices.json"
    headers = {"Authorization": f"auth_token {access_token}"}
    r = requests.get(url, headers=headers, timeout=15)
    print("devices status", r.status_code)
    print(r.text[:800])
    r.raise_for_status()
    return r.json()


def ayla_set_property(access_token: str, dsn: str, prop_name: str, value):
    url = f"{DEVICE_HOST}/apiv1/dsns/{dsn}/properties/{prop_name}/datapoints.json"
    headers = {"Authorization": f"auth_token {access_token}"}
    body = {"datapoint": {"value": value}}
    r = requests.post(url, headers=headers, json=body, timeout=15)
    print("set prop status", r.status_code, r.text[:400])
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    id_token = auth0_password_get_id_token(EMAIL, PASSWORD)
    tok, _ = ayla_token_sign_in(id_token)
    devices = ayla_list_devices(tok)
    # Example: turn something on/off
    # ayla_set_property(tok, dsn="<device_dsn>", prop_name="some_property", value=1)
