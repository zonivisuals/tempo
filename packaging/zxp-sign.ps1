#Requires -Version 5.1
<#
.SYNOPSIS
  Sign the Tempo CEP panel into a distributable .zxp.
.DESCRIPTION
  ZXPSignCmd comes from Adobe-CEP/CEP-Resources (Tools/ZXPSignCmd):
  https://github.com/Adobe-CEP/CEP-Resources
  Guide: https://github.com/Adobe-CEP/Getting-Started-guides/tree/master/Package%20Distribute%20Install
  Flow: self-signed cert for dev (ZXPSignCmd -selfSignedCert) or a real
  code-signing certificate for Exchange; sign with a timestamp server so
  expiry does not brick installed panels; verify; list via Adobe Developer
  Distribution (https://developer.adobe.com/developer-distribution/).
  CEP checks the certificate EVERY launch: repackage BEFORE expiry.
.EXAMPLE
  .\packaging\zxp-sign.ps1 -Cert .\cert.p12 -Password $env:CERT_PASS
#>
param(
  [string]$Cert = ".\cert.p12",
  [string]$Password = $env:CERT_PASS,
  [string]$Timestamp = "http://timestamp.digicert.com"
)
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$ver = (Select-String -Pattern 'ExtensionBundleVersion="([^"]+)"' `
  -Path (Join-Path $root "panel\CSXS\manifest.xml")).Matches[0].Groups[1].Value
$out = Join-Path $root "dist\tempo-panel-$ver.zxp"
New-Item -ItemType Directory -Path (Join-Path $root "dist") -Force | Out-Null
& ZXPSignCmd -sign (Join-Path $root "panel") $out $Cert $Password -tsa $Timestamp
& ZXPSignCmd -verify $out
Write-Output "signed: $out"
