#!/usr/bin/env python3
"""Fix double-prefix import issues from the first migration pass.

Also updates tests/test_imports.py with sys.path prepend.
"""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))

# Map: buggy_dotted_prefix -> correct_dotted_prefix  (only applies to MODULE prefix before 'import')
FIXES = [
    ("moderation.moderation.anonymous_admin", "moderation.anonymous_admin"),
    ("moderation.moderation.block_content", "moderation.block_content"),
    ("moderation.moderation.bot_protection", "moderation.bot_protection"),
    ("moderation.moderation.forward_protection", "moderation.forward_protection"),
    ("moderation.moderation.language_filter", "moderation.language_filter"),
    ("moderation.moderation.nsfw_detector", "moderation.nsfw_detector"),
]

def fix_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    orig = content
    for bad, good in FIXES:
        # 'from BAD.xxx import' -> 'from GOOD.xxx import'
        content = re.sub(
            r"\bfrom\s+" + re.escape(bad) + r"(?=[\.\s])",
            "from " + good,
            content,
        )
        # 'import BAD.xxx' (less common)
        content = re.sub(
            r"\bimport\s+" + re.escape(bad) + r"(?=[\.\s,])",
            "import " + good,
            content,
        )
    if content != orig:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        rel = os.path.relpath(path, ROOT)
        print(f"FIXED {rel}")

def main():
    for dirpath, _dirs, files in os.walk(ROOT):
        if any(p in dirpath for p in (".git", "__pycache__", ".venv", "venv")):
            continue
        for fn in files:
            if fn.endswith(".py") and fn != "_fixup.py" and fn != "_migrate.py":
                fix_file(os.path.join(dirpath, fn))

    # Patch tests/test_imports.py to sys.path.insert(0, ROOT)
    test_path = os.path.join(ROOT, "tests", "test_imports.py")
    if os.path.exists(test_path):
        with open(test_path, "r", encoding="utf-8") as f:
            content = f.read()
        shebang = "#!/usr/bin/env python3\n"
        sys_path_code = (
            "import sys\n"
            "import os\n"
            "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        )
        if "sys.path.insert" not in content:
            # Insert after shebang (if any) then logging setup line 3
            lines = content.split("\n", 4)
            if lines[0].startswith("#!"):
                new_content = shebang + sys_path_code + "\n".join(lines[1:])
            else:
                new_content = sys_path_code + content
            # Also fix the remaining double imports inline
            for bad, good in FIXES:
                new_content = new_content.replace(bad, good)
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print("PATCHED tests/test_imports.py with sys.path")
    print("Done.")

if __name__ == "__main__":
    main()
