"""\nFastAPI backend for Chaitra Builders & Developers WhatsApp Booking Confirmation Sender.\n"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from whatsapp_sender import send_booking_confirmation

app = FastAPI(title="CBD WhatsApp Sender")

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


@app.post("/send")
async def send(booking: Booking):
    try:
        await send_booking_confirmation(booking.model_dump())
        return {"status": "success", "message": f"Message sent to {booking.phone}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
