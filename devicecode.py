import asyncio
import aiohttp
import urllib.parse

AUTH0_DOMAIN = "https://login.sharkninja.com"
CLIENT_ID = "wsguxrqm77mq4LtrTrwg8ZJUxmSrexGi"
SCOPES = "openid profile email offline_access"

async def get_device_code(session: aiohttp.ClientSession):
    url = f"{AUTH0_DOMAIN}/oauth/device/code"
    data = {
        "client_id": CLIENT_ID,
        "scope": SCOPES,
        # "audience": "...",  # add if/when you find an audience value
    }
    async with session.post(url, data=data) as resp:
        text = await resp.text()
        resp.raise_for_status()
        return await resp.json()

async def poll_for_token(session: aiohttp.ClientSession, device_code: str, interval: int):
    url = f"{AUTH0_DOMAIN}/oauth/token"
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
        "client_id": CLIENT_ID,
    }
    while True:
        async with session.post(url, data=data) as resp:
            txt = await resp.text()
            if resp.status == 200:
                return await resp.json()
            try:
                payload = await resp.json()
            except Exception:
                raise RuntimeError(f"Unexpected response: {resp.status} {txt}")

            err = payload.get("error")
            if err == "authorization_pending":
                await asyncio.sleep(interval)
                continue
            elif err == "slow_down":
                interval += 5
                await asyncio.sleep(interval)
                continue
            else:
                raise RuntimeError(f"Device code failed: {payload}")

async def main():
    async with aiohttp.ClientSession() as session:
        device_info = await get_device_code(session)
        print("Go to:", device_info["verification_uri"])
        print("Enter code:", device_info["user_code"])
        print("Or open:", device_info.get("verification_uri_complete", "<no direct link>"))

        tokens = await poll_for_token(
            session,
            device_info["device_code"],
            device_info.get("interval", 5),
        )
        print("Got tokens:", tokens)

if __name__ == "__main__":
    asyncio.run(main())
