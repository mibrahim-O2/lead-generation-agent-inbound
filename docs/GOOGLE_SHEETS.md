# Google Sheets live demo

This optional feature makes a Google Sheet fill up row by row while the agent
processes leads. It is meant for demos and screen recordings with dummy data.

It is off by default. The normal install, the tests and CI never contact Google.

> **Never paste the service account key into a chat, an email, a screenshot or a
> commit.** It is a password for your Google project. It lives only in the
> `secrets/` folder on your machine, which is git-ignored.

## What you get

- A **Leads** tab: one row is added the moment each lead finishes.
- An **Inbox** tab (optional): type an enquiry into it and the agent picks it up.
- The agent still only drafts. Nothing is emailed or sent to anyone.

## Before you start

- A Google account.
- This repo installed (`make install`).
- About 15 minutes.

The Google Cloud Console changes its menus from time to time, so a button may
have a slightly different name or place than described here.

## Step 1 - Create a Google Cloud project

1. Open https://console.cloud.google.com/ and sign in.
2. Click the project picker at the top of the page, then **New Project**.
3. Give it any name, for example `lead-agent-demo`, and click **Create**.
4. Make sure the new project is selected in the project picker.

## Step 2 - Enable the Google Sheets API

1. In the menu, open **APIs & Services**, then **Library**.
2. Search for **Google Sheets API**, open it and click **Enable**.

You do **not** need the Google Drive API. This project opens the sheet by its id
and asks only for Sheets access.

## Step 3 - Create a service account

A service account is a robot user that the agent logs in as.

1. Open **APIs & Services**, then **Credentials**.
2. Click **Create Credentials**, then **Service account**.
3. Give it a name, for example `lead-agent`, and click **Create and continue**.
4. Skip the optional role and access steps and click **Done**.
5. In the list of service accounts, note its email address. It looks like
   `lead-agent@your-project.iam.gserviceaccount.com`. You need it in step 6.

## Step 4 - Create and download a JSON key

1. Click the service account you just created.
2. Open the **Keys** tab, click **Add key**, then **Create new key**.
3. Choose **JSON** and click **Create**. A `.json` file is downloaded.

## Step 5 - Put the key in `secrets/service-account.json`

`secrets/service-account.json` is the default location, so if your key is already
there you can skip this step.

From the repo folder, in the WSL terminal (adjust the download path and file name
to yours):

```bash
mkdir -p secrets
```

```bash
mv /mnt/c/Users/YOUR_WINDOWS_USER/Downloads/your-key-file.json secrets/service-account.json
```

Check that git ignores it. This must print the path back:

```bash
git check-ignore secrets/service-account.json
```

If it prints nothing, stop and do not commit anything.

## Step 6 - Create the sheet and share it

1. Create a new Google Sheet at https://sheets.google.com/.
2. Rename the first tab to **Leads** (double-click the tab name at the bottom).
3. Add a second tab and name it **Inbox**.
4. Leave both tabs empty. The agent writes the header rows itself.
5. Click **Share**, paste the service account email from step 3, choose
   **Editor**, and click **Send**.

The header rows the agent creates:

| Tab | Columns |
| --- | --- |
| Leads | Received At, Lead ID, Name, Channel, Message, Intent, Score, Hot, Route, Status, Missing Info, Handover Reason, Draft Reply, Run ID |
| Inbox | Received At, Name, Email, Phone, Message, Processed |

On an empty Leads tab the agent also freezes the header row and adds a dropdown
on **Status** (pending_approval, approved, rejected, needs_human, nurture,
discarded).

## Step 7 - Fill in `.env`

Find the sheet id in the sheet's address. It is the long part between `/d/` and
`/edit`:

```
https://docs.google.com/spreadsheets/d/THIS_PART_IS_THE_ID/edit
```

Open `.env` and set:

| Variable | Value |
| --- | --- |
| `SHEETS_ENABLED` | `1` |
| `GOOGLE_SHEET_ID` | the id from the address |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `secrets/service-account.json` (the default) |
| `SHEET_LEADS_TAB` | `Leads` (the default) |
| `SHEET_INBOX_TAB` | `Inbox` (the default) |

`example.env` describes each of them.

## Step 8 - Install the Google library

```bash
pip install -e ".[sheets]"
```

## Step 9 - Run the demo

Open the sheet in your browser next to the terminal, then:

```bash
make demo-sheet
```

It prints the model and the estimated cost first, then processes the five sample
leads one at a time. A new row appears in the Leads tab after each one.

- With `LEADGEN_MOCK_LLM=1`, or with no API key, it uses the built-in mock model
  and costs nothing.
- With a key and `LEADGEN_MOCK_LLM=0` it uses the real model and costs tokens.
- Change the pause between leads with `make demo-sheet DELAY=5`.

## Typing leads into the Inbox tab

Type a row into the **Inbox** tab: at least the **Message** column (column E),
and ideally Name, Email and Phone. Leave **Processed** (column F) empty.

The columns must be in this order: Received At, Name, Email, Phone, Message,
Processed. If the tab is completely empty, run `python -m leadgen --source sheet`
once first and the agent writes that header row for you.

Process the new rows once:

```bash
python -m leadgen --source sheet
```

Or keep watching and process rows as you type them (stop with Ctrl+C):

```bash
python -m leadgen --source sheet --watch --interval 10
```

Each processed row gets a note in its **Processed** column, so it is never handled
twice. The watch stops by itself when `MAX_LEADS_PER_RUN` or `MAX_TOKENS_PER_RUN`
is reached.

`--source sheet` needs the real model (`LEADGEN_MOCK_LLM=0`) or, to use the mock
on purpose, `SHEETS_ALLOW_MOCK=1` in `.env`.

## Safety

- `--dry-run` never writes to the sheet. It may read the Inbox tab.
- In mock mode the sheet is not touched at all unless `SHEETS_ALLOW_MOCK=1` is
  set. `make demo-sheet` sets it for that one command.
- Everything is written as plain text, so a message starting with `=` cannot run
  as a formula.
- If Google fails, the lead is still saved locally under `data/runtime/`, the
  error says what to fix, and the run continues. After three failures in a row,
  sheet updates pause for the rest of that run.
- Use dummy data only. Anyone the sheet is shared with can read every row.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `Google Sheets support is not installed` | Run `pip install -e ".[sheets]"`. |
| `Service account key not found at ...` | Put the key at `secrets/service-account.json` or set `GOOGLE_SERVICE_ACCOUNT_FILE`. |
| `... is not a valid service account JSON key` | The file is not the key you downloaded. Create a new JSON key (step 4). |
| `Share the sheet with ...@...iam.gserviceaccount.com as Editor` (a 403 error) | The sheet is not shared with the service account. Do step 6.5 again and choose Editor. |
| `Enable the Google Sheets API ...` (a 403 error) | The API is not enabled in the project that owns the service account. Do step 2. |
| `GOOGLE_SHEET_ID is wrong` (a 404 error) | Copy the id again from the address bar, without `/edit` or anything after it. |
| `The sheet has no tab named "Leads"` | Rename the tab, or set `SHEET_LEADS_TAB` / `SHEET_INBOX_TAB` to the exact name. |
| `SHEETS_ENABLED=1 but GOOGLE_SHEET_ID is empty` | Set `GOOGLE_SHEET_ID` in `.env`. |
| `--source sheet is off in mock mode` | Set `LEADGEN_MOCK_LLM=0`, or `SHEETS_ALLOW_MOCK=1` to use the mock on purpose. |
| `Google's request quota was hit` | Wait a minute. Use a larger `--interval` or `DELAY`. |
| Rows appear but there is no dropdown or frozen header | The tab was not empty on first use. Clear the tab completely and run again. |
| Nothing appears in the sheet and there is no error | Check `SHEETS_ENABLED=1`, and that you did not pass `--dry-run`. |

## Turning it off

Set `SHEETS_ENABLED=0` in `.env`. To revoke access completely, delete the key in
the Google Cloud Console (service account, **Keys** tab) and remove the service
account from the sheet's **Share** list.
