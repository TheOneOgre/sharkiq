# Shark OAuth One-Shot Capture (wait mode, terminal UI)
# - Registers com.sharkninja.shark protocol handler under HKCU (current user)
# - Waits for redirect to trigger handler
# - Copies FULL redirect URL to clipboard, prints it to terminal
# - Cleans up registry + temp files (no permanent changes)

$ErrorActionPreference = "Stop"

$proto   = "com.sharkninja.shark"
$root    = "HKCU:\Software\Classes\$proto"
$tmpDir  = Join-Path $env:TEMP ("SharkOAuthCapture_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

$captureFile = Join-Path $tmpDir "captured_url.txt"
$handlerPs1  = Join-Path $tmpDir "handler.ps1"

@'
param(
  [string]$capturePath,
  [string]$url
)
try {
  if ($url) { $url = $url.Trim('"') }
  if ($capturePath) {
    Set-Content -Path $capturePath -Value $url -Encoding UTF8 -Force
  }
} catch { }
'@ | Set-Content -Path $handlerPs1 -Encoding UTF8 -Force

function Cleanup {
  try { Remove-Item -Path $root -Recurse -Force -ErrorAction SilentlyContinue } catch {}
  try { Remove-Item -Path $tmpDir -Recurse -Force -ErrorAction SilentlyContinue } catch {}
}

try {
  Write-Host "Shark OAuth One-Shot: setting up temporary protocol handler..." -ForegroundColor Cyan

  # Ensure capture file doesn't exist
  Remove-Item -Path $captureFile -Force -ErrorAction SilentlyContinue

  # Register protocol handler
  New-Item -Path "$root\shell\open\command" -Force | Out-Null
  Set-ItemProperty -Path $root -Name "(default)" -Value "URL:$proto Protocol" | Out-Null
  New-ItemProperty -Path $root -Name "URL Protocol" -Value "" -Force | Out-Null

  # Protocol launch command -> writes captured URL into $captureFile
  $cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$handlerPs1`" `"$captureFile`" `"%1`""
  Set-ItemProperty -Path "$root\shell\open\command" -Name "(default)" -Value $cmd | Out-Null

  Write-Host ""
  Write-Host "READY." -ForegroundColor Green
  Write-Host "1) Go back to Home Assistant" -ForegroundColor Gray
  Write-Host "2) Click the Shark login link" -ForegroundColor Gray
  Write-Host "3) After login, this window will print + copy the redirect URL" -ForegroundColor Gray
  Write-Host ""
  Write-Host "Waiting for redirect..." -ForegroundColor Yellow

  # Wait up to 10 minutes for redirect
  $deadline = (Get-Date).AddMinutes(10)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path $captureFile) { break }
    Start-Sleep -Milliseconds 200
  }

  if (!(Test-Path $captureFile)) {
    Write-Host ""
    Write-Host "Timed out waiting for the redirect." -ForegroundColor Red
    Write-Host "If you completed login but nothing was captured, your system may be opening a Shark app or another handler instead." -ForegroundColor Red
    exit 1
  }

  $captured = (Get-Content -Path $captureFile -Raw).Trim().Trim('"')

  Write-Host ""
  Write-Host "CAPTURED ✅  (copied to clipboard)" -ForegroundColor Green

  try {
    Set-Clipboard -Value $captured
  } catch {
    Write-Host "Warning: failed to copy to clipboard: $($_.Exception.Message)" -ForegroundColor DarkYellow
  }

  Write-Host ""
  Write-Host "Paste this into Home Assistant:" -ForegroundColor Cyan
  Write-Host $captured -ForegroundColor White
  Write-Host ""

  # Optional: keep window open a moment so users see it even if launched from a one-liner
  Write-Host "Cleaning up temporary handler..." -ForegroundColor Gray
}
catch {
  Write-Host ""
  Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
finally {
  Cleanup
  Write-Host "Done. You can close this window." -ForegroundColor Gray
}
Read-Host "Press Enter to exit"
