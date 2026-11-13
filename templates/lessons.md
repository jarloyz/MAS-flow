# Lessons Learned

> Maintained by the `documenter`. **Active Rules are binding** for the roles they name and are audited by the `guard`.
> A cause seen 2+ times is promoted — to a **deterministic check** when a tool can detect it (card `CHECK-<n>`), to an Active Rule otherwise.
> Active Rules have a budget (`masflow.py check`): to add one beyond it, first merge, retire or graduate another.

## Active Rules
_Format: `- R<n> [roles: executor, guard] <one imperative, checkable sentence> (HU-XXX)`. Roles: any agent name, or `all`._

_(none yet)_

## Escapes
_Defects no gate caught (verify regressions, bugs found by the Human): `- <date> <test or symptom> — story HU-XXX — missed by: <gate> — why — action: <CHECK-n | R<n> | test group | none>`._

## Retired
_Rules removed from Active Rules: `- R<n> <rule> — retired <date>: <now enforced by check X | merged into R<m> | not seen in 10 stories>`._

## Log
_One line per rejection: `- <date> HU-XXX slice N — <gate>: <cause>`._
