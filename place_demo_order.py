#!/usr/bin/env python3
import os
from dotenv import load_dotenv
load_dotenv()

# Try common import; adapt if your repo uses different module names
try:
    # common sync API wrapper
    from pocketoptionapi_async.stable_api import PocketOption
except Exception:
    # fallback to client (some forks expose sync client differently)
    try:
        from pocketoptionapi_async.client import PocketOption as PocketOption
    except Exception:
        raise SystemExit("Cannot import PocketOption class. Run grep as explained in README to find the class name.")

def main():
    ssid = os.getenv("SSID")
    if not ssid:
        raise SystemExit("SSID not set. Put it in .env or export SSID in shell.")

    api = PocketOption(ssid)            # instantiate client
    ok, msg = api.connect()             # many forks return (ok, msg) from connect
    if not ok:
        print("Connect failed:", msg)
        return

    # --- change these to an asset available in demo account ---
    amount = 1.0
    asset = "EURUSD"      # example — use an asset listed by the demo account
    direction = "call"    # or "put"
    duration = 60         # seconds or API-specific timeframe

    # Try common method names in order of likelihood
    for method in ("buy", "place_order", "create_order", "trade"):
        if hasattr(api, method):
            fn = getattr(api, method)
            try:
                print(f"Using method: {method}")
                res = fn(amount, asset, duration, direction)  # many libs use this signature
            except TypeError:
                # try keyword style
                try:
                    res = fn(amount=amount, asset=asset, direction=direction, duration=duration)
                except Exception as e:
                    print("Method exists but calling failed:", e)
                    res = None
            print("Result:", res)
            break
    else:
        print("No typical order method found on api object. See instructions to grep for available methods.")

    try:
        # read balance or open positions if available
        if hasattr(api, "get_balance"):
            print("Balance:", api.get_balance())
        elif hasattr(api, "balance"):
            print("Balance property:", api.balance)
    except Exception:
        pass

    api.close()

if __name__ == "__main__":
    main()
