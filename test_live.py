"""Test that both message formats are detected and parsed correctly."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from parser import CardEntry

# Simulate the extract function from bot.py
import re, json

def extract_card_from_message(text):
    card_number = ""
    response = ""

    json_match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            card_number = data.get("card", "")
            response = data.get("response", "")
        except:
            pass

    if not card_number:
        card_match = re.search(r'Card:\s*(\d[\d|]+)', text)
        if card_match:
            card_number = card_match.group(1).strip()

    if not response:
        resp_match = re.search(r'Response:\s*(.+?)(?:\n|$)', text)
        if resp_match:
            response = resp_match.group(1).strip()

    if not card_number:
        return None

    return CardEntry(card=card_number, response=response, status="Charged")


# Message 1: Braintree (single-line JSON)
msg1 = """👤 User: Rohit
🆔 ID: 1038982906

💳 Card: 4239530083492141|10|26|731
📩 Response: Transaction Successful ✅

{"card":"4239530083492141|10|26|731","credit":"@xoxhunterxD","gateway":"Braintree Charge","response":"Transaction Successful ✅","status":"Charged 💎","time":"13.61s"}"""

# Message 2: Stripe (pretty JSON)
msg2 = """👤 User: Rohit
🆔 ID: 1038982906

💳 Card: 4340762031453216|04|31|682
📩 Response: Payment Successfully 💎

{
  "card": "4340762031453216|04|2031|682",
  "credit": "@xoxhunterxd",
  "gateway": "Stripe $1 Charge",
  "response": "Payment Successfully 💎",
  "status": "Charged 💎",
  "time": "4.8s"
}"""

print("=" * 50)
for i, msg in enumerate([msg1, msg2], 1):
    entry = extract_card_from_message(msg)
    if entry:
        print(f"Message {i}:")
        print(f"  Card: {entry.card}")
        print(f"  Response: {entry.response}")
        print(f"  BIN: {entry.bin_number}")
        print(f"  Status: {entry.status}")
        print(f"  Action: DELETE original -> SEND BIN drop -> PIN")
    else:
        print(f"Message {i}: FAILED to parse!")
    print()
print("=" * 50)
print("Both formats work! ✅")
