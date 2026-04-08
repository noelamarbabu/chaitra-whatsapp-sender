"""
WhatsApp Booking Confirmation Sender
Uses Playwright with persistent browser context to send messages via WhatsApp Web.
"""

import asyncio
import logging
import os
import time
from urllib.parse import quote

from playwright.async_api import async_playwright

# Path to store WhatsApp Web session data
SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_session")

logger = logging.getLogger(__name__)

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--no-first-run",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-extensions",
    "--disable-default-apps",
    "--lang=en-US",
]

# Keep these ordered by confidence. WhatsApp occasionally changes attributes.
SEND_BUTTON_SELECTORS = [
    '[data-testid="send-btn"]',
    'button[aria-label="Send"]',
    'span[data-icon="send"]',
    'xpath=//button[@aria-label="Send"]',
    'xpath=//span[@data-icon="send"]/ancestor::button[1]',
]

INVALID_NUMBER_SELECTORS = [
    "text=Phone number shared via url is invalid",
    "text=phone number shared via url is invalid",
    "text=This phone number is not on WhatsApp",
    "text=This number is not on WhatsApp",
    "text=not on WhatsApp",
]

READINESS_SELECTORS = [
    '[data-testid="conversation-compose-box-input"]',
    '[contenteditable="true"][data-tab="10"]',
    'footer [contenteditable="true"]',
    '[data-testid="send-btn"]',
]

STALE_LOCK_FILES = [
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
    "lock",
    ".chrome-lock",
    os.path.join("Default", "LOCK"),
]


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


def cleanup_stale_session_files() -> None:
    """Remove stale lock files that can block persistent Chromium launches."""
    if not os.path.exists(SESSION_DIR):
        return

    for rel_path in STALE_LOCK_FILES:
        lock_path = os.path.join(SESSION_DIR, rel_path)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                logger.info("Removed stale lock file: %s", lock_path)
            except OSError as exc:
                logger.warning("Could not remove lock file %s: %s", lock_path, exc)


async def _wait_for_any_selector(page, selectors, timeout_ms, state="visible"):
    """Wait until any selector matches and return (element_handle, selector)."""
    per_selector_timeout = max(int(timeout_ms / max(len(selectors), 1)), 1000)
    last_error = None

    for selector in selectors:
        try:
            handle = await page.wait_for_selector(
                selector,
                timeout=per_selector_timeout,
                state=state,
            )
            if handle:
                return handle, selector
        except Exception as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise RuntimeError("No selector matched within timeout")


async def _click_send_with_fallback(page, timeout_ms):
    """Click send button with selector fallback and return selector used."""
    send_button, selector_used = await _wait_for_any_selector(
        page,
        SEND_BUTTON_SELECTORS,
        timeout_ms,
        state="visible",
    )
    await send_button.click()
    return selector_used


async def _detect_invalid_whatsapp_number(page):
    """Detect WhatsApp invalid-number UI messages and return a normalized label."""
    for selector in INVALID_NUMBER_SELECTORS:
        try:
            handle = await page.query_selector(selector)
            if handle:
                return "Check the number"
        except Exception:
            continue
    return None


async def _reset_page_for_next_number(context, page):
    """Close active page and open a fresh page to isolate row failures."""
    try:
        await page.close()
    except Exception:
        pass
    return await context.new_page()


async def _goto_with_guard(page, url: str, timeout_ms: int):
    """Guarded navigation so a hung navigation does not block the whole batch indefinitely."""
    await asyncio.wait_for(
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms),
        timeout=(timeout_ms / 1000.0) + 5,
    )


async def send_whatsapp_message(
    phone: str,
    message: str,
    headless: bool = False,
    send_timeout_ms: int = 90000,
):
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
        cleanup_stale_session_files()

        context = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=headless,
            args=CHROMIUM_ARGS,
            locale="en-US",
        )

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=send_timeout_ms)
            await _wait_for_any_selector(page, READINESS_SELECTORS, send_timeout_ms)
        except Exception as e:
            await context.close()
            raise RuntimeError(
                f"Failed to open WhatsApp Web: {str(e)}. "
                "Check your internet connection and try again."
            )

        # Navigation succeeded — WhatsApp Web opened. Consider this a success.
        # Try to click the send button (best-effort, don't fail if it doesn't work).
        try:
            await _click_send_with_fallback(page, send_timeout_ms)
            await page.wait_for_timeout(2000)
        except Exception:
            pass  # User can send manually from the open browser

        await context.close()


async def send_booking_confirmation(booking: dict, headless: bool = False, custom_message: str = ""):
    """
    Build and send a booking confirmation message via WhatsApp.

    Args:
        booking: Dictionary containing all booking fields
        headless: Whether to run the browser in headless mode
        custom_message: Optional AI-enhanced message to send instead of the default
    """
    phone = booking.get("phone", "").strip()
    if not phone or len(phone) != 10 or not phone.isdigit():
        raise ValueError(f"Invalid phone number: '{phone}'. Must be exactly 10 digits.")

    message = custom_message.strip() if custom_message else build_message(booking)
    await send_whatsapp_message(phone, message, headless=headless)


async def send_bulk_whatsapp_messages(
    bookings: list,
    custom_messages=None,
    headless: bool = False,
    step_delay_seconds: float = 10.0,
    send_timeout_ms: int = 90000,
    close_delay_ms: int = 3000,
):
    """
    Send WhatsApp messages in bulk using a single persistent browser context (headed).
    Yields status dicts for each booking as an async generator.

    Args:
        bookings: List of booking dicts.
        custom_messages: Optional list of custom message strings (same length as bookings).
                         Empty string means use the default template.
    """
    os.makedirs(SESSION_DIR, exist_ok=True)
    total = len(bookings)

    async with async_playwright() as p:
        cleanup_stale_session_files()

        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=headless,
                args=CHROMIUM_ARGS,
                locale="en-US",
            )
        except Exception as exc:
            error_text = f"Browser launch failed: {exc}"
            logger.exception("Bulk launch failed")
            for idx, booking in enumerate(bookings):
                yield {
                    "index": idx + 1,
                    "total": total,
                    "phone": booking.get("phone", ""),
                    "customer_name": booking.get("customer_name", "Unknown"),
                    "status": "failed",
                    "step": "launch",
                    "error": error_text,
                }
            return

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            for idx, booking in enumerate(bookings):
                row_start = time.perf_counter()
                current_step = "prepare"
                phone = booking.get("phone", "").strip()
                customer_name = booking.get("customer_name", "Unknown")

                yield {
                    "index": idx + 1,
                    "total": total,
                    "phone": phone,
                    "customer_name": customer_name,
                    "status": "preparing",
                    "step": "validate",
                }

                if not phone or len(phone) != 10 or not phone.isdigit():
                    yield {
                        "index": idx + 1,
                        "total": total,
                        "phone": phone,
                        "customer_name": customer_name,
                        "status": "failed",
                        "step": "validate",
                        "error": f"Invalid phone number: {phone}",
                    }
                    continue

                # Use custom message if provided, otherwise build from template.
                custom = (
                    (custom_messages[idx] if custom_messages and idx < len(custom_messages) else "")
                    .strip()
                )
                message = custom if custom else build_message(booking)
                encoded_message = quote(message)
                url = f"https://web.whatsapp.com/send?phone=91{phone}&text={encoded_message}"

                yield {
                    "index": idx + 1,
                    "total": total,
                    "phone": phone,
                    "customer_name": customer_name,
                    "status": "sending",
                    "step": "navigate",
                }

                try:
                    current_step = "navigate"
                    await _goto_with_guard(page, url, send_timeout_ms)

                    yield {
                        "index": idx + 1,
                        "total": total,
                        "phone": phone,
                        "customer_name": customer_name,
                        "status": "sending",
                        "step": "ready-check",
                    }

                    invalid_marker = await _detect_invalid_whatsapp_number(page)
                    if invalid_marker:
                        page = await _reset_page_for_next_number(context, page)
                        yield {
                            "index": idx + 1,
                            "total": total,
                            "phone": phone,
                            "customer_name": customer_name,
                            "status": "failed",
                            "step": "validate-whatsapp-number",
                            "error_code": "check-number",
                            "error": invalid_marker,
                        }
                        continue

                    current_step = "ready-check"
                    await _wait_for_any_selector(page, READINESS_SELECTORS, send_timeout_ms)

                    invalid_marker = await _detect_invalid_whatsapp_number(page)
                    if invalid_marker:
                        page = await _reset_page_for_next_number(context, page)
                        yield {
                            "index": idx + 1,
                            "total": total,
                            "phone": phone,
                            "customer_name": customer_name,
                            "status": "failed",
                            "step": "validate-whatsapp-number",
                            "error_code": "check-number",
                            "error": invalid_marker,
                        }
                        continue

                    current_step = "wait-before-send"
                    yield {
                        "index": idx + 1,
                        "total": total,
                        "phone": phone,
                        "customer_name": customer_name,
                        "status": "sending",
                        "step": current_step,
                        "delay_seconds": step_delay_seconds,
                    }
                    await page.wait_for_timeout(int(step_delay_seconds * 1000))

                    invalid_marker = await _detect_invalid_whatsapp_number(page)
                    if invalid_marker:
                        page = await _reset_page_for_next_number(context, page)
                        yield {
                            "index": idx + 1,
                            "total": total,
                            "phone": phone,
                            "customer_name": customer_name,
                            "status": "failed",
                            "step": "validate-whatsapp-number",
                            "error_code": "check-number",
                            "error": invalid_marker,
                        }
                        continue

                    current_step = "click-send"
                    try:
                        selector_used = await _click_send_with_fallback(page, send_timeout_ms)
                    except Exception:
                        invalid_marker = await _detect_invalid_whatsapp_number(page)
                        if invalid_marker:
                            page = await _reset_page_for_next_number(context, page)
                            yield {
                                "index": idx + 1,
                                "total": total,
                                "phone": phone,
                                "customer_name": customer_name,
                                "status": "failed",
                                "step": "validate-whatsapp-number",
                                "error_code": "check-number",
                                "error": invalid_marker,
                            }
                            continue
                        raise
                    await page.wait_for_timeout(close_delay_ms)

                    elapsed_ms = int((time.perf_counter() - row_start) * 1000)
                    yield {
                        "index": idx + 1,
                        "total": total,
                        "phone": phone,
                        "customer_name": customer_name,
                        "status": "delivered",
                        "step": "delivered",
                        "selector": selector_used,
                        "elapsed_ms": elapsed_ms,
                    }
                except Exception as exc:
                    logger.exception("Bulk send failed at step %s for phone %s", current_step, phone)
                    page = await _reset_page_for_next_number(context, page)
                    yield {
                        "index": idx + 1,
                        "total": total,
                        "phone": phone,
                        "customer_name": customer_name,
                        "status": "failed",
                        "step": current_step,
                        "error": str(exc),
                    }
        finally:
            await context.close()


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
