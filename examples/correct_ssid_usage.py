"""
Example demonstrating the correct way to use SSID with PocketOption API

This example shows how to:
1. Get the correct SSID format from browser
2. Initialize the client properly
3. Handle authentication errors
"""

import asyncio
from pocketoptionapi_async import AsyncPocketOptionClient
from pocketoptionapi_async.exceptions import InvalidParameterError, AuthenticationError


async def main():
    print("=" * 70)
    print("PocketOption API - Correct SSID Usage Example")
    print("=" * 70)
    
    print("\n📋 INSTRUCTIONS:")
    print("1. Open PocketOption in your browser (https://pocketoption.com)")
    print("2. Press F12 to open Developer Tools")
    print("3. Go to the Network tab")
    print("4. Filter by 'WS' (WebSocket)")
    print("5. Look for a message starting with: 42[\"auth\",")
    print("6. Copy the ENTIRE message (including 42[\"auth\",{...}])")
    print("\n")
    
    # Example of CORRECT SSID format
    print("✅ CORRECT SSID format:")
    print('   42["auth",{"session":"your_session_here","isDemo":1,"uid":12345,"platform":1}]')
    print("\n")
    
    # Example of WRONG format
    print("❌ WRONG SSID format (just the session ID):")
    print('   dxxxxxxxxxxxxxxxxxxxxxxxxxxxx')
    print("\n")
    
    # Get SSID from user
    ssid_input = input("Enter your SSID (or press Enter to see demo): ").strip()
    
    if not ssid_input:
        print("\n📝 Using demo SSID to show validation...")
        ssid_input = '42["auth",{"session":"demo_session_id","isDemo":1,"uid":12345,"platform":1}]'
    
    print("\n" + "=" * 70)
    
    try:
        print("🔧 Initializing PocketOption client...")
        
        # Create client with SSID
        client = AsyncPocketOptionClient(
            ssid=ssid_input,
            is_demo=True,  # Set to False for live trading
            enable_logging=True  # Set to False to reduce console output
        )
        
        print("✅ Client initialized successfully!")
        print(f"   Session ID: {client.session_id[:20]}...")
        print(f"   User ID: {client.uid}")
        print(f"   Demo mode: {client.is_demo}")
        print("\n")
        
        # Try to connect
        print("🔌 Connecting to PocketOption...")
        connected = await client.connect()
        
        if connected:
            print("✅ Connected successfully!")
            
            # Get balance
            try:
                balance = await client.get_balance()
                print(f"💰 Balance: {balance.balance} {balance.currency}")
            except Exception as e:
                print(f"⚠️  Could not get balance: {e}")
            
            # Disconnect
            await client.disconnect()
            print("✅ Disconnected successfully")
            
        else:
            print("❌ Connection failed")
            print("\n💡 Troubleshooting:")
            print("   • Make sure your SSID is in the correct format")
            print("   • Your SSID might be expired - get a fresh one from browser")
            print("   • Make sure you copied the ENTIRE message including 42[\"auth\",{...}]")
    
    except InvalidParameterError as e:
        print(f"\n❌ SSID Format Error:")
        print(f"   {e}")
        print("\n💡 Make sure you're using the complete SSID format from browser DevTools!")
    
    except AuthenticationError as e:
        print(f"\n❌ Authentication Error:")
        print(f"   {e}")
        print("\n💡 Your SSID might be expired. Get a fresh one from your browser!")
    
    except Exception as e:
        print(f"\n❌ Unexpected Error:")
        print(f"   {type(e).__name__}: {e}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
