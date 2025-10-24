#!/usr/bin/env python3
"""
async_place_demo_order.py
Usage:
  source .venv/bin/activate
  python async_place_demo_order.py

This script:
- Loads SSID from .env
- Connects with AsyncPocketOptionClient
- Attempts to place a small demo order using several common call signatures
- Prints responses and checks active orders
"""
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

SSID = os.getenv("SSID")
if not SSID:
    raise SystemExit("SSID not found in .env. Add SSID=... (demo SSID, isDemo:1).")

try:
    from pocketoptionapi_async.client import AsyncPocketOptionClient
except Exception as e:
    raise SystemExit("Cannot import AsyncPocketOptionClient: " + str(e))

# Configure order params (change asset/duration/amount to what your demo account supports)
AMOUNT = 1.0
ASSET = "EURUSD"      # update if needed (use an asset visible in demo UI)
DIRECTION = "call"    # or "put"
DURATION = 60         # seconds or API-specific timeframe

async def try_call(fn, *args, **kwargs):
    try:
        res = await fn(*args, **kwargs)
        return True, res
    except TypeError as te:
        # signature mismatch
        return False, te
    except Exception as e:
        return False, e

async def main():
    client = AsyncPocketOptionClient(SSID)

    print("Connecting...")
    try:
        await client.connect()
    except Exception as e:
        print("Failed to connect:", e)
        return

    print("Connected. Attempting to place order...")

    # candidate method names in priority order
    candidate_methods = [
        "place_order",
        "buy",
        "create_order",
        "trade",
        "_send_order"   # internal but present in some versions
    ]

    tried = False
    for method_name in candidate_methods:
        if hasattr(client, method_name):
            tried = True
            method = getattr(client, method_name)
            print(f"Trying method: {method_name} (positional)")

            ok, res = await try_call(method, AMOUNT, ASSET, DURATION, DIRECTION)
            if ok:
                print(f"Success (positional) with {method_name} ->", res)
                order_result = res
                break

            # try common keyword variations
            kw_variants = [
                {"amount": AMOUNT, "asset": ASSET, "direction": DIRECTION, "duration": DURATION},
                {"amount": AMOUNT, "instrument": ASSET, "direction": DIRECTION, "duration": DURATION},
                {"amount": AMOUNT, "asset": ASSET, "type": "binary", "duration": DURATION, "direction": DIRECTION},
                {"value": AMOUNT, "asset": ASSET, "side": DIRECTION, "duration": DURATION},
            ]
            for kw in kw_variants:
                print(f"Trying {method_name} with kwargs: {list(kw.keys())}")
                ok, res = await try_call(method, **kw)
                if ok:
                    print(f"Success (kw) with {method_name} ->", res)
                    order_result = res
                    break
            else:
                print(f"{method_name} didn't accept attempted signatures; last error:", res)
                order_result = None

            if order_result is not None:
                break

    if not tried:
        print("No candidate order methods found on client.")
    else:
        # If we got an order result, attempt to check order status / active orders
        try:
            if hasattr(client, "check_order_result"):
                print("Calling check_order_result(...) to verify...")
                try:
                    ok, info = await try_call(client.check_order_result, order_result)
                    print("check_order_result:", ok, info)
                except Exception as e:
                    print("check_order_result call failed:", e)

            if hasattr(client, "get_active_orders"):
                print("Fetching active orders...")
                ok, active = await try_call(client.get_active_orders)
                if ok:
                    print("Active orders:", active)
                else:
                    print("get_active_orders error:", active)
        except Exception as e:
            print("Post-order checks failed:", e)

    # read balance if method exists
    try:
        if hasattr(client, "get_balance"):
            bal = await client.get_balance()
            print("Balance:", bal)
    except Exception as e:
        print("get_balance failed:", e)

    # disconnect
    try:
        await client.disconnect()
    except Exception:
        # some forks use close/disconnect variations
        try:
            await client.close()
        except Exception:
            pass

    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
