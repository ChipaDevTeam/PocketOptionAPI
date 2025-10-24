#!/usr/bin/env python3
"""
fix_imports.py
Usage:
  python fix_imports.py /path/to/pocketoptionapi_async

Patches bare internal imports (e.g. `from models import X` or `import client`)
to package-qualified imports `from pocketoptionapi_async.models import X`
or `from pocketoptionapi_async import client`.

It will back up each file to filename.bak before editing.
"""
import sys, os, re, shutil

if len(sys.argv) < 2:
    print("Usage: python fix_imports.py /path/to/pocketoptionapi_async")
    sys.exit(1)

pkg_dir = sys.argv[1]
if not os.path.isdir(pkg_dir):
    print("Directory not found:", pkg_dir)
    sys.exit(2)

# determine candidate module names in that folder (module.py or package dir)
candidates = set()
for name in os.listdir(pkg_dir):
    if name.endswith(".py"):
        candidates.add(name[:-3])
    elif os.path.isdir(os.path.join(pkg_dir, name)) and os.path.isfile(os.path.join(pkg_dir, name, "__init__.py")):
        candidates.add(name)

print("Found candidate internal modules:", sorted(candidates))

# regex helpers
def replace_in_text(text, mod):
    # 1) from <mod> import ...
    pattern1 = re.compile(rf'(^|\n)(\s*)from\s+{re.escape(mod)}\s+import\s+', flags=re.MULTILINE)
    repl1 = rf'\1\2from pocketoptionapi_async.{mod} import '
    text = pattern1.sub(repl1, text)

    # 2) import <mod> [as ...]  -> convert to `from pocketoptionapi_async import <mod> [as ...]`
    # but avoid converting "import a, b" or "import pkg.mod"
    pattern2 = re.compile(rf'(^|\n)(\s*)import\s+{re.escape(mod)}(\s|$|,| as)', flags=re.MULTILINE)
    repl2 = rf'\1\2from pocketoptionapi_async import {mod}\3'
    text = pattern2.sub(repl2, text)

    return text

# walk and patch
patched_files = []
for root, _, files in os.walk(pkg_dir):
    for fname in files:
        if not fname.endswith(".py"):
            continue
        path = os.path.join(root, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        new_text = text
        for mod in sorted(candidates, key=lambda x: -len(x)):  # longer first
            # avoid changing the very file which defines the module if it imports itself
            # but it's safe to replace in general
            new_text = replace_in_text(new_text, mod)

        if new_text != text:
            bak = path + ".bak"
            print("Patching", path, "-> backup saved to", bak)
            shutil.copy2(path, bak)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
            patched_files.append(path)

if not patched_files:
    print("No files required patching.")
else:
    print("Patched files count:", len(patched_files))
    for p in patched_files:
        print(" -", p)
print("Done.")
