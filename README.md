# Chaitra Builders & Developers — WhatsApp Booking Confirmation Sender

A local web application that lets staff fill in customer booking details via a web form and automatically send a formatted WhatsApp message using Playwright + WhatsApp Web. Fully free — no third-party APIs required.

---

## Features

- **Professional branded form** with CBD maroon/gold color scheme and logo
- **Live message preview** updates as you type
- **Auto-send via WhatsApp Web** using Playwright browser automation
- **Excel session logging** — each session creates a timestamped `.xlsx` file in `logs/`
- **Floating log notification** shows current log file and record count
- **Calendar date pickers** with Today button on all date fields
- **Session management** — End Session (shutdown) and Start Session (restart polling)
- **Copy to clipboard** for manual pasting

---

## Prerequisites

- Python 3.9+
- Google Chrome / Chromium installed on your system

---

## Setup Instructions

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright browser

```bash
playwright install chromium
```

### 3. First-time WhatsApp login (QR code scan)

Run the sender script directly — a browser window will open with WhatsApp Web:

```bash
python whatsapp_sender.py
```

- Scan the QR code with your phone's WhatsApp app.
- Once logged in, the session is saved to the `whatsapp_session/` folder.
- You only need to do this once. Future runs will reuse the saved session.

### 4. Start the backend server

```bash
python api.py
```

The API server will start on `http://localhost:8000`.

### 5. Open the web form

Open `form.html` in your browser (just double-click it or drag it into a browser tab).

- A green status dot at the top confirms the backend is online.
- Fill in the booking details → click **Send via WhatsApp** → done!

---

## Usage

1. Fill in all required booking fields in the form.
2. The **Message Preview** box at the bottom updates live as you type.
3. Click **Send via WhatsApp** to send the message automatically.
4. Or click **Copy Message** to copy the formatted text to your clipboard.
5. Click **End Session** to shut down the backend and save the log.
6. Click **Start Session** to restart (requires running `python api.py` again).

---

## Project Structure

```
chaitra-whatsapp-sender/
├── whatsapp_sender.py     # Core Playwright automation logic
├── api.py                 # FastAPI backend with Excel logging
├── form.html              # Web form (opened in browser)
├── cbd-logo.jpg           # CBD company logo
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── .gitignore             # Git ignore rules
├── whatsapp_session/      # Auto-created: saves WhatsApp login session
└── logs/                  # Auto-created: per-session Excel log files
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/send` | POST | Send booking confirmation via WhatsApp |
| `/log-info` | GET | Get current log file name and record count |
| `/shutdown` | POST | Shut down the backend server |

---

## Important Notes

- **`whatsapp_session/` folder** keeps your WhatsApp Web login session. Do not delete it, or you will need to scan the QR code again.
- **`logs/` folder** contains per-session Excel files named with the session start timestamp (e.g., `06-04-2026_02-30-15_PM.xlsx`).
- **This tool is designed for low-volume use** — sending individual booking confirmations, not bulk messaging.
- Phone numbers must be 10 digits (Indian numbers only, +91 prefix is added automatically).

---

## Troubleshooting

| Issue                          | Solution                                                             |
| ------------------------------ | -------------------------------------------------------------------- |
| Backend status shows "offline" | Make sure `python api.py` is running                                 |
| QR code appears every time     | The `whatsapp_session/` folder may have been deleted — scan again    |
| Message not sending            | Check that the phone number is valid and the contact is on WhatsApp  |
| Timeout error                  | WhatsApp Web may be slow to load — try again, ensure stable internet |
