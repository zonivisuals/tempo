param(
  [string]$UrlPath = "/",
  [string]$Out = "shot.png",
  [int]$WaitMs = 3200,
  [int]$Width = 1440,
  [int]$Height = 900,
  [switch]$FullPage,
  [string]$ScrollTo = "",
  [int]$OffsetY = -80
)
$ErrorActionPreference = "Stop"
$Port = 4100 + (Get-Random -Minimum 0 -Maximum 300)
$Url = "http://localhost:$Port$UrlPath"
$Root = (Get-Location).Path

$nextBin = Join-Path $Root "node_modules\next\dist\bin\next"
if (-not (Test-Path $nextBin)) { throw "next binary not found at $nextBin" }

$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = "node"
$pinfo.Arguments = "`"$nextBin`" start -p $Port"
$pinfo.WorkingDirectory = $Root
$pinfo.UseShellExecute = $false
$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true
$serverProc = [System.Diagnostics.Process]::Start($pinfo)

$ready = $false
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 1
  try {
    $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    $ready = $true
    break
  } catch { }
}
if (-not $ready) {
  "--- server stdout ---"; $serverProc.StandardOutput.ReadToEnd() | Select-Object -Last 10
  "--- server stderr ---"; $serverProc.StandardError.ReadToEnd() | Select-Object -Last 10
  & taskkill /T /F /PID $serverProc.Id 2>&1 | Out-Null
  throw "server not ready on $Url"
}

$scrollToJs = if ($ScrollTo -ne "") { "`"$ScrollTo`"" } else { "null" }
$js = @"
import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: $Width, height: $Height },
  deviceScaleFactor: 1,
});
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE:", m.text().slice(0, 140)); });
await page.goto("$Url", { waitUntil: "networkidle" });
await page.waitForTimeout($WaitMs);
const SEL = $scrollToJs;
if (SEL) {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el) el.scrollIntoView({ behavior: "instant", block: "start" });
  }, SEL);
  await page.evaluate((dy) => window.scrollBy(0, dy), $OffsetY);
}
if ($(if ($FullPage) { "true" } else { "false" })) {
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.6;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 260));
    }
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise((r) => setTimeout(r, 700));
    window.scrollTo(0, 0);
    await new Promise((r) => setTimeout(r, 400));
  });
}
await page.screenshot({ path: process.env.TEMP + "/opencode/$Out", fullPage: $(if ($FullPage) { "true" } else { "false" }) });
await browser.close();
console.log("shot: $Out");
"@
$js | Set-Content "scripts/.shot-run.mjs" -Encoding utf8
node "scripts/.shot-run.mjs"
Remove-Item "scripts/.shot-run.mjs" -ErrorAction SilentlyContinue

& taskkill /T /F /PID $serverProc.Id 2>&1 | Out-Null
