"""\nWhatsApp Booking Confirmation Sender\nUses Playwright with persistent browser context to send messages via WhatsApp Web.\n"""

import asyncio
import os
from urllib.parse import quote
from playwright.async_api import async_playwright

# Path to store WhatsApp Web session data
SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_session")


def build_message(data: dict) -> str:
    """Build the formatted WhatsApp booking confirmation message."""

    # Default empty fields to "-"
    def val(key, default="-"):
        v = data.get(key, "")
        if v is None or str(v).strip() == "":
            return default
        return str(v).strip()

    customer_name = val("customer_name")
    booked_date = val("booked_date")
    phone = val("phone")
    mail_id = val("mail_id")
    plot_no = val("plot_no")
    sqft = val("sqft")
    facing = val("facing")
    actual_price = val("actual_price")
    closing_price = val("closing_price")
    total_price = val("total_price")
    paid_amount = val("paid_amount")
    balance_amount = val("balance_amount")
    offer = val("offer")
    reg_slot_1 = val("reg_slot_1", default="")
    reg_slot_2 = val("reg_slot_2", default="")
    balance_due_date = val("balance_due_date", default="")
    feedback = val("feedback")

    # Build registration slot line
    if reg_slot_1 and reg_slot_2:
        reg_line = f"{reg_slot_1} & {reg_slot_2}"
    elif reg_slot_1:
        reg_line = reg_slot_1
    else:
        reg_line = "-"

    # Build balance update line
    if balance_due_date:
        balance_update = (
            f"THIS IS TO INFORMING YOU REMAINING BALANCE AMOUNT SHOULD CLEAR "
            f"ON OR BEFORE {balance_due_date} TO PROCESS REGISTRATION WORKS."
        )
    else:
        balance_update = "-"

    message = (
        f"*WELCOME TO CBD FAMILY.*\n"
        f"THANK YOU FOR CHOOSING US.\n"
        f"BELOW ARE YOUR BOOKING DETAILS.\n"
        f"\n"
        f"CUSTOMER NAME :- {customer_name}\n"
        f"BOOKED DATE :- {booked_date}\n"
        f"CONTACT :- {phone}\n"
        f"MAIL ID :- {mail_id}\n"
        f"PLOT NO :- {plot_no}\n"
        f"SQFT :- {sqft}\n"
        f"FACING :- {facing}\n"
        f"ACTUAL PRICE :- \u20b9{actual_price}\n"
        f"CLOSING PRICE IN SQFT :- \u20b9{closing_price}/-\n"
        f"TOTAL PRICE :- \u20b9{total_price}\n"
        f"PAID AMOUNT :- \u20b9{paid_amount}\n"
        f"BALANCE AMOUNT :- {balance_amount}\n"
        f"OFFER :- {offer}\n"
        f"REGISTRATION SLOT :- {reg_line}\n"
        f"BALANCE AMOUNT UPDATE :- {balance_update}\n"
        f"FEEDBACK :- {feedback}\n"
        f"\n"
        f"https://whatsapp.com/channel/0029Vax9QUa1CYoIwIGu6D2V\n"
        f"\n"
        f"REGARDS\n"
        f"CHAITRA BUILDERS AND DEVELOPERS"
    )

    return message


async def send_whatsapp_message(phone: str, message: str, headless: bool = False):
    """
    Send a WhatsApp message using Playwright with a persistent browser session.

    Args:
        phone: 10-digit phone number (without country code)
        message: The message text to send
        headless: Whether to run the browser in headless mode
    """
    # Ensure session directory exists
    os.makedirs(SESSION_DIR, exist_ok=True)

    encoded_message = quote(message)
    url = f"https://web.whatsapp.com/send?phone=91{phone}&text={encoded_message}"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=headless,
            args=["--no-sandbox"],
            locale="en-US",
        )

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)

            # Wait for the send button to appear (WhatsApp Web loaded and message ready)
            send_button = await page.wait_for_selector(
                '[data-testid="send-btn"]',
                timeout=90000,
                state="visible",
            )

            await send_button.click()

            # Wait for the message to be sent
            await page.wait_for_timeout(2000)

        except Exception as e:
            raise RuntimeError(
                f"Failed to send WhatsApp message: {str(e)}. "
                "Make sure WhatsApp Web is logged in and the phone number is valid."
            )
        finally:
            await context.close()


async def send_booking_confirmation(booking: dict, headless: bool = False):
    """
    Build and send a booking confirmation message via WhatsApp.

    Args:
        booking: Dictionary containing all booking fields
        headless: Whether to run the browser in headless mode
    """
    phone = booking.get("phone", "").strip()
    if not phone or len(phone) != 10 or not phone.isdigit():
        raise ValueError(f"Invalid phone number: '{phone}'. Must be exactly 10 digits.")

    message = build_message(booking)
    await send_whatsapp_message(phone, message, headless=headless)


# --- Standalone test ---
if __name__ == "__main__":
    sample_booking = {
        "customer_name": "BOGGARAPU YASHODHA",
        "booked_date": "18/10/2025",
        "phone": "6300636696",
        "mail_id": "-",
        "plot_no": "9 & 10",
        "sqft": "1200Sqft",
        "facing": "EAST",
        "actual_price": "750000",
        "closing_price": "500",
        "total_price": "600000",
        "paid_amount": "600000",
        "balance_amount": "0",
        "offer": "WITH REGISTRATION CLOSING PRICE HAS GIVEN OFFER.",
        "reg_slot_1": "13/04/2026",
        "reg_slot_2": "16/04/2026",
        "balance_due_date": "10/04/2026",
        "feedback": "-",
    }

    # Print the message for verification
    print("=== Message Preview ===")
    print(build_message(sample_booking))
    print("=======================")

    # Uncomment the line below to actually send via WhatsApp
    # asyncio.run(send_booking_confirmation(sample_booking))

    # To send and test:
    asyncio.run(send_booking_confirmation(sample_booking))
