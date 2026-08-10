#!/usr/bin/env python3
"""Comprehensive verification for settings.py color changes."""
import re

FILE = "/Users/nishkarshkumar/Desktop/Doraemon/titanic-saver/features/settings.py"

with open(FILE, "r") as f:
    content = f.read()
    lines = content.split("\n")

print("=" * 70)
print("COMPREHENSIVE VERIFICATION REPORT")
print("=" * 70)

# 1. Check remaining non-blue colored_button
non_blue = re.findall(r'colored_button\([^,]+,\s*"(green|red|default)"', content)
print(f"\n1. Remaining non-blue colored_button calls: {len(non_blue)}")
if non_blue:
    for c in non_blue:
        print(f"   WARNING: Still found: {c}")
else:
    print("   PASS: No green/red/default remaining")

# 2. Check for bare InlineKeyboardButton (not wrapped in colored_button)
bare_count = 0
bare_lines_list = []
for i, line in enumerate(lines, 1):
    if "InlineKeyboardButton(" in line and "colored_button(" not in line:
        bare_count += 1
        bare_lines_list.append(i)
print(f"\n2. Bare InlineKeyboardButton calls (no colored_button wrapper): {bare_count}")
if bare_lines_list:
    print(f"   WARNING: Lines: {bare_lines_list}")
else:
    print("   PASS: All InlineKeyboardButton calls use colored_button wrapper")

# 3. Count ALL colored_button calls by color
blue_count = len(re.findall(r'colored_button\([^,]+,\s*"blue"', content))
green_count = len(re.findall(r'colored_button\([^,]+,\s*"green"', content))
red_count = len(re.findall(r'colored_button\([^,]+,\s*"red"', content))
default_count = len(re.findall(r'colored_button\([^,]+,\s*"default"', content))
total_cb = blue_count + green_count + red_count + default_count
print(f"\n3. Total colored_button usage by color:")
print(f"   - Blue:    {blue_count}")
print(f"   - Green:   {green_count}")
print(f"   - Red:     {red_count}")
print(f"   - Default: {default_count}")
print(f"   - TOTAL:   {total_cb}")

# 4. Verify specific sections
print(f"\n4. Specific section verification:")

# 4a. settings_menu L100-103 area (Open Here / Open in Private)
for i, line in enumerate(lines, 1):
    if '📖 Open Here' in line or '💬 Open in Private' in line:
        has_blue = '"blue"' in line
        has_green = '"green"' in line
        status = "PASS" if has_blue and not has_green else "FAIL"
        print(f"   L{i}: {line.strip()[:90]}")
        print(f"      -> Blue={has_blue}, Green={has_green} -> {status}")

# 4b. Night mode hour grid
found_nightmode = False
for i, line in enumerate(lines, 1):
    if "str(hour)" in line and "callback_prefix" in line:
        found_nightmode = True
        has_blue = 'colored_button(str(hour), "blue")' in line
        print(f"   Nightmode hour grid L{i}: colored_button wrap -> {'PASS' if has_blue else 'FAIL'}")
        break
if not found_nightmode:
    print("   WARNING: Nightmode hour grid NOT found!")

# 4c. Emergency keyboard bare buttons
print("   Emergency keyboard (12 toggle buttons):")
emergency_vars = ["enabled", "text", "stickers", "media", "links", "premium", "contact", "location", "voice", "audio", "forward", "poll"]
emergency_ok = 0
for var in emergency_vars:
    pattern = f'colored_button({var}, "blue")'
    found = False
    for line in lines:
        if pattern in line:
            found = True
            emergency_ok += 1
            break
print(f"      {emergency_ok}/12 emergency toggle buttons wrapped in colored_button(blue) -> {'PASS' if emergency_ok == 12 else 'FAIL'}")

# 4d. "Go to Private" keyboard
print("   'Go to Private' keyboard:")
for i, line in enumerate(lines, 1):
    if "Click Here to Open in Private" in line:
        has_blue = '"blue"' in line
        print(f"      L{i}: Blue={has_blue} -> {'PASS' if has_blue else 'FAIL'}")
        break

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
