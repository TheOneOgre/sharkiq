import requests

AUTH0_URL       = "https://login.sharkninja.com"
AUTH0_CLIENT_ID = "wsguxrqm77mq4LtrTrwg8ZJUxmSrexGi"
USERNAME        = "dogg123456789@gmail.com"
PASSWORD        = "Trta7A1Jq56$FKef!ys0IPoqfS8b8v"

AZURE_US_BASE   = "https://sharkninja-prd-cus-001.azure-api.net/icm/b2c/SharkNinja-US-Site/sharkus/"
AZURE_EU_BASE   = "https://sharkninja.azure-api.net/icm/b2c/SharkNinja-EU-Site/"

def get_auth0_token():
    token_url = f"{AUTH0_URL}/oauth/token"
    payload = {
        "grant_type": "password",
        "client_id": AUTH0_CLIENT_ID,
        "username": USERNAME,
        "password": PASSWORD,
        "scope": "openid profile email offline_access",
    }
    r = requests.post(token_url, json=payload)
    print("[+] Auth0 status:", r.status_code)
    print("[+] Auth0 body:", r.text[:400])
    r.raise_for_status()
    return r.json()["access_token"]

def poke_azure(base, token, path=""):
    url = base + path
    headers = {
        "Authorization": f"Bearer {token}",
        # sometimes needed:
        # "Ocp-Apim-Subscription-Key": "...",
    }
    print(f"[+] GET {url}")
    r = requests.get(url, headers=headers)
    print("[+] Status:", r.status_code)
    print("[+] Body:", r.text[:800])

if __name__ == "__main__":
    token = get_auth0_token()
    # Start by hitting the base; sometimes they redirect or error with useful info
    poke_azure(AZURE_US_BASE, token)
    # then try likely paths (example guesses):
    for path in ["user/profile", "user/config", "config", "cloudcore/config", "iot/config"]:
        print("\n---", path, "---")
        poke_azure(AZURE_US_BASE, token, path)
