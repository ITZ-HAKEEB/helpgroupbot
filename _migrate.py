#!/usr/bin/env python3
"""One-time migration script: reorganize flat files into subpackages.

Mapping (src/py modules get moved, imports rewritten.
Run from project root: python _migrate.py
"""
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------------- File moves: old_path (relative to ROOT) -> new_path (relative to ROOT)
MOVE_MAP = {
    # core/
    "config.py": "core/config.py",
    "database.py": "core/database.py",
    "generate_session.py": "core/generate_session.py",

    # managers/  (includes merged Manager/ + *_manager_mongo.py)
    "Manager/__init__.py": "managers/__init__.py",
    "Manager/README.md": "managers/README.md",
    "Manager/actions.py": "managers/actions.py",
    "Manager/grouphandler.py": "managers/grouphandler.py",
    "Manager/id.py": "managers/id.py",
    "Manager/info.py": "managers/info.py",
    "Manager/mass_actions.py": "managers/mass_actions.py",
    "Manager/promote.py": "managers/promote.py",
    "Manager/psend.py": "managers/psend.py",
    "Manager/purge.py": "managers/purge.py",
    "Manager/staff.py": "managers/staff.py",
    "Manager/zombie.py": "managers/zombie.py",

    "admin_manager_mongo.py": "managers/admin_manager_mongo.py",
    "block_content_manager_mongo.py": "managers/block_content_manager_mongo.py",
    "filters_manager_mongo.py": "managers/filters_manager_mongo.py",
    "moderation_manager_mongo.py": "managers/moderation_manager_mongo.py",
    "settings_manager_mongo.py": "managers/settings_manager_mongo.py",
    "staff_manager_mongo.py": "managers/staff_manager_mongo.py",
    "user_manager_mongo.py": "managers/user_manager_mongo.py",

    # moderation/
    "admin.py": "moderation/admin.py",
    "antiflood.py": "moderation/antiflood.py",
    "anonymous_admin.py": "moderation/anonymous_admin.py",
    "blocking.py": "moderation/blocking.py",
    "block_content.py": "moderation/block_content.py",
    "bot_protection.py": "moderation/bot_protection.py",
    "filter.py": "moderation/filter.py",
    "forward_protection.py": "moderation/forward_protection.py",
    "language_filter.py": "moderation/language_filter.py",
    "link_spam.py": "moderation/link_spam.py",
    "moderation.py": "moderation/moderation.py",
    "nsfw_detector.py": "moderation/nsfw_detector.py",
    "sudo.py": "moderation/sudo.py",

    # handlers/
    "bio_handler.py": "handlers/bio_handler.py",
    "blocking_handler.py": "handlers/blocking_handler.py",
    "edit_handler.py": "handlers/edit_handler.py",
    "welcome.py": "handlers/welcome.py",

    # features/
    "auto_delete.py": "features/auto_delete.py",
    "broadcast.py": "features/broadcast.py",
    "clean_service.py": "features/clean_service.py",
    "font.py": "features/font.py",
    "font_normalizer.py": "features/font_normalizer.py",
    "help.py": "features/help.py",
    "join_request.py": "features/join_request.py",
    "nightmode.py": "features/nightmode.py",
    "recurring.py": "features/recurring.py",
    "settings.py": "features/settings.py",
    "sticker_manager.py": "features/sticker_manager.py",
    "tagger.py": "features/tagger.py",
    "translator.py": "features/translator.py",
    "translator_ai.py": "features/translator_ai.py",
    "voice_chat.py": "features/voice_chat.py",

    # tests/
    "test_imports.py": "tests/test_imports.py",
}

# ---------------- Import rewrite table: old dotted module -> new dotted module
# Order matters: longer Manager.X entries must come before bare Manager.
IMPORT_REWRITE = [
    # Manager.* -> managers.*
    ("Manager.actions", "managers.actions"),
    ("Manager.grouphandler", "managers.grouphandler"),
    ("Manager.id", "managers.id"),
    ("Manager.info", "managers.info"),
    ("Manager.mass_actions", "managers.mass_actions"),
    ("Manager.promote", "managers.promote"),
    ("Manager.psend", "managers.psend"),
    ("Manager.purge", "managers.purge"),
    ("Manager.staff", "managers.staff"),
    ("Manager.zombie", "managers.zombie"),
    ("Manager", "managers"),

    # core
    ("config", "core.config"),
    ("database", "core.database"),
    ("generate_session", "core.generate_session"),

    # managers (mongo managers)
    ("admin_manager_mongo", "managers.admin_manager_mongo"),
    ("block_content_manager_mongo", "managers.block_content_manager_mongo"),
    ("filters_manager_mongo", "managers.filters_manager_mongo"),
    ("moderation_manager_mongo", "managers.moderation_manager_mongo"),
    ("settings_manager_mongo", "managers.settings_manager_mongo"),
    ("staff_manager_mongo", "managers.staff_manager_mongo"),
    ("user_manager_mongo", "managers.user_manager_mongo"),

    # moderation/
    ("anonymous_admin", "moderation.anonymous_admin"),
    ("antiflood", "moderation.antiflood"),
    ("block_content", "moderation.block_content"),
    ("blocking_handler", "handlers.blocking_handler"),
    ("blocking", "moderation.blocking"),
    ("bot_protection", "moderation.bot_protection"),
    ("edit_handler", "handlers.edit_handler"),
    ("filter", "moderation.filter"),
    ("forward_protection", "moderation.forward_protection"),
    ("language_filter", "moderation.language_filter"),
    ("link_spam", "moderation.link_spam"),
    ("moderation", "moderation.moderation"),
    ("nsfw_detector", "moderation.nsfw_detector"),
    ("sudo", "moderation.sudo"),
    ("admin", "moderation.admin"),

    # handlers/
    ("bio_handler", "handlers.bio_handler"),
    ("welcome", "handlers.welcome"),

    # features/
    ("auto_delete", "features.auto_delete"),
    ("broadcast", "features.broadcast"),
    ("clean_service", "features.clean_service"),
    ("font_normalizer", "features.font_normalizer"),
    ("font", "features.font"),
    ("help", "features.help"),
    ("join_request", "features.join_request"),
    ("nightmode", "features.nightmode"),
    ("recurring", "features.recurring"),
    ("settings_manager_mongo", "managers.settings_manager_mongo"),  # duplicate, keep
    ("settings", "features.settings"),
    ("sticker_manager", "features.sticker_manager"),
    ("tagger", "features.tagger"),
    ("translator_ai", "features.translator_ai"),
    ("translator", "features.translator"),
    ("voice_chat", "features.voice_chat"),
]

# Deduplicate while preserving order (unique by first element)
_seen = set()
IMPORT_REWRITE_UNIQUE = []
for old, new in IMPORT_REWRITE:
    if old not in _seen:
        _seen.add(old)
        IMPORT_REWRITE_UNIQUE.append((old, new))
IMPORT_REWRITE = IMPORT_REWRITE_UNIQUE

# Sorted by length desc so longer matches are tried first
IMPORT_REWRITE.sort(key=lambda x: len(x[0]), reverse=True)


def rewrite_imports(content: str) -> str:
    """Rewrite all ``from X import Y`` and ``import X`` style lines with new module paths."""
    lines = content.split("\n")
    new_lines = []
    for line in lines:
        stripped = line.lstrip()
        # Only rewrite top-level / indented import lines.
        if stripped.startswith("from ") or stripped.startswith("import "):
            # Try replacing left-side only (module name patterns.
            for old_mod, new_mod in IMPORT_REWRITE:
                # Pattern 1: from MODULE import ...
                # Use word-boundary-ish via regex but only for "from MODULE import"
                pattern_from = rf"\bfrom\s+" + re.escape(old_mod) + r"(\.?(?=\s|$))(?=\s+import\b)"
                pattern_from2 = rf"\bfrom\s+" + re.escape(old_mod) + r"(?=\s+import\b)"
                pattern_import = rf"\bimport\s+" + re.escape(old_mod) + r"(?=\s|,|$)"
                # Avoid matching partial words (e.g. 'import settings_manager' should not match 'settings')
                # Check: after old_mod must be followed by space, comma, end, dot + ... import ... 
                sub_from = re.sub(
                    r"\bfrom\s+" + re.escape(old_mod) + r"(?=\s+import\b|\.)",
                    "from " + new_mod,
                    line,
                )
                if sub_from != line:
                    line = sub_from
                    continue
                sub_import = re.sub(
                    r"\bimport\s+" + re.escape(old_mod) + r"(?=\s|,|$)",
                    "import " + new_mod,
                    line,
                )
                if sub_import != line:
                    line = sub_import
                    break
        new_lines.append(line)
    return "\n".join(new_lines)


def move_files():
    for src_rel, dst_rel in MOVE_MAP.items():
        src = os.path.join(ROOT, src_rel)
        dst = os.path.join(ROOT, dst_rel)
        if not os.path.exists(src):
            print(f"SKIP missing source: {src_rel}")
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(dst)
        shutil.move(src, dst)
        print(f"MOVED {src_rel} -> {dst_rel}")


def rewrite_all_imports():
    # Rewrite all .py files under ROOT (recursively).
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        # Skip hidden dirs and venv-style
        if any(p in dirpath for p in (".git", "__pycache__", ".venv", "venv")):
            continue
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            # Skip the migrate script itself
            if os.path.basename(fpath) == "_migrate.py":
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            new_content = rewrite_imports(content)
            if new_content != content:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                rel = os.path.relpath(fpath, ROOT)
                print(f"REWROTE imports in {rel}")


def create_init_files():
    for pkg in ("core", "managers", "moderation", "handlers", "features", "tests"):
        init = os.path.join(ROOT, pkg, "__init__.py")
        if not os.path.exists(init):
            with open(init, "w", encoding="utf-8") as f:
                f.write('"""`' + pkg + '` package."""\n')
            print(f"CREATED {pkg}/__init__.py")


def cleanup_old_manager_dir():
    old = os.path.join(ROOT, "Manager")
    if os.path.isdir(old):
        # If empty, remove
        try:
            os.rmdir(old)
            print(f"REMOVED empty Manager/ directory")
        except OSError:
            print(f"WARNING: Manager/ not empty, not removed")


def main():
    print("=== Step 1: Move files ===")
    move_files()
    print("\n=== Step 2: Create __init__.py files ===")
    create_init_files()
    print("\n=== Step 3: Rewrite imports across all .py files ===")
    rewrite_all_imports()
    print("\n=== Step 4: Cleanup old Manager/ dir ===")
    cleanup_old_manager_dir()
    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
