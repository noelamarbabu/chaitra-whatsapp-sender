"""
FastAPI backend for Chaitra Builders & Developers WhatsApp Booking Confirmation Sender.
"""

import io
import json
import os
import signal
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from openpyxl import Workbook, load_workbook
import google.generativeai as genai
from groq import Groq
from whatsapp_sender import send_booking_confirmation, send_bulk_whatsapp_messages

APP_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(APP_DIR, ".env"))

# Google Gemini client
genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Groq client (fallback)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

app = FastAPI(title="CBD WhatsApp Sender")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


BULK_HEADLESS = env_bool("BULK_HEADLESS", False)
BULK_STEP_DELAY_SECONDS = max(env_float("BULK_STEP_DELAY_SECONDS", 10.0), 0.0)
BULK_SEND_TIMEOUT_MS = max(env_int("BULK_SEND_TIMEOUT_MS", 45000), 5000)
BULK_CLOSE_DELAY_MS = max(env_int("BULK_CLOSE_DELAY_MS", 3000), 0)

# Logs directory (next to this script)
LOG_DIR = os.path.join(APP_DIR, "logs")

# Session-specific Excel file — created once when the server starts
SESSION_START = datetime.now()
SESSION_LOG_FILE = os.path.join(
    LOG_DIR,
    SESSION_START.strftime("%d-%m-%Y_%I-%M-%S_%p") + ".xlsx",
)

LOG_COLUMNS = [
    "Timestamp", "Customer Name", "Booked Date", "Phone", "Mail ID",
    "Plot No", "Sqft", "Facing", "Actual Price", "Closing Price/Sqft",
    "Total Price", "Paid Amount", "Balance Amount", "Offer",
    "Reg Slot 1", "Reg Slot 2", "Balance Due Date", "Feedback", "Status",
]


def get_record_count() -> int:
    """Return the current number of records in the session log (0 if no file yet)."""
    if not os.path.exists(SESSION_LOG_FILE):
        return 0
    wb = load_workbook(SESSION_LOG_FILE)
    ws = wb.active
    return max(ws.max_row - 1, 0)  # subtract header


def log_to_excel(booking_data: dict, status: str) -> int:
    """Append a booking entry to the session's Excel log file. Returns record number."""
    os.makedirs(LOG_DIR, exist_ok=True)

    if os.path.exists(SESSION_LOG_FILE):
        wb = load_workbook(SESSION_LOG_FILE)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Booking Log"
        ws.append(LOG_COLUMNS)

    row = [
        datetime.now().strftime("%d/%m/%Y %I:%M:%S %p"),
        booking_data.get("customer_name", "-"),
        booking_data.get("booked_date", "-"),
        booking_data.get("phone", "-"),
        booking_data.get("mail_id", "-"),
        booking_data.get("plot_no", "-"),
        booking_data.get("sqft", "-"),
        booking_data.get("facing", "-"),
        booking_data.get("actual_price", "-"),
        booking_data.get("closing_price", "-"),
        booking_data.get("total_price", "-"),
        booking_data.get("paid_amount", "-"),
        booking_data.get("balance_amount", "-"),
        booking_data.get("offer", "-"),
        booking_data.get("reg_slot_1", ""),
        booking_data.get("reg_slot_2", ""),
        booking_data.get("balance_due_date", ""),
        booking_data.get("feedback", "-"),
        status,
    ]
    ws.append(row)
    wb.save(SESSION_LOG_FILE)
    return ws.max_row - 1  # record number (subtract header)

# Enable CORS for all origins (so form.html on file:// can call this)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Booking(BaseModel):
    customer_name: str
    booked_date: str
    phone: str
    mail_id: str = "-"
    plot_no: str
    sqft: str
    facing: str
    actual_price: str
    closing_price: str
    total_price: str
    paid_amount: str
    balance_amount: str
    offer: str = "-"
    reg_slot_1: str = ""
    reg_slot_2: str = ""
    balance_due_date: str = ""
    feedback: str = "-"
    custom_message: str = ""

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if len(v) != 10 or not v.isdigit():
            raise ValueError("Phone number must be exactly 10 digits")
        return v


class BulkSendRequest(BaseModel):
    bookings: list
    custom_messages: list = []


class AIEnhanceRequest(BaseModel):
    message: str
    instruction: str = ""


TEMPLATE_COLUMNS = [
    "Customer Name", "Booked Date", "Phone", "Mail ID",
    "Plot No", "Sqft", "Facing", "Actual Price", "Closing Price/Sqft",
    "Total Price", "Paid Amount", "Balance Amount", "Offer",
    "Reg Slot 1", "Reg Slot 2", "Balance Due Date", "Feedback",
]

TEMPLATE_FIELD_MAP = {
    "Customer Name": "customer_name",
    "Booked Date": "booked_date",
    "Phone": "phone",
    "Mail ID": "mail_id",
    "Plot No": "plot_no",
    "Sqft": "sqft",
    "Facing": "facing",
    "Actual Price": "actual_price",
    "Closing Price/Sqft": "closing_price",
    "Total Price": "total_price",
    "Paid Amount": "paid_amount",
    "Balance Amount": "balance_amount",
    "Offer": "offer",
    "Reg Slot 1": "reg_slot_1",
    "Reg Slot 2": "reg_slot_2",
    "Balance Due Date": "balance_due_date",
    "Feedback": "feedback",
}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def serve_form():
    """Serve the booking form HTML page."""
    return FileResponse(os.path.join(APP_DIR, "form.html"), media_type="text/html")


@app.get("/cbd-logo.jpg")
async def serve_logo():
    """Serve the CBD logo image."""
    return FileResponse(os.path.join(APP_DIR, "cbd-logo.jpg"), media_type="image/jpeg")


@app.post("/send")
async def send(booking: Booking):
    data = booking.model_dump()
    custom_msg = data.pop("custom_message", "")
    try:
        await send_booking_confirmation(data, custom_message=custom_msg)
        record_num = log_to_excel(data, "SENT")
        log_filename = os.path.basename(SESSION_LOG_FILE)
        return {
            "status": "success",
            "message": f"Message sent to {booking.phone}",
            "log_file": log_filename,
            "record_number": record_num,
        }
    except Exception as e:
        log_to_excel(data, f"FAILED: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/log-info")
async def log_info():
    """Return current log file name and record count."""
    return {
        "log_file": os.path.basename(SESSION_LOG_FILE),
        "record_count": get_record_count(),
    }


@app.get("/download-template")
async def download_template():
    """Generate and return an Excel template for bulk sending."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Bulk Send Template"
    ws.append(TEMPLATE_COLUMNS)
    # Sample row
    ws.append([
        "SAMPLE NAME", "01/01/2025", "9876543210", "-",
        "1", "1200", "EAST", "750000", "500",
        "600000", "600000", "0", "-",
        "", "", "", "-",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bulk_send_template.xlsx"},
    )


@app.post("/upload-bulk")
async def upload_bulk(file: UploadFile = File(...)):
    """Parse an uploaded Excel file and return the data as JSON."""
    contents = await file.read()
    wb = load_workbook(io.BytesIO(contents))
    ws = wb.active

    rows = list(ws.iter_rows(min_row=1, values_only=True))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Excel file is empty or has only headers.")

    headers = [str(h).strip() if h else "" for h in rows[0]]

    bookings = []
    for row in rows[1:]:
        booking = {}
        for i, header in enumerate(headers):
            if header in TEMPLATE_FIELD_MAP and i < len(row):
                val = row[i]
                booking[TEMPLATE_FIELD_MAP[header]] = str(val).strip() if val is not None else ""
        if booking.get("phone"):
            bookings.append(booking)

    return {"bookings": bookings, "count": len(bookings)}


@app.post("/bulk-send")
async def bulk_send(request: BulkSendRequest):
    """Send WhatsApp messages in bulk. Streams SSE status updates."""
    bookings = request.bookings

    custom_messages = request.custom_messages or []

    async def event_stream():
        async for status in send_bulk_whatsapp_messages(
            bookings,
            custom_messages,
            headless=BULK_HEADLESS,
            step_delay_seconds=BULK_STEP_DELAY_SECONDS,
            send_timeout_ms=BULK_SEND_TIMEOUT_MS,
            close_delay_ms=BULK_CLOSE_DELAY_MS,
        ):
            if status.get("status") in ("delivered", "failed"):
                idx = status["index"] - 1
                if 0 <= idx < len(bookings):
                    log_status = (
                        "SENT (BULK)" if status["status"] == "delivered"
                        else f"FAILED (BULK): {status.get('error', '')}"
                    )
                    log_to_excel(bookings[idx], log_status)
            yield f"data: {json.dumps(status)}\n\n"
        yield f"data: {json.dumps({'status': 'complete'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _enhance_with_gemini(system_prompt: str, user_prompt: str) -> str:
    """Call Google Gemini to enhance the message."""
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=system_prompt,
    )
    resp = model.generate_content(
        user_prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=1500,
        ),
    )
    return resp.text.strip()


def _enhance_with_groq(system_prompt: str, user_prompt: str) -> str:
    """Call Groq to enhance the message."""
    resp = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=1500,
    )
    return resp.choices[0].message.content.strip()


@app.post("/ai-enhance")
async def ai_enhance(request: AIEnhanceRequest):
    """Enhance message using Gemini (primary) with Groq fallback."""
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=500, detail="No AI API key configured.")

    instruction = request.instruction.strip() if request.instruction else ""
    if not instruction:
        instruction = "Make this message more professional and warm while keeping all the booking details intact."

    system_prompt = (
        "You are a message editor for Chaitra Builders & Developers, a real estate company. "
        "You will receive a WhatsApp booking confirmation message. Your task is to enhance or "
        "rephrase it based on the user's instruction. Rules:\n"
        "1. Keep ALL booking details (names, numbers, dates, amounts) exactly the same — do not change any data.\n"
        "2. Keep the message suitable for WhatsApp (plain text, use * for bold).\n"
        "3. Keep the WhatsApp channel link and the REGARDS signature at the end.\n"
        "4. Return ONLY the enhanced message text, nothing else — no explanations."
    )

    user_prompt = f"Instruction: {instruction}\n\nOriginal message:\n{request.message}"
    provider = "gemini"

    # Try Gemini first, fall back to Groq
    try:
        if os.getenv("GEMINI_API_KEY"):
            enhanced = _enhance_with_gemini(system_prompt, user_prompt)
        else:
            raise Exception("No Gemini key, skipping to Groq")
    except Exception as gemini_err:
        if not os.getenv("GROQ_API_KEY"):
            raise HTTPException(status_code=500, detail=f"Gemini error: {str(gemini_err)}")
        try:
            provider = "groq"
            enhanced = _enhance_with_groq(system_prompt, user_prompt)
        except Exception as groq_err:
            raise HTTPException(status_code=500, detail=f"Both LLMs failed — Gemini: {str(gemini_err)} | Groq: {str(groq_err)}")

    return {"enhanced_message": enhanced, "provider": provider}


@app.post("/shutdown")
async def shutdown():
    """Gracefully shut down the server."""
    total = get_record_count()
    log_filename = os.path.basename(SESSION_LOG_FILE)
    os.kill(os.getpid(), signal.SIGTERM)
    return {
        "status": "shutting_down",
        "log_file": log_filename,
        "total_records": total,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
