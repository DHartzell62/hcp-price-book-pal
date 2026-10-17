# Versions

## v1.4.1 (2026-10-17)
- Menu option E opens your email with a message to Dave Hartzell (subject: HCP Price Book Pal). Contact is email only.
- The Hartzell's Heat & Air logo is the program's icon.
- Fixed: two downloads in the same second could collide on the original-backup folder (this was the rare test failure).

## v1.4 (2026-10-17) - supplier price ingestion, three trades, installer
- Ingestion inbox: drop a supplier price sheet (Excel, CSV, or text PDF) in the inbox folder; parts match by part number.
- Proposals keep your current markup; each Excel tab is read with its own headings; List/MSRP/retail columns are never used as cost.
- Flags: big jumps (box vs each), part numbers shared by several items, duplicate sheet lines, short part numbers, PDF-sourced rows. A flagged row needs YES typed out.
- Cost now has the same 10x / 90% guard as price. File size, unzipped size, row and page limits on supplier files.
- Plumbing (62) and electrical (62) libraries, 212 entries in all; the missing list shows only trades your price book already has.
- start.bat reinstalls whenever the package list changes, so upgrades get new packages. All packages pinned.
- Optional no-Python Windows build (build_exe.py). 56 + 8 + 3 offline tests.
- Scanned (picture) PDF quotes cannot be read; export them as Excel or CSV.

## v1.3.1 (2026-10-17) - second security review
- Any failure after a create (bad reply, timeout, expired login) now cleans up; clean-up looks twice and confirms.
- A preview only unlocks a send when it finishes cleanly, and one preview approves one send.
- A real apostrophe at the start of a name survives the spreadsheet round trip.
- An expired login gives a plain message instead of an error dump. 49 offline tests.

## v1.3 "Basic" (2026-10-17) - security release
- Creates are never retried; if one fails, anything HCP made is found and removed, and every delete is confirmed.
- What you preview is exactly what is sent: an edit saved after the preview is refused.
- The HCP login is kept outside the tool folder (AppData\Local\HCPPriceBookPal) and never follows a redirect; new "Log out" step.
- Excel formula injection blocked in every spreadsheet the tool writes.
- Negative prices and 10x price jumps refused; every item id checked; paging capped; printed names cleaned.
- Remove only touches items from that add run, still in the tool's category and unchanged.
- Exact package versions pinned. 46 offline tests.

## v1.2 "Basic" (2026-10-17)
- Add the missing services you priced: one category "Added by Price Book Pal", preview first, typed YES.
- New services are created with online booking OFF and checked (HCP turns booking on by default for new services).
- Remove services an add run created. Live add and remove tested on a real account.
- 37 offline tests.

## v1.1 "Basic" (2026-10-17)
- Built-in library of 88 upfront, customer-friendly HVAC and water heater service names and descriptions.
- Suggest: renames only when the new name means exactly the same job; fills only empty or very short descriptions. You mark Y in Excel, nothing else changes.
- Missing list: common services your price book may not have yet, with descriptions ready to use.
- 34 offline tests.

## v1.0 "Basic" (2026-10-17)
- Download services and materials to a spreadsheet; permanent read-only original backup on every download.
- Clean descriptions; paste-ready packs for ChatGPT, Claude or Gemini (names and descriptions only, never prices).
- Preview, send with typed YES, whole-item readback, undo one push, restore everything from an original.
- 30 offline tests against a fake HCP; one-item live test passed on a real account.

## Planned
- v2.0 "Auto": the user's own AI key rewrites descriptions automatically.
- v3.0 "Pro": vendor price sheets, markup formulas, new items, estimate templates. Email Dave Hartzell, dave@hartzellsheatair.com.
