# 0001 — AE UXP watch

**Status:** watching. **Date:** 2026-09-21.

## Context

Premiere Pro 25.6 (Nov 2025) superseded CEP with UXP: dual-support for ~1 calendar year, then CEP removal
(`Adobe-CEP/Samples PProPanel ReadMe`). After Effects has no such announcement as of 2026-09;
the CEP 12 Cookbook still lists `AEFT 25.0`, and the reference scaffold remains
`Adobe-CEP/Samples/tree/master/AfterEffectsPanel`.

## Decision

Ship Tempo as a CEP panel (`AEFT`, CEP 9–12 range pinned to smoke-tested versions only).
Do not copy version ranges from random repos; verify against the CEP Cookbook host/version matrix.

## Revisit when

Adobe announces AE UXP extensibility (developer.adobe.com or CEP-Resources `UXP-Migration-Guide`).
Then: spike a UXP panel behind a decision log entry, keep ExtendScript logic portable, re-evaluate §2.1.
