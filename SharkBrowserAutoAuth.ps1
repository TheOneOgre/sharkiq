# Shark OAuth One-Shot Capture (wait mode)
# - Registers com.sharkninja.shark protocol handler under HKCU (current user)
# - Waits for redirect to trigger handler
# - Extracts code/state, copies code to clipboard, shows popup
# - Cleans up registry + temp files (no permanent changes)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms | Out-Null

$proto   = "com.sharkninja.shark"
$root    = "HKCU:\Software\Classes\$proto"
$tmpDir  = Join-Path $env:TEMP ("SharkOAuthCapture_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

$captureFile = Join-Path $tmpDir "captured_url.txt"
$handlerPs1  = Join-Path $tmpDir "handler.ps1"

@'
param([string]$url)
try {
  if ($url) { $url = $url.Trim('"') }
  $out = $env:SHARK_OAUTH_CAPTURE_FILE
  if ($out) { Set-Content -Path $out -Value $url -Encoding UTF8 -Force }
} catch { }
'@ | Set-Content -Path $handlerPs1 -Encoding UTF8 -Force

function Cleanup {
  try { Remove-Item -Path $root -Recurse -Force -ErrorAction SilentlyContinue } catch {}
  try { Remove-Item -Path $tmpDir -Recurse -Force -ErrorAction SilentlyContinue } catch {}
}

function Extract-CodeState([string]$capturedUrl) {
  $code = $null; $state = $null
  try {
    $uri = [Uri]$capturedUrl
    $q = $uri.Query.TrimStart('?')
    $pairs = $q.Split('&') | Where-Object { $_ -match '=' }
    $kv = @{}
    foreach ($p in $pairs) {
      $k,$v = $p.Split('=',2)
      $kv[[Uri]::UnescapeDataString($k)] = [Uri]::UnescapeDataString($v)
    }
    $code  = $kv["code"]
    $state = $kv["state"]
  } catch {}
  return @($code, $state)
}

try {
  # Ensure capture file doesn't exist
  Remove-Item -Path $captureFile -Force -ErrorAction SilentlyContinue

  # Register protocol handler
  New-Item -Path "$root\shell\open\command" -Force | Out-Null
  Set-ItemProperty -Path $root -Name "(default)" -Value "URL:$proto Protocol" | Out-Null
  New-ItemProperty -Path $root -Name "URL Protocol" -Value "" -Force | Out-Null

  # Protocol launch command -> writes captured URL into $captureFile
  $cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"& { `$env:SHARK_OAUTH_CAPTURE_FILE='$captureFile'; & '$handlerPs1' '%1' }`""
  Set-ItemProperty -Path "$root\shell\open\command" -Name "(default)" -Value $cmd | Out-Null

  # Tell user what to do next
  [System.Windows.Forms.MessageBox]::Show(
    "Ready.`n`nNow go back to Home Assistant and click the Shark login link.`n`nThis helper will wait for the redirect and then show/copy the code.",
    "Shark OAuth One-Shot"
  ) | Out-Null

  # Wait up to 10 minutes for redirect
  $deadline = (Get-Date).AddMinutes(10)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path $captureFile) { break }
    Start-Sleep -Milliseconds 200
  }

  if (!(Test-Path $captureFile)) {
    [System.Windows.Forms.MessageBox]::Show(
      "Timed out waiting for the redirect.`n`nIf you completed login but nothing was captured, your system may be opening a Shark app (or another handler) instead of this temporary one.",
      "Shark OAuth One-Shot"
    ) | Out-Null
    exit 1
  }

  $captured = (Get-Content -Path $captureFile -Raw).Trim().Trim('"')
  $code, $state = Extract-CodeState $captured

  if ($code) {
    Set-Clipboard -Value $code
    $msg = "✅ Captured auth code (copied to clipboard):`n`n$code`n`nState: $state`n`nPaste the code into Home Assistant, then click OK to clean up."
  } else {
    Set-Clipboard -Value $captured
    $msg = "✅ Captured redirect URL (copied to clipboard):`n`n$captured`n`nNo 'code=' found. Paste the URL into Home Assistant, then click OK to clean up."
  }

  [System.Windows.Forms.MessageBox]::Show($msg, "Shark OAuth One-Shot") | Out-Null
}
catch {
  [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "Shark OAuth One-Shot") | Out-Null
  exit 1
}
finally {
  Cleanup
}
