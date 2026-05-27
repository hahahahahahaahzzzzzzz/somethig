"""
generate_session.py — Run this LOCALLY one time to generate your session string.
Then paste the string into Render's environment variables.
"""

from pyrogram import Client
import os
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not API_ID or API_ID == "your_api_id_here":
    print("=" * 50)
    print("  First, set API_ID and API_HASH in .env")
    print("  Get them from https://my.telegram.org")
    print("=" * 50)
    exit()

print("=" * 50)
print("  Session String Generator")
print("  You'll be asked for your phone number + OTP")
print("  This is a ONE-TIME process")
print("=" * 50)

with Client(
    "session_gen",
    api_id=int(API_ID),
    api_hash=API_HASH,
) as app:
    session_string = app.export_session_string()
    print()
    print("=" * 50)
    print("  YOUR SESSION STRING (copy this):")
    print("=" * 50)
    print()
    print(session_string)
    print()
    print("=" * 50)
    print("  Paste this as SESSION_STRING in Render env vars")
    print("  DO NOT share this with anyone!")
    print("=" * 50)
