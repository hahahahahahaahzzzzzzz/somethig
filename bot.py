"""
bot.py — Telegram Response Filter Bot (Pyrogram / Userbot)

Listens for .txt result files from ANY source (including other bots),
filters Charged & Insufficient cards, looks up BIN info via Juspay API,
and drops each card as a separate pinned message.

Usage:
    1. Set BOT_TOKEN, API_ID, API_HASH in .env
    2. pip install -r requirements.txt
    3. python bot.py
    4. First run will ask for your phone number (one-time login)
"""

import os
import asyncio
import logging
import requests
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import ChatAdminRequired, MessageIdInvalid

from card_parser import parse_result_file, CardEntry

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────

load_dotenv()
API_ID = os.getenv("API_ID", "").strip('"\'')
API_HASH = os.getenv("API_HASH", "").strip('"\'')

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# BIN lookup cache
bin_cache: dict[str, dict] = {}

# Load caption filters from .env (split by ||)
_raw_filter = os.getenv("CAPTION_FILTER", "").strip('"\'')
CAPTION_FILTERS = [c.strip().lower() for c in _raw_filter.split("||") if c.strip()]

# Gateways where ALL messages should be deleted (even charged)
_raw_delete_gw = os.getenv("DELETE_GATEWAYS", "").strip('"\'')
DELETE_GATEWAYS = [g.strip().lower() for g in _raw_delete_gw.split("||") if g.strip()]

# Only work in this group
_raw_chat = os.getenv("ALLOWED_CHAT", "-1003727002856").strip('"\'')
ALLOWED_CHAT = int(_raw_chat) if _raw_chat else -1003727002856

# Session string for cloud deployment (Render, etc.)
SESSION_STRING = os.getenv("SESSION_STRING", "").strip('"\'')

# Create Pyrogram userbot client
if SESSION_STRING:
    # Cloud mode: use session string (no interactive login needed)
    app = Client(
        "filter_bot",
        api_id=int(API_ID) if API_ID else 0,
        api_hash=API_HASH or "",
        session_string=SESSION_STRING,
    )
else:
    # Local mode: uses session file (asks for phone on first run)
    app = Client(
        "filter_bot_session",
        api_id=int(API_ID) if API_ID else 0,
        api_hash=API_HASH or "",
    )


# ──────────────────────────────────────────────
# BIN Lookup (Juspay API)
# ──────────────────────────────────────────────

def lookup_bin(bin_number: str) -> dict:
    """Look up BIN info using Juspay API."""
    if not bin_number or len(bin_number) < 6:
        return {}

    bin6 = bin_number[:6]

    if bin6 in bin_cache:
        return bin_cache[bin6]

    try:
        resp = requests.get(
            f"https://api.juspay.in/cardbins/{bin6}",
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            info = {
                "brand": (data.get("brand") or "N/A").upper(),
                "type": (data.get("type") or "N/A").upper(),
                "extended_type": (data.get("extended_card_type") or data.get("type") or "N/A").upper(),
                "card_sub_type": data.get("card_sub_type") or "N/A",
                "card_sub_type_category": (data.get("card_sub_type_category") or "N/A").upper(),
                "bank": data.get("bank") or "N/A",
                "juspay_bank_code": data.get("juspay_bank_code") or "N/A",
                "country": data.get("country") or "N/A",
            }
            bin_cache[bin6] = info
            return info
        else:
            return {}

    except Exception as e:
        logger.error(f"BIN lookup error for {bin6}: {e}")
        return {}


def get_country_flag(country_name: str) -> str:
    """Get a flag emoji based on country name."""
    flags = {
        "INDIA": "\U0001f1ee\U0001f1f3", "UNITED STATES": "\U0001f1fa\U0001f1f8",
        "UNITEDSTATES": "\U0001f1fa\U0001f1f8", "UNITED KINGDOM": "\U0001f1ec\U0001f1e7",
        "CANADA": "\U0001f1e8\U0001f1e6", "AUSTRALIA": "\U0001f1e6\U0001f1fa",
        "GERMANY": "\U0001f1e9\U0001f1ea", "FRANCE": "\U0001f1eb\U0001f1f7",
        "BRAZIL": "\U0001f1e7\U0001f1f7", "JAPAN": "\U0001f1ef\U0001f1f5",
        "CHINA": "\U0001f1e8\U0001f1f3", "RUSSIA": "\U0001f1f7\U0001f1fa",
        "MEXICO": "\U0001f1f2\U0001f1fd", "ITALY": "\U0001f1ee\U0001f1f9",
        "SPAIN": "\U0001f1ea\U0001f1f8", "SOUTH KOREA": "\U0001f1f0\U0001f1f7",
        "NETHERLANDS": "\U0001f1f3\U0001f1f1", "TURKEY": "\U0001f1f9\U0001f1f7",
        "SAUDI ARABIA": "\U0001f1f8\U0001f1e6", "SOUTH AFRICA": "\U0001f1ff\U0001f1e6",
        "NIGERIA": "\U0001f1f3\U0001f1ec", "INDONESIA": "\U0001f1ee\U0001f1e9",
        "SINGAPORE": "\U0001f1f8\U0001f1ec", "MALAYSIA": "\U0001f1f2\U0001f1fe",
        "PHILIPPINES": "\U0001f1f5\U0001f1ed", "THAILAND": "\U0001f1f9\U0001f1ed",
        "VIETNAM": "\U0001f1fb\U0001f1f3", "UAE": "\U0001f1e6\U0001f1ea",
        "UNITED ARAB EMIRATES": "\U0001f1e6\U0001f1ea", "PAKISTAN": "\U0001f1f5\U0001f1f0",
        "BANGLADESH": "\U0001f1e7\U0001f1e9", "EGYPT": "\U0001f1ea\U0001f1ec",
        "POLAND": "\U0001f1f5\U0001f1f1", "SWEDEN": "\U0001f1f8\U0001f1ea",
        "NORWAY": "\U0001f1f3\U0001f1f4", "DENMARK": "\U0001f1e9\U0001f1f0",
        "FINLAND": "\U0001f1eb\U0001f1ee", "IRELAND": "\U0001f1ee\U0001f1ea",
        "SWITZERLAND": "\U0001f1e8\U0001f1ed", "BELGIUM": "\U0001f1e7\U0001f1ea",
        "AUSTRIA": "\U0001f1e6\U0001f1f9", "PORTUGAL": "\U0001f1f5\U0001f1f9",
        "BRUNEI DARUSSALAM": "\U0001f1e7\U0001f1f3", "NEW ZEALAND": "\U0001f1f3\U0001f1ff",
        "ARGENTINA": "\U0001f1e6\U0001f1f7", "CHILE": "\U0001f1e8\U0001f1f1",
        "COLOMBIA": "\U0001f1e8\U0001f1f4", "PERU": "\U0001f1f5\U0001f1ea",
        "KENYA": "\U0001f1f0\U0001f1ea", "GHANA": "\U0001f1ec\U0001f1ed",
    }
    return flags.get(country_name.upper(), "\U0001f30d") if country_name else "\U0001f30d"


# ──────────────────────────────────────────────
# Card Drop Formatter
# ──────────────────────────────────────────────

def format_single_card(entry: CardEntry, bin_info: dict, status_label: str, status_emoji: str) -> str:
    """Format a single card as a standalone drop message."""
    brand = bin_info.get("brand", "N/A")
    card_type = bin_info.get("type", "N/A")
    extended = bin_info.get("extended_type", "N/A")
    sub_type = bin_info.get("card_sub_type", "N/A")
    sub_type_cat = bin_info.get("card_sub_type_category", "N/A")
    bank = bin_info.get("bank", "N/A")
    bank_code = bin_info.get("juspay_bank_code", "N/A")
    country = bin_info.get("country", "N/A")
    flag = get_country_flag(country)

    # Info line: BRAND - TYPE - SUB_TYPE
    info_parts = [brand, extended, sub_type]
    info_line = " - ".join(p for p in info_parts if p and p != "N/A")
    if not info_line:
        info_line = "N/A"

    return (
        f"{status_label} {status_emoji}\n"
        f"\n"
        f"\U0001d5d6\U0001d5ee\U0001d5ff\U0001d5f1: {entry.card}\n"
        f"\U0001d411\U0001d41e\U0001d42c\U0001d429\U0001d428\U0001d427\U0001d42c\U0001d41e: {entry.response}\n"
        f"\n"
        f"\U0001d401\U0001d408\U0001d40d: {entry.bin_number}\n"
        f"\U0001d5dc\U0001d5fb\U0001d5f3\U0001d5fc: {info_line}\n"
        f"\U0001d408\U0001d42c\U0001d42c\U0001d42e\U0001d41e\U0001d42b: {bank}\n"
        f"\U0001d402\U0001d428\U0001d42e\U0001d427\U0001d42d\U0001d42b\U0001d432: {country} {flag}\n"
        f"\U0001d413\U0001d432\U0001d429\U0001d41e: {card_type}\n"
        f"\U0001d404\U0001d431\U0001d42d\U0001d41e\U0001d427\U0001d41d\U0001d41e\U0001d41d: {extended}\n"
        f"\U0001d412\U0001d42e\U0001d41b \U0001d413\U0001d432\U0001d429\U0001d41e: {sub_type}\n"
        f"\U0001d402\U0001d41a\U0001d42d\U0001d41e\U0001d420\U0001d428\U0001d42b\U0001d432: {sub_type_cat}\n"
        f"\U0001d401\U0001d41a\U0001d427\U0001d424 \U0001d402\U0001d428\U0001d41d\U0001d41e: {bank_code}"
    )


def caption_matches(caption: str) -> bool:
    """Check if caption matches any of the user-defined CAPTION_FILTERS."""
    if not caption or not CAPTION_FILTERS:
        return False
    caption_lower = caption.strip().lower()
    return any(cf in caption_lower for cf in CAPTION_FILTERS)


# ──────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────

@app.on_message(filters.command("cmds"))
async def handle_cmds(client: Client, message: Message):
    """/cmds — show all available commands."""
    if message.chat.id != ALLOWED_CHAT:
        return

    cmds = (
        "\U0001f4cb \U0001d5d4\U0001d5f9\U0001d5f9 \U0001d5d6\U0001d5fc\U0001d5fa\U0001d5fa\U0001d5ee\U0001d5fb\U0001d5f1\U0001d600\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "\U0001f4c4 /fl \u2014 Reply to file/msg\n"
        "   Extract all cards (removes Luhn invalid + expired)\n\n"
        "\U0001f4c4 /fl <BIN> \u2014 Reply to file/msg\n"
        "   Filter cards by BIN with BIN info\n\n"
        "\U0001f50d /bin <BIN or Card> \u2014 BIN lookup\n"
        "   Also works as reply to a message\n\n"
        "\U0001f30d /country <name> \u2014 Reply to file\n"
        "   Filter cards by country\n\n"
        "\U0001f3e6 /bank <name> \u2014 Reply to file\n"
        "   Filter cards by bank/issuer\n\n"
        "\U0001f4e4 /export \u2014 Export today's charged cards\n"
        "   Sends a .txt with all charged cards today\n\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u2699\ufe0f \U0001d5d4\U0001d602\U0001d601\U0001d5fc\U0001d5fa\U0001d5ee\U0001d601\U0001d5f6\U0001d5fc\U0001d5fb\n\n"
        "\u2705 Auto-delete Declined messages\n"
        "\U0001f5d1\ufe0f Auto-delete DELETE_GATEWAYS\n"
        "\U0001f4b3 Replace Charged/Insufficient with BIN drop\n"
        "\U0001f4cc Auto-pin every card drop\n"
        "\U0001f4c2 Auto-filter result files by caption"
    )
    await message.reply_text(cmds)


@app.on_message(filters.document)
async def handle_document(client: Client, message: Message):
    """Handle .txt files — only in allowed group."""
    if message.chat.id != ALLOWED_CHAT:
        return

    document = message.document
    caption = message.caption or ""

    # Only process if caption matches your filter
    if not caption_matches(caption):
        return

    # Only process .txt files
    if not document.file_name or not document.file_name.lower().endswith(".txt"):
        return

    # Skip huge files
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        return

    try:
        # Download the file
        file_path = await message.download()

        # Read the file content
        content = None
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, AttributeError):
                continue

        # Clean up downloaded file
        if os.path.exists(file_path):
            os.remove(file_path)

        if content is None:
            return

        # Parse the file
        parsed = parse_result_file(content)

        # No hits? Do nothing
        if not parsed.charged and not parsed.insufficient:
            return

        chat_id = message.chat.id

        # ── Drop Charged cards one by one & pin each ──
        for entry in parsed.charged:
            bin_info = lookup_bin(entry.bin_number)
            card_text = format_single_card(
                entry, bin_info,
                "\U0001d402\U0001d421\U0001d41a\U0001d42b\U0001d420\U0001d41e\U0001d41d", "\u2705"
            )

            sent_msg = await client.send_message(chat_id=chat_id, text=card_text)

            try:
                await sent_msg.pin(disable_notification=True)
            except (ChatAdminRequired, MessageIdInvalid) as e:
                logger.warning(f"Could not pin message: {e}")
            except Exception as e:
                logger.warning(f"Pin error: {e}")

            await asyncio.sleep(1)

        # ── Drop Insufficient cards one by one & pin each ──
        for entry in parsed.insufficient:
            bin_info = lookup_bin(entry.bin_number)
            card_text = format_single_card(
                entry, bin_info,
                "\U0001d408\U0001d427\U0001d42c\U0001d42e\U0001d41f\U0001d41f\U0001d422\U0001d41c\U0001d422\U0001d41e\U0001d427\U0001d42d", "\u26a0\ufe0f"
            )

            sent_msg = await client.send_message(chat_id=chat_id, text=card_text)

            try:
                await sent_msg.pin(disable_notification=True)
            except (ChatAdminRequired, MessageIdInvalid) as e:
                logger.warning(f"Could not pin message: {e}")
            except Exception as e:
                logger.warning(f"Pin error: {e}")

            await asyncio.sleep(1)

        logger.info(
            f"Processed file in chat {chat_id}: "
            f"{len(parsed.charged)} charged, {len(parsed.insufficient)} insufficient"
        )

    except Exception as e:
        logger.error(f"Error processing file: {e}", exc_info=True)


# ──────────────────────────────────────────────
# /fl Command — Filter cards from any file/message
# ──────────────────────────────────────────────

import re
import io
from datetime import datetime

# Regex to match card patterns: number|mm|yy or yyyy|cvv
CARD_REGEX = re.compile(
    r'\b(\d{13,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})\b'
)


def luhn_check(card_number: str) -> bool:
    """Validate card number using Luhn algorithm."""
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13:
        return False
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def is_expired(month: str, year: str) -> bool:
    """Check if a card is expired. Card is valid through the end of its expiry month."""
    now = datetime.now()
    try:
        m = int(month)
        y = int(year)
        # Handle 2-digit year
        if y < 100:
            y += 2000
        # Card is valid through the entire expiry month
        # Expired = current year/month is AFTER the expiry year/month
        if now.year > y:
            return True
        if now.year == y and now.month > m:
            return True
        return False
    except (ValueError, TypeError):
        return True  # Can't parse = treat as expired


def extract_cards_from_text(text: str) -> list[str]:
    """Extract all card patterns from any text using regex."""
    cards = []
    for match in CARD_REGEX.finditer(text):
        cards.append(match.group(0))
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for c in cards:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def clean_cards(cards: list[str]) -> tuple[list[str], int, int]:
    """Remove Luhn-invalid and expired cards. Returns (clean_cards, luhn_removed, expired_removed)."""
    luhn_removed = 0
    expired_removed = 0
    clean = []

    for card in cards:
        parts = card.split("|")
        card_num = parts[0]
        month = parts[1] if len(parts) > 1 else ""
        year = parts[2] if len(parts) > 2 else ""

        # Luhn check
        if not luhn_check(card_num):
            luhn_removed += 1
            continue

        # Expiry check
        if is_expired(month, year):
            expired_removed += 1
            continue

        clean.append(card)

    return clean, luhn_removed, expired_removed


@app.on_message(filters.command("fl") & filters.reply)
async def handle_fl_command(client: Client, message: Message):
    """/fl — extract cards from replied file/message. /fl BIN — filter by BIN."""
    if message.chat.id != ALLOWED_CHAT:
        return

    replied = message.reply_to_message
    if not replied:
        return

    # Parse the BIN filter argument (if any)
    parts = message.text.strip().split(maxsplit=1)
    bin_filter = parts[1].strip() if len(parts) > 1 else None

    # Get text content from the replied message
    content = ""

    if replied.document:
        try:
            file_path = await replied.download()
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    with open(file_path, "r", encoding=encoding) as f:
                        content = f.read()
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"/fl download error: {e}")
            return
    elif replied.text:
        content = replied.text
    else:
        return

    if not content:
        return

    # Extract all cards
    all_cards = extract_cards_from_text(content)
    total_found = len(all_cards)

    if not all_cards:
        await message.reply_text("\u274c No cards found in that message/file.")
        return

    # Remove Luhn-invalid and expired cards
    all_cards, luhn_removed, expired_removed = clean_cards(all_cards)

    if not all_cards:
        await message.reply_text(
            f"\u274c All cards removed!\n"
            f"\U0001f4b3 Found: {total_found}\n"
            f"\u274c Luhn Invalid: {luhn_removed}\n"
            f"\U0001f4c5 Expired: {expired_removed}"
        )
        return

    # Filter by BIN if specified
    if bin_filter:
        filtered = [c for c in all_cards if c.startswith(bin_filter)]
        if not filtered:
            await message.reply_text(f"\u274c No cards found with BIN `{bin_filter}`")
            return

        # Get BIN info for the caption
        bin_info = lookup_bin(bin_filter[:6])
        brand = bin_info.get("brand", "N/A")
        extended = bin_info.get("extended_type", "N/A")
        sub_type = bin_info.get("card_sub_type", "N/A")
        bank = bin_info.get("bank", "N/A")
        country = bin_info.get("country", "N/A")
        flag = get_country_flag(country)

        info_parts = [brand, extended, sub_type]
        info_line = " - ".join(p for p in info_parts if p and p != "N/A")

        caption = (
            f"\U0001d401\U0001d408\U0001d40d: {bin_filter}\n"
            f"\U0001d5dc\U0001d5fb\U0001d5f3\U0001d5fc: {info_line}\n"
            f"\U0001d408\U0001d42c\U0001d42c\U0001d42e\U0001d41e\U0001d42b: {bank}\n"
            f"\U0001d402\U0001d428\U0001d42e\U0001d427\U0001d42d\U0001d42b\U0001d432: {country} {flag}\n"
            f"\U0001f4b3 Cards: {len(filtered)}"
        )
        cards_to_send = filtered
    else:
        caption = (
            f"\U0001f4b3 Total Found: {total_found}\n"
            f"\u274c Luhn Invalid: {luhn_removed}\n"
            f"\U0001f4c5 Expired: {expired_removed}\n"
            f"\u2705 Clean Cards: {len(all_cards)}"
        )
        cards_to_send = all_cards

    # Create .txt file with 1 card per line
    file_content = "\n".join(cards_to_send)
    file_bytes = io.BytesIO(file_content.encode("utf-8"))
    filename = f"cards_{bin_filter}.txt" if bin_filter else "cards.txt"
    file_bytes.name = filename

    # Send the file
    await message.reply_document(
        document=file_bytes,
        caption=caption,
    )

    logger.info(f"/fl command: sent {len(cards_to_send)} cards (luhn_removed={luhn_removed}, expired={expired_removed})")


# ──────────────────────────────────────────────
# /bin Command — BIN lookup (reply or direct)
# ──────────────────────────────────────────────

# Store today's charged cards for /export
charged_today: list[str] = []
charged_today_date: str = ""


def format_bin_info(bin6: str, bin_info: dict) -> str:
    """Format full BIN info as a beautiful message."""
    brand = bin_info.get("brand", "N/A")
    card_type = bin_info.get("type", "N/A")
    extended = bin_info.get("extended_type", "N/A")
    sub_type = bin_info.get("card_sub_type", "N/A")
    sub_type_cat = bin_info.get("card_sub_type_category", "N/A")
    bank = bin_info.get("bank", "N/A")
    bank_code = bin_info.get("juspay_bank_code", "N/A")
    country = bin_info.get("country", "N/A")
    flag = get_country_flag(country)

    info_parts = [brand, extended, sub_type]
    info_line = " - ".join(p for p in info_parts if p and p != "N/A")

    return (
        f"\U0001d401\U0001d408\U0001d40d: {bin6}\n"
        f"\U0001d5dc\U0001d5fb\U0001d5f3\U0001d5fc: {info_line}\n"
        f"\U0001d408\U0001d42c\U0001d42c\U0001d42e\U0001d41e\U0001d42b: {bank}\n"
        f"\U0001d402\U0001d428\U0001d42e\U0001d427\U0001d42d\U0001d42b\U0001d432: {country} {flag}\n"
        f"\U0001d413\U0001d432\U0001d429\U0001d41e: {card_type}\n"
        f"\U0001d404\U0001d431\U0001d42d\U0001d41e\U0001d427\U0001d41d\U0001d41e\U0001d41d: {extended}\n"
        f"\U0001d412\U0001d42e\U0001d41b \U0001d413\U0001d432\U0001d429\U0001d41e: {sub_type}\n"
        f"\U0001d402\U0001d41a\U0001d42d\U0001d41e\U0001d420\U0001d428\U0001d42b\U0001d432: {sub_type_cat}\n"
        f"\U0001d401\U0001d41a\U0001d427\U0001d424 \U0001d402\U0001d428\U0001d41d\U0001d41e: {bank_code}"
    )


@app.on_message(filters.command("bin"))
async def handle_bin_command(client: Client, message: Message):
    """/bin — BIN lookup. Reply to msg or /bin 471227 or /bin full_card."""
    if message.chat.id != ALLOWED_CHAT:
        return

    input_text = ""

    # Check if it's a reply
    if message.reply_to_message and message.reply_to_message.text:
        replied_text = message.reply_to_message.text
        # Try to extract card/BIN from replied message
        card_match = re.search(r'\b(\d{13,19})\b', replied_text)
        if card_match:
            input_text = card_match.group(1)
        else:
            # Try finding just a 6-8 digit BIN
            bin_match = re.search(r'\b(\d{6,8})\b', replied_text)
            if bin_match:
                input_text = bin_match.group(1)

    # Check command arguments
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) > 1:
        input_text = parts[1].strip()

    if not input_text:
        await message.reply_text(
            "\u2753 Usage:\n"
            "/bin 471227\n"
            "/bin 4712270074227232|10|27|031\n"
            "Or reply to a message with /bin"
        )
        return

    # Extract the BIN (first 6 digits) from whatever input we got
    digits_only = re.sub(r'[^\d]', '', input_text.split("|")[0] if "|" in input_text else input_text)
    if len(digits_only) < 6:
        await message.reply_text("\u274c Need at least 6 digits for BIN lookup.")
        return

    bin6 = digits_only[:6]
    bin_info = lookup_bin(bin6)

    if not bin_info:
        await message.reply_text(f"\u274c No BIN info found for `{bin6}`")
        return

    text = format_bin_info(bin6, bin_info)
    await message.reply_text(text)


# ──────────────────────────────────────────────
# /export — Export today's charged cards
# ──────────────────────────────────────────────

@app.on_message(filters.command("export"))
async def handle_export_command(client: Client, message: Message):
    """/export — send all today's charged cards as a .txt file."""
    if message.chat.id != ALLOWED_CHAT:
        return

    global charged_today, charged_today_date
    today = datetime.now().strftime("%Y-%m-%d")

    # Reset if new day
    if charged_today_date != today:
        charged_today = []
        charged_today_date = today

    if not charged_today:
        await message.reply_text("\U0001f4ad No charged cards collected today yet.")
        return

    # Remove duplicates
    seen = set()
    unique = []
    for c in charged_today:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    file_content = "\n".join(unique)
    file_bytes = io.BytesIO(file_content.encode("utf-8"))
    file_bytes.name = f"charged_{today}.txt"

    await message.reply_document(
        document=file_bytes,
        caption=(
            f"\u2705 Today's Charged Cards\n"
            f"\U0001f4c5 Date: {today}\n"
            f"\U0001f4b3 Total: {len(unique)}"
        ),
    )


# ──────────────────────────────────────────────
# Helper: Get content from replied message/file
# ──────────────────────────────────────────────

async def get_replied_content(message: Message) -> str:
    """Download and read content from a replied message or file."""
    replied = message.reply_to_message
    if not replied:
        return ""

    if replied.document:
        try:
            file_path = await replied.download()
            content = ""
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    with open(file_path, "r", encoding=encoding) as f:
                        content = f.read()
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue
            if os.path.exists(file_path):
                os.remove(file_path)
            return content
        except Exception as e:
            logger.error(f"Download error: {e}")
            return ""
    elif replied.text:
        return replied.text
    return ""


# ──────────────────────────────────────────────
# /country — Filter cards by country
# ──────────────────────────────────────────────

@app.on_message(filters.command("country") & filters.reply)
async def handle_country_command(client: Client, message: Message):
    """/country US — filter cards by country from replied file."""
    if message.chat.id != ALLOWED_CHAT:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("\u2753 Usage: Reply to a file with /country US or /country INDIA")
        return

    country_filter = parts[1].strip().upper()

    content = await get_replied_content(message)
    if not content:
        return

    all_cards = extract_cards_from_text(content)
    if not all_cards:
        await message.reply_text("\u274c No cards found.")
        return

    # Clean cards first
    all_cards, _, _ = clean_cards(all_cards)

    # Filter by country
    matched = []
    for card in all_cards:
        bin6 = card.split("|")[0][:6]
        info = lookup_bin(bin6)
        card_country = info.get("country", "").upper()
        if country_filter in card_country:
            matched.append(card)

    if not matched:
        await message.reply_text(f"\u274c No cards found from {country_filter}")
        return

    # Get country flag
    sample_info = lookup_bin(matched[0].split("|")[0][:6])
    flag = get_country_flag(sample_info.get("country", ""))

    file_content = "\n".join(matched)
    file_bytes = io.BytesIO(file_content.encode("utf-8"))
    file_bytes.name = f"cards_{country_filter}.txt"

    await message.reply_document(
        document=file_bytes,
        caption=(
            f"\U0001d402\U0001d428\U0001d42e\U0001d427\U0001d42d\U0001d42b\U0001d432: {country_filter} {flag}\n"
            f"\U0001f4b3 Cards: {len(matched)}"
        ),
    )


# ──────────────────────────────────────────────
# /bank — Filter cards by bank/issuer
# ──────────────────────────────────────────────

@app.on_message(filters.command("bank") & filters.reply)
async def handle_bank_command(client: Client, message: Message):
    """/bank CIMB — filter cards by bank/issuer from replied file."""
    if message.chat.id != ALLOWED_CHAT:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("\u2753 Usage: Reply to a file with /bank CIMB or /bank Chase")
        return

    bank_filter = parts[1].strip().upper()

    content = await get_replied_content(message)
    if not content:
        return

    all_cards = extract_cards_from_text(content)
    if not all_cards:
        await message.reply_text("\u274c No cards found.")
        return

    # Clean cards first
    all_cards, _, _ = clean_cards(all_cards)

    # Filter by bank
    matched = []
    for card in all_cards:
        bin6 = card.split("|")[0][:6]
        info = lookup_bin(bin6)
        card_bank = info.get("bank", "").upper()
        if bank_filter in card_bank:
            matched.append(card)

    if not matched:
        await message.reply_text(f"\u274c No cards found from bank: {bank_filter}")
        return

    # Get sample bank info for caption
    sample_info = lookup_bin(matched[0].split("|")[0][:6])
    bank_name = sample_info.get("bank", bank_filter)
    country = sample_info.get("country", "N/A")
    flag = get_country_flag(country)

    file_content = "\n".join(matched)
    file_bytes = io.BytesIO(file_content.encode("utf-8"))
    file_bytes.name = f"cards_{bank_filter}.txt"

    await message.reply_document(
        document=file_bytes,
        caption=(
            f"\U0001d408\U0001d42c\U0001d42c\U0001d42e\U0001d41e\U0001d42b: {bank_name}\n"
            f"\U0001d402\U0001d428\U0001d42e\U0001d427\U0001d42d\U0001d42b\U0001d432: {country} {flag}\n"
            f"\U0001f4b3 Cards: {len(matched)}"
        ),
    )





def is_checker_message(text: str) -> bool:
    """Check if a message is from a checker bot (has card result format)."""
    if not text:
        return False
    text_lower = text.lower()
    has_card = (
        "\U0001f4b3 card:" in text_lower
        or "\U0001d5d6\U0001d5ee\U0001d5ff\U0001d5f1:" in text_lower
        or '"card"' in text_lower
    )
    has_response = (
        "\U0001f4e9 response:" in text_lower
        or '"response"' in text_lower
        or "response:" in text_lower
    )
    return has_card and has_response


def is_from_delete_gateway(text: str) -> bool:
    """Check if message is from a gateway that should be fully deleted."""
    if not DELETE_GATEWAYS:
        return False
    text_lower = text.lower()
    return any(gw in text_lower for gw in DELETE_GATEWAYS)


def get_message_status(text: str) -> str:
    """Determine the status: 'charged', 'insufficient', 'declined', or 'unknown'."""
    if not text:
        return "unknown"
    text_lower = text.lower()

    if "charged" in text_lower or "payment successfully" in text_lower or "transaction successful" in text_lower:
        return "charged"
    if "insufficient" in text_lower:
        return "insufficient"
    if "declined" in text_lower:
        return "declined"

    return "unknown"


def extract_card_from_message(text: str) -> CardEntry | None:
    """Extract card number and response from a live checker bot message."""
    import re
    import json

    card_number = ""
    response = ""

    # Try to extract from JSON block first
    json_match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            card_number = data.get("card", "")
            response = data.get("response", "")
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: extract from formatted lines
    if not card_number:
        # Match 💳 Card: XXXX|XX|XX|XXX or 𝗖𝗮𝗿𝗱: XXXX|...
        card_match = re.search(r'(?:\U0001f4b3\s*Card:|Card:)\s*(\d[\d|]+)', text)
        if card_match:
            card_number = card_match.group(1).strip()

    if not response:
        # Match 📩 Response: ... or Response: ...
        resp_match = re.search(r'(?:\U0001f4e9\s*Response:|Response:)\s*(.+?)(?:\n|$)', text)
        if resp_match:
            response = resp_match.group(1).strip()

    if not card_number:
        return None

    # Determine status
    status = get_message_status(text)

    entry = CardEntry(
        card=card_number,
        response=response,
        status=status.capitalize(),
    )
    return entry


@app.on_message(filters.text & ~filters.private)
async def handle_live_message(client: Client, message: Message):
    """Auto-delete Declined. Replace Charged/Insufficient with BIN drop + pin."""
    text = message.text or ""

    # Only work in allowed group
    if message.chat.id != ALLOWED_CHAT:
        return

    # Only process messages that look like checker bot output
    if not is_checker_message(text):
        return

    # 1) If message is from a DELETE_GATEWAY (e.g. Stripe Auth) — delete ALL
    if is_from_delete_gateway(text):
        try:
            await message.delete()
            logger.info(f"Deleted delete-gateway message in chat {message.chat.id}")
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")
        return

    # 2) Check status
    status = get_message_status(text)

    if status == "declined":
        # Just delete declined messages
        try:
            await message.delete()
            logger.info(f"Deleted declined message in chat {message.chat.id}")
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")

    elif status in ("charged", "insufficient"):
        # Extract card info from the message
        entry = extract_card_from_message(text)
        if not entry:
            return

        chat_id = message.chat.id

        # Delete the original checker message
        try:
            await message.delete()
        except Exception as e:
            logger.warning(f"Could not delete original message: {e}")

        # Look up BIN info
        bin_info = lookup_bin(entry.bin_number)

        # Build our formatted card drop
        if status == "charged":
            status_label = "\U0001d402\U0001d421\U0001d41a\U0001d42b\U0001d420\U0001d41e\U0001d41d"
            status_emoji = "\u2705"
        else:
            status_label = "\U0001d408\U0001d427\U0001d42c\U0001d42e\U0001d41f\U0001d41f\U0001d422\U0001d41c\U0001d422\U0001d41e\U0001d427\U0001d42d"
            status_emoji = "\u26a0\ufe0f"

        card_text = format_single_card(entry, bin_info, status_label, status_emoji)

        # Send our formatted drop
        sent_msg = await client.send_message(chat_id=chat_id, text=card_text)

        # Pin it
        try:
            await sent_msg.pin(disable_notification=True)
        except Exception as e:
            logger.warning(f"Could not pin message: {e}")

        # Save charged cards for /export
        if status == "charged":
            global charged_today, charged_today_date
            today = datetime.now().strftime("%Y-%m-%d")
            if charged_today_date != today:
                charged_today = []
                charged_today_date = today
            charged_today.append(entry.card)

        logger.info(f"Replaced {status} message with BIN drop in chat {chat_id}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
    if not API_ID or API_ID == "your_api_id_here":
        print("=" * 50)
        print("  ERROR: Set your credentials in .env file!")
        print()
        print("  1. Go to https://my.telegram.org")
        print("  2. Log in with your phone number")
        print("  3. Go to 'API Development Tools'")
        print("  4. Create an application")
        print("  5. Copy API_ID and API_HASH to .env")
        print("=" * 50)
    else:
        print("=" * 50)
        print("  Response Filter Bot (Userbot) — Starting...")
        print("  First run will ask for phone number.")
        print("  Press Ctrl+C to stop.")
        print("=" * 50)
        app.run()
