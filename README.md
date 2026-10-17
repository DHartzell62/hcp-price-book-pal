# HCP Price Book Pal v1.4.1

A free tool for Housecall Pro users, from Dave Hartzell, Hartzell's Heat & Air, Kingfisher, Oklahoma.
Questions, or anything this tool does not do: email dave@hartzellsheatair.com.

It downloads your Housecall Pro price book (services and materials) to a spreadsheet, cleans up and rewrites
the descriptions, reads your supplier's price sheets, adds services you are missing, and sends your approved
changes back into HCP, with a backup and an undo for everything.

## Download
Go to **Releases** on the right side of this page and download the newest version:
- **HCP_Price_Book_Pal_..._Windows_NoPython.zip**: easiest. Unzip it to a folder you can write to (your Desktop or Documents, not Program Files) and double-click `start.bat`.
- **HCP_Price_Book_Pal_..._Python.zip**: smaller, for computers that already have Python. Install Python from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), unzip, and double-click `start.bat`.

**Windows will warn you the first time** ("Windows protected your PC") because the program is new and not signed yet. Click **More info**, then **Run anyway**.

Then follow the menu top to bottom. Every step shows a tip box first.

## What it does
- **Revamp what you have:** clean up descriptions, take better names and descriptions from the built-in library of 200+ HVAC, plumbing and electrical services, or have your own ChatGPT or Claude rewrite them. A name is only changed when the new one means exactly the same job.
- **Build what is missing:** see common services your price book may not have yet (only for the trades you already do), with descriptions ready to use. Put in your own price and the tool adds them, with online booking OFF until you turn it on. Each add can be removed again.
- **Feed supplier prices (the ingestion inbox):** drop your supplier's price sheet (Excel, CSV or text PDF) in the `inbox` folder. The tool matches it to your parts by part number and proposes new costs, plus new prices that keep your current markup. Anything unusual is flagged and needs YES typed out. Scanned PDF quotes cannot be read: export them as Excel or CSV.

## Your login stays yours
The tool opens HCP's own login page in a browser and you type your password there. The login is kept on your computer, outside the tool folder (in your Windows user folder under AppData\Local\HCPPriceBookPal), so sharing or zipping the tool folder never shares your login. It is sent only to Housecall Pro. Use "Log out" in the menu to delete it. Your price book never leaves your computer, except for the item names and descriptions you choose to paste into your own AI chat (never prices or costs).

## Safety
- Every download saves a permanent, read-only copy of your whole price book first. "Put EVERYTHING back" restores it.
- Nothing goes to HCP until you pick "Send my changes", see the preview, and type YES. What you send is exactly what the preview showed.
- Editing writes only the name, description, price and cost of rows you changed. The only steps that create or delete are "Add the missing services I priced" and "Remove services I added", and they only touch services in the "Added by Price Book Pal" category.
- If something changed in HCP since your download, that row is skipped, not overwritten.
- Every item is backed up before it changes (`backups` folder) and the whole item is read back after. "Undo one push" reverses a push.
- Prices that jump more than 10 times or drop more than 90%, negative prices and spreadsheet damage from Excel are refused.

## More tools for your shop
I run my own HVAC company on tools I built for it. If you want any of these set up for your shop, email me at dave@hartzellsheatair.com. These are custom setups, not part of this free download.

**More for Housecall Pro**
- Call checker: missed calls and which calls booked, from your HCP call recordings
- Money truth: invoices that show open but were paid, and real profit per job
- Maintenance plan renewal audit: members who are due and never got a reminder
- Duplicate customer finder
- Lost estimate report: why estimates were declined and which options customers pick
- Supplier price updates and special pricing loaded into your price book
- Notifications: new leads, unpaid invoices and other HCP events sent where you want them

**AI for your business**
- A custom AI chat for your website, trained on your own prices and services
- AI phone answering that picks up, captures the caller and the job, and hands it to your office
- AI-written descriptions, estimates and follow-ups in your own voice

**Ads and marketing**
- Google Ads campaigns built and watched by AI, with call and booking tracking
- Facebook and Instagram ads and posting, Google Business Profile posts, YouTube shorts
- Website pages, local SEO and review requests

**Accounting and reporting**
- QuickBooks and Housecall Pro matched up, with weekly profit and loss
- A daily dashboard: revenue, jobs, unpaid invoices, technician numbers, maintenance plans

## Fine print
This uses the same private connection HCP's website uses. It is not made, supported or approved by Housecall Pro, and HCP can change their site and break it. Use it at your own risk, try a few items first, and check your price book in HCP after. The first run asks you to agree that you are responsible for your account and your prices.

## License
Free to use and improve for your own business under the PolyForm Noncommercial License 1.0.0 (see LICENSE.md). You may not sell it or offer it as a paid product or service. For anything else, email Dave Hartzell, dave@hartzellsheatair.com.
