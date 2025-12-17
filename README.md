# SharkIQ (Experimental / Testing)

This repository is a **custom HACS source** used for testing very new and experimental SharkIQ integration code.

---

## Install via HACS (Custom Repository)

1. In Home Assistant, open **HACS** → **Integrations**
2. Open the menu (top-right) → **Custom repositories**
3. Add this repository URL:

   - Repository: `https://github.com/TheOneOgre/sharkiq`  
   - Category: **Integration**  

4. Find **Sharkiq Dev** in HACS and install the latest release
5. **Restart Home Assistant**
6. Go to **Settings** → **Devices & services** → **Add Integration**
7. Search for and install: **Sharkiq Dev**

If you encounter any issues during install or setup, please report them on 'https://github.com/sharkiqlibs/sharkiq/issues/141'.

---

## Browser Login Helper (Optional)

Some authentication flows require completing a **browser-based OAuth login**.  
Because Shark uses a mobile-style redirect URI, copying the resulting redirect URL manually can be inconvenient.

For user convenience, this repository includes an **optional Windows helper script** that simplifies this process.

### What the helper does

The `SharkBrowserAutoAuth.ps1` script will:

- Temporarily register a handler for Shark’s custom redirect URI
- Wait while you click the **Login** link in Home Assistant and complete the browser login
- Automatically capture the redirect URL when the browser hands it off
- Copy the full redirect URL to your clipboard
- Display progress and the captured URL in the terminal
- **Clean up automatically** (removes the handler and all temporary files when finished)

No permanent system changes are left behind.

> **Important:**  
> This helper is **optional** and provided only as a convenience.  
> The integration itself does **not** require external scripts to function.

---

## How to use the helper

1. Open a PowerShell window
2. Run the command below
3. Return to Home Assistant and click the Shark **Login** link
4. Complete the browser login
5. Paste the captured redirect URL into Home Assistant when prompted

### One-line PowerShell command

```powershell
$u='https://raw.githubusercontent.com/TheOneOgre/sharkiq/main/SharkBrowserAutoAuth.ps1';$p="$env:TEMP\SharkOAuth.ps1";iwr $u -OutFile $p;& $p;rm $p
