# API/frontend contract drift requires a live integration test, not eyeballing field names

**Date**: 2026-07-02

## Problem

Slices 003 (backend) and 005 (SPA) were built in parallel against the same documented
HTTP contract. Both sides individually passed their suites, yet the cycle-1 review
found the shapes had drifted: field names (`location` vs `current_location`,
`choice_id`/`free_text` vs `choice`), envelope differences, and endpoints the frontend
called that the backend never exposed (per-round combat routes that spec 007 later
deleted). Every drift had survived review because each side's tests mocked the *other*
side — the frontend's fixtures asserted the frontend's own assumptions, and the
backend's tests asserted the backend's.

**Eyeballing two documents (or two codebases) against each other does not catch
drift. Only a test that runs one side against the other does.**

## Solution

1. **Canonical shape, one owner** (ADR-017): the backend's response models are the
   contract; the frontend types mirror them field-for-field. Any change starts on the
   backend and propagates.
2. **A live-backend e2e suite** (`frontend/tests/e2e/live-play-loop.spec.ts`, T014):
   Playwright drives the real SPA against the real FastAPI app with
   `VITE_USE_MOCK=false` — the only configuration in which drift is physically
   observable.
3. **Contract assertions in backend tests**: response-model field sets are asserted
   (e.g. `"effects_applied" not in TurnResponse.model_fields`), so a shape change
   breaks a test on the owning side before the consumer ever sees it.

## Rule of thumb

If two components are developed against a shared contract document, schedule an
integration test that exercises the *pair* in the same slice that freezes the
contract — not in a later hardening slice. The cost of the drift grows with every
component built on top of the wrong assumption.
