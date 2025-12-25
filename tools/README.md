# PocketOption Tools

This directory contains utility tools for working with the PocketOption API.

## get_ssid.py - SSID Extraction Tool

This tool automatically extracts your PocketOption session ID (SSID) by monitoring WebSocket traffic during login.

### What is SSID?

SSID (Session ID) is the authentication token required to use the PocketOption API. It's a string that looks like:

```
42["auth",{"session":"your-session-here","isDemo":1,"uid":12345,"platform":1}]
```

### Prerequisites

Before running the tool, make sure you have the required dependencies installed:

```bash
pip install -r requirements.txt
```

The tool requires:
- `selenium>=4.0.0`
- `webdriver-manager>=4.0.0`
- Chrome browser installed on your system

### How to Use

1. **Navigate to the tools directory:**
   ```bash
   cd tools
   ```

2. **Run the script:**
   ```bash
   python get_ssid.py
   ```

3. **Follow the on-screen instructions:**
   - A Chrome browser window will open automatically
   - Navigate to the PocketOption login page
   - Log in with your credentials
   - Wait for the automatic redirection to the trading cabinet
   - The script will automatically extract and save your SSID

4. **Find your SSID:**
   - The SSID will be saved to a `.env` file in the current directory
   - You can now use this SSID in your API scripts

### Expected Output

When successful, you'll see:

```
2025-12-25 10:30:15 - INFO - ================================================================================
2025-12-25 10:30:15 - INFO - PocketOption SSID Extractor Tool
2025-12-25 10:30:15 - INFO - ================================================================================
2025-12-25 10:30:15 - INFO - INSTRUCTIONS:
2025-12-25 10:30:15 - INFO - 1. A Chrome browser will open shortly
2025-12-25 10:30:15 - INFO - 2. Please log in to PocketOption with your credentials
...
2025-12-25 10:31:45 - INFO - Found valid SSID string in WebSocket payload
2025-12-25 10:31:45 - INFO - ================================================================================
2025-12-25 10:31:45 - INFO - SUCCESS! SSID successfully extracted and saved to .env file.
2025-12-25 10:31:45 - INFO - You can now use this SSID in your PocketOption API scripts.
2025-12-25 10:31:45 - INFO - ================================================================================
```

### Troubleshooting

#### "SSID string pattern not found in WebSocket logs"

If you see this warning, try the following:

1. **Run the script again** - Sometimes the WebSocket connection timing can vary
2. **Manual extraction method:**
   - Open PocketOption in Chrome
   - Press F12 to open Developer Tools
   - Go to the "Network" tab
   - Filter by "WS" (WebSocket)
   - Log in and navigate to a trading page
   - Look for messages containing `42["auth"`
   - Copy the complete message including the `42["auth",{...}]` format
   - Save it to your `.env` file as: `SSID="your-copied-message"`

#### Browser doesn't open

- Make sure Chrome is installed on your system
- The script uses `webdriver-manager` which automatically downloads ChromeDriver
- Check your internet connection

#### Other issues

- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Check the console output for specific error messages
- Try running the script with Python 3.8 or higher

### Using Your SSID

Once you have your SSID, you can use it in your API scripts:

```python
from pocketoptionapi_async import AsyncPocketOptionClient
import asyncio

async def main():
    # Load SSID from environment or paste it directly
    SSID = "42[\"auth\",{\"session\":\"...\",\"isDemo\":1,\"uid\":12345,\"platform\":1}]"
    
    client = AsyncPocketOptionClient(SSID, is_demo=True)
    await client.connect()
    
    balance = await client.get_balance()
    print(f"Balance: {balance.balance} {balance.currency}")
    
    await client.disconnect()

asyncio.run(main())
```

### Security Note

Your SSID is sensitive information that grants access to your PocketOption account. Keep it secure and never share it publicly. The `.env` file should be added to `.gitignore` to prevent accidental commits.
