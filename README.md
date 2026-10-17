# HCP Price Book Pal v1.0 "Basic"

Free from Dave Hartzell, Hartzell's Heat & Air, Kingfisher, Oklahoma. Questions or anything this tool does not do: call 405-375-4822.

It downloads your Housecall Pro price book (services and materials) to a spreadsheet, cleans up and rewrites the descriptions (with ChatGPT or Claude if you want), and pushes your edits back into HCP.

## Start
1. Install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
2. Double-click `start.bat`. The first run installs what it needs.
3. Follow the menu top to bottom. Each step shows a tip box first.

## Your login stays yours
Step 1 opens HCP's own login page in a browser. You type your password there. The tool keeps the login on your computer (the `hcp_profile` folder) and sends it nowhere else. Delete that folder to log out.

## Safety
- Nothing goes to HCP until step 7, and step 7 asks you to type YES.
- Only the name, description, price and cost of rows you changed are written. New rows are ignored: this tool edits, it never creates or deletes.
- If something changed in HCP since your download, that row is skipped, not overwritten.
- Every item is backed up before it changes (`backups` folder) and read back after. Step 8 undoes a push.
- When the AI rewrites descriptions, any row where it changed a name or a price is refused.

## Fine print
This uses the same private connection HCP's website uses. It is not made or supported by Housecall Pro, and HCP can change their site and break it. Use it at your own risk, try a few items first, and check your price book in HCP after.
