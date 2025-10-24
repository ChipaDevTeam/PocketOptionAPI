# inspect_pocket.py
import importlib, pkgutil, inspect, os
import sys

# make sure repo root is importable
root = os.path.abspath(os.path.dirname(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

PKG = "pocketoptionapi_async"

try:
    pkg = importlib.import_module(PKG)
except Exception as e:
    print("Failed to import package", PKG, ":", e)
    sys.exit(1)

print("Package imported:", pkg)
print("\nTop-level modules in package:")
for m in pkgutil.iter_modules(pkg.__path__):
    print(" -", m.name)

candidates = []
print("\nScanning modules for classes and order-like methods (this may take a sec)...\n")
for finder, name, ispkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
    try:
        mod = importlib.import_module(name)
    except Exception as e:
        print("  (skip) failed to import", name, ":", e)
        continue
    for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
        # only show classes defined in this package
        if cls.__module__.startswith(PKG):
            methods = [m for m, _ in inspect.getmembers(cls, inspect.isfunction)]
            # look for order-like methods
            order_like = [m for m in methods if any(x in m.lower() for x in ("buy", "place", "order", "trade", "create"))]
            if order_like:
                print(f"Class: {cls.__module__}.{cls_name}")
                print("  order-like methods:", order_like)
                candidates.append((cls.__module__, cls_name, order_like))
            else:
                # also show client-ish classes
                if any(x in cls_name.lower() for x in ("client","pocket","async")):
                    print(f"Class: {cls.__module__}.{cls_name}")
                    print("  methods sample:", methods[:8])
    # small separator
print("\nDone. If nothing useful shows up paste the output here and I’ll produce the exact script.")
