"""Quick test script to verify parser works with the sample file."""

from parser import parse_result_file

# Read the sample file
with open("Stripe 1$ Charge_result_1038982906_data.txt", "r", encoding="utf-8") as f:
    content = f.read()

# Parse it
result = parse_result_file(content)

print(f"Title: {result.title}")
print(f"Total entries parsed: {len(result.all_entries)}")
print(f"Charged found: {len(result.charged)}")
print(f"Insufficient found: {len(result.insufficient)}")
print()

print("=" * 50)
print("CHARGED CARDS:")
print("=" * 50)
for entry in result.charged:
    print(f"  💳 {entry.card}")
    print(f"     Response: {entry.response}")
    print(f"     Status: {entry.status}")
    print(f"     BIN: {entry.bin_number}")
    print()

print("=" * 50)
print("INSUFFICIENT CARDS:")
print("=" * 50)
for entry in result.insufficient:
    print(f"  💳 {entry.card}")
    print(f"     Response: {entry.response}")
    print(f"     Status: {entry.status}")
    print(f"     BIN: {entry.bin_number}")
    print()
