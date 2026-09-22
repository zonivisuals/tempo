# packaging — sidecar installer + panel signing (Windows-only for now)

## Sidecar (`build-windows.ps1`)

PyInstaller `--onedir` (Velopack updates a folder — `--onefile` is
incompatible) + `vpk pack` into `Setup.exe` (or MSI with `-Msi`).
Version comes from `service/pyproject.toml` — the single source.
Releases feed from any HTTPS dir/S3/R2/GitHub Releases (Velopack
`UpdateManager` URL baked at first run; deltas automatic).

```powershell
.\packaging\build-windows.ps1
.\packaging\build-windows.ps1 -Version 0.2.0 -Channel beta -Msi
```

Release machine needs: Python 3.11+, `pip install ./service`,
`pip install pyinstaller`, `dotnet tool install -g vpk`, code-signing
cert (EV recommended — SmartScreen reputation otherwise).
Scripts are parse-checked in CI; the full build runs on the release
machine and its output is smoke-tested per docs/release.md.

## Panel (`zxp-sign.ps1`)

ZXPSignCmd from Adobe-CEP/CEP-Resources. Dev: self-signed cert.
Release: real certificate + timestamp server (CEP re-checks the cert
EVERY launch — an expired cert silently kills the panel, so repackage
BEFORE expiry). List via Adobe Developer Distribution.
