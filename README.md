# Chaitra Builders & Developers — WhatsApp Booking Confirmation Sender

A local web application that lets staff fill in customer booking details via a web form and automatically send a formatted WhatsApp message using Playwright + WhatsApp Web. Supports both individual and **bulk sending** via Excel upload, with **AI-powered message enhancement** via Google Gemini (with Groq fallback). Fully free WhatsApp automation — no third-party messaging APIs required.

---

## Prerequisites

- Python 3.9+
- Google Chrome / Chromium installed on your system
- Google Gemini API key and/or Groq API key (for AI message enhancement)

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

### 3. Configure AI keys (for AI enhancement)

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your-gemini-key-here
GEMINI_MODEL=gemini-2.0-flash

GROQ_API_KEY=your-groq-key-here
GROQ_MODEL=llama-3.3-70b-versatile

# Bulk Playwright behavior (optional)
BULK_HEADLESS=false
BULK_STEP_DELAY_SECONDS=10
BULK_SEND_TIMEOUT_MS=90000
BULK_CLOSE_DELAY_MS=3000
```

The `.env` file is gitignored. Gemini is the primary provider; Groq is used automatically as a fallback when Gemini quota is exhausted.

### 4. First-time WhatsApp login (QR code scan)

Run the sender script directly — a browser window will open with WhatsApp Web:

```bash
python whatsapp_sender.py
```

- Scan the QR code with your phone's WhatsApp app.
- Once logged in, the session is saved to the `whatsapp_session/` folder.
- You only need to do this once. Future runs will reuse the saved session.
- **Note:** The first run will also attempt to send a test message with sample data. You can stop it after scanning the QR if you just want to set up the session.

### 5. Start the backend server

```bash
python api.py
```

The API server will start on `http://localhost:8000`.

### 6. Open the web form

Open `form.html` in your browser (just double-click it or drag it into a browser tab).

- A green status dot at the top confirms the backend is online.
- Fill in the booking details → click **Send via WhatsApp** → done!

---

## Usage

### Individual Send

1. Fill in all required booking fields in the form.
2. The **Message Preview** box at the bottom updates live as you type.
3. Click **Send via WhatsApp** to send the message automatically.
4. Or click **Copy Message** to copy the formatted text to your clipboard.

### AI Message Enhancement

1. Fill in the booking form fields as usual.
2. In the **✨ AI Message Enhance** section below the preview:
   - Type a custom instruction (e.g., "Make it more friendly") **or** click a preset chip.
   - Preset options: **Friendly**, **Professional**, **Festive**, **Payment Urgency**, **Concise**, **Telugu**.
3. Click **✨ Enhance** — the AI will rephrase the message while keeping all booking data intact.
4. Review the AI-enhanced version and click **✅ Use This Message** to apply it.
5. The enhanced message will be sent when you click **Send via WhatsApp** or **Copy Message**.
6. Click **✖ Discard** to go back to the original template message.
7. Editing any form field resets back to the original message.

### Bulk Send

1. Click **📥 Download Template** to download the Excel template.
2. Fill in the template with customer booking details (one row per customer).
3. Select the filled Excel file and click **📤 Upload Excel** — a preview table will appear.
4. Click **🚀 Bulk Send** to start sending messages to all contacts.
5. A **Status Dialog** opens showing real-time progress for each message:
   - ⏳ **Preparing** — Building the message
   - 📤 **Sending** — Navigating to WhatsApp and sending
   - ✅ **Delivered (Number) - Successfully** — Message sent
   - ❌ **Failed** — Error occurred (details shown)
6. Bulk sending runs in **headed sequential mode by default** (one visible browser window reused for all rows).
7. All sent/failed messages are logged to the session Excel log file.

---

## Project Structure

```
chaitra-whatsapp-sender/
├── whatsapp_sender.py     # Core Playwright automation logic (single + bulk)
├── api.py                 # FastAPI backend (form serving, send, bulk, AI endpoints)
├── form.html              # Web form (individual + bulk send + AI enhance UI)
├── requirements.txt       # Python dependencies
├── .env                   # AI API keys — Gemini + Groq (gitignored)
├── README.md              # This file
├── .gitignore             # Git ignore rules
├── logs/                  # Auto-created: session Excel logs
└── whatsapp_session/      # Auto-created: saves WhatsApp login session
```

---

## API Endpoints

| Method | Endpoint             | Description                                     |
| ------ | -------------------- | ----------------------------------------------- |
| GET    | `/`                  | Serve the booking form HTML                     |
| GET    | `/health`            | Health check                                    |
| POST   | `/send`              | Send a single WhatsApp message                  |
| POST   | `/ai-enhance`        | Enhance message (Gemini primary, Groq fallback) |
| GET    | `/download-template` | Download the bulk send Excel template           |
| POST   | `/upload-bulk`       | Upload a filled Excel file, returns parsed data |
| POST   | `/bulk-send`         | Send messages in bulk (SSE status stream)       |
| GET    | `/log-info`          | Current log file name and record count          |
| POST   | `/shutdown`          | Gracefully shut down the server                 |

---

## Important Notes

- **`whatsapp_session/` folder** keeps your WhatsApp Web login session. Do not delete it, or you will need to scan the QR code again.
- **Bulk browser mode:** Individual sends open a visible browser. Bulk sends are headed by default and run sequentially in a single reused browser context.
- Set `BULK_HEADLESS=true` in `.env` if you explicitly want hidden/background browser execution.
- **Bulk sending requires an active WhatsApp session** — make sure you've completed the first-time QR code scan before using bulk send.
- **AI API keys** are stored in `.env` (gitignored). At least one of Gemini or Groq is required for AI enhance.
- Phone numbers must be 10 digits (Indian numbers only, +91 prefix is added automatically).
- The Excel template includes a sample row — delete it before uploading your real data.

---

## Troubleshooting

| Issue                          | Solution                                                             |
| ------------------------------ | -------------------------------------------------------------------- |
| Backend status shows "offline" | Make sure `python api.py` is running                                 |
| QR code appears every time     | The `whatsapp_session/` folder may have been deleted — scan again    |
| Message not sending            | Check that the phone number is valid and the contact is on WhatsApp  |
| Timeout error                  | WhatsApp Web may be slow to load — try again, ensure stable internet |
| Bulk upload fails              | Ensure the Excel file matches the template format (column headers)   |
| Bulk send shows all failed     | Verify WhatsApp session is active (run `python whatsapp_sender.py`)  |
| AI enhance not working         | Check `GEMINI_API_KEY` and/or `GROQ_API_KEY` in `.env`               |
