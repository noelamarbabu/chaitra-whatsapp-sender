"""
FastAPI backend for Chaitra Builders & Developers WhatsApp Booking Confirmation Sender.
"""

import os
import signal
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from openpyxl import Workbook, load_workbook
from whatsapp_sender import send_booking_confirmation

APP_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="CBD WhatsApp Sender")

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

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if len(v) != 10 or not v.isdigit():
            raise ValueError("Phone number must be exactly 10 digits")
        return v


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
    try:
        await send_booking_confirmation(data)
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
