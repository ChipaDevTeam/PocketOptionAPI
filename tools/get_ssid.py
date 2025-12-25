import os
import json
import time
import re
import logging
from typing import cast, List, Dict, Any
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver import get_driver

# Configure logging for this script to provide clear, structured output.
# Using a simpler format for better readability by end users.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def save_to_env(key: str, value: str):
    """
    Saves or updates a key-value pair in the .env file.
    If the key already exists, its value is updated. Otherwise, the new key-value pair is added.

    Args:
        key: The environment variable key (e.g., "SSID").
        value: The value to be associated with the key.
    """
    env_path = os.path.join(os.getcwd(), ".env")
    lines = []
    found = False

    # Read existing .env file content
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    # Update existing key
                    lines.append(f'{key}="{value}"\n')
                    found = True
                else:
                    lines.append(line)

    if not found:
        # Add new key if not found
        lines.append(f'{key}="{value}"\n')

    # Write updated content back to .env file
    with open(env_path, "w") as f:
        f.writelines(lines)
    logger.info(f"Successfully saved {key} to .env file.")


def get_pocketoption_ssid():
    """
    Automates the process of logging into PocketOption, navigating to a specific cabinet page,
    and then scraping WebSocket traffic to extract the session ID (SSID).
    The extracted SSID is then saved to the .env file.
    
    Instructions:
    1. Run this script
    2. A Chrome browser will open and navigate to PocketOption login page
    3. Log in manually with your credentials
    4. Wait for the script to automatically extract your SSID
    5. The SSID will be saved to .env file in the current directory
    """
    driver = None
    try:
        logger.info("=" * 80)
        logger.info("PocketOption SSID Extractor Tool")
        logger.info("=" * 80)
        logger.info("INSTRUCTIONS:")
        logger.info("1. A Chrome browser will open shortly")
        logger.info("2. Please log in to PocketOption with your credentials")
        logger.info("3. Wait for automatic redirection to the trading cabinet")
        logger.info("4. The script will extract your SSID automatically")
        logger.info("=" * 80)
        
        # Initialize the Selenium WebDriver using the helper function from driver.py.
        # This ensures the browser profile is persistent for easier logins.
        driver = get_driver("chrome")
        login_url = "https://pocketoption.com/en/login"
        cabinet_base_url = "https://pocketoption.com/en/cabinet"
        target_cabinet_url = "https://pocketoption.com/en/cabinet/demo-quick-high-low/"
        
        # Flexible regex pattern to capture auth messages in various formats
        # This pattern handles:
        # - Optional isFastHistory field
        # - Any field order in the JSON object
        # - Various session string formats
        ssid_pattern = r'42\["auth",(\{(?:[^{}]|\{[^}]*\})*\})\]'

        logger.info(f"Navigating to login page: {login_url}")
        driver.get(login_url)

        # Wait indefinitely for the user to manually log in and be redirected to the cabinet base page.
        # This uses an explicit wait condition to check if the current URL contains the cabinet_base_url.
        logger.info(f"Waiting for user to login and redirect to {cabinet_base_url}...")
        logger.info("Please complete the login in the browser window...")
        WebDriverWait(driver, 9999).until(EC.url_contains(cabinet_base_url))
        logger.info("Login successful. Redirected to cabinet base page.")

        # Now navigate to the specific target URL within the cabinet.
        logger.info(f"Navigating to target cabinet page: {target_cabinet_url}")
        driver.get(target_cabinet_url)

        # Wait for the target cabinet URL to be fully loaded.
        # This ensures that any WebSocket connections initiated on this page are established.
        WebDriverWait(driver, 60).until(EC.url_contains(target_cabinet_url))
        logger.info("Successfully navigated to the target cabinet page.")

        # Give the page more time to establish WebSocket connections and capture auth messages
        # Increased from 5 to 10 seconds to ensure auth messages are captured
        logger.info("Waiting for WebSocket connections to establish...")
        time.sleep(10)

        # Retrieve performance logs which include network requests and WebSocket frames.
        # These logs are crucial for capturing the raw WebSocket messages.
        get_log = getattr(driver, "get_log", None)
        if not callable(get_log):
            raise AttributeError(
                "Your WebDriver does not support get_log(). Make sure you are using Chrome with performance logging enabled."
            )
        performance_logs = cast(List[Dict[str, Any]], get_log("performance"))
        logger.info(f"Collected {len(performance_logs)} performance log entries.")

        found_full_ssid_string = None
        websocket_frames_found = 0
        auth_messages_found = 0
        
        # Iterate through the performance logs to find WebSocket frames.
        for entry in performance_logs:
            try:
                message = json.loads(entry["message"])
                # Check if the log entry is a WebSocket frame (either sent or received)
                # and contains the desired payload data.
                if (
                    message["message"]["method"] == "Network.webSocketFrameReceived"
                    or message["message"]["method"] == "Network.webSocketFrameSent"
                ):
                    websocket_frames_found += 1
                    payload_data = message["message"]["params"]["response"]["payloadData"]
                    
                    # Check if this is an auth-related message
                    if '"auth"' in payload_data:
                        auth_messages_found += 1
                        logger.debug(f"Found auth message: {payload_data[:200]}...")
                    
                    # Attempt to find the full SSID string using the defined regex pattern.
                    match = re.search(ssid_pattern, payload_data)
                    if match:
                        # Reconstruct the full SSID string
                        json_part = match.group(1)
                        found_full_ssid_string = f'42["auth",{json_part}]'
                        
                        # Validate that it contains required fields
                        try:
                            data = json.loads(json_part)
                            if "session" in data and "uid" in data:
                                logger.info(
                                    f"Found valid SSID string in WebSocket payload"
                                )
                                logger.info(f"SSID preview: 42[\"auth\",{{\"session\":\"***\",\"uid\":{data.get('uid')},\"isDemo\":{data.get('isDemo', 'N/A')},...}}]")
                                # Break after finding the first valid match
                                break
                            else:
                                logger.warning(f"Found auth message but missing required fields: {list(data.keys())}")
                                found_full_ssid_string = None
                        except json.JSONDecodeError as e:
                            logger.warning(f"Found auth pattern but invalid JSON: {e}")
                            found_full_ssid_string = None
            except Exception as e:
                logger.debug(f"Error processing log entry: {e}")
                continue
        
        logger.info(f"Statistics: Found {websocket_frames_found} WebSocket frames, {auth_messages_found} auth messages")

        if found_full_ssid_string:
            # Save the extracted full SSID string to the .env file.
            save_to_env("SSID", found_full_ssid_string)
            logger.info("=" * 80)
            logger.info("SUCCESS! SSID successfully extracted and saved to .env file.")
            logger.info("You can now use this SSID in your PocketOption API scripts.")
            logger.info("=" * 80)
        else:
            logger.warning("=" * 80)
            logger.warning(
                "SSID string pattern not found in WebSocket logs after login."
            )
            logger.warning("Possible reasons:")
            logger.warning("1. WebSocket connection was not established yet (try running again)")
            logger.warning("2. You may need to navigate to a trading page manually")
            logger.warning("3. The auth message format has changed")
            logger.warning("")
            logger.warning("Alternative method to get SSID:")
            logger.warning("1. Open PocketOption in Chrome")
            logger.warning("2. Open Developer Tools (F12)")
            logger.warning("3. Go to Network tab and filter by 'WS' (WebSocket)")
            logger.warning("4. Look for messages containing '42[\"auth\"'")
            logger.warning("5. Copy the complete message including the 42[\"auth\",{...}] format")
            logger.warning("=" * 80)

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
    finally:
        # Ensure the WebDriver is closed even if an error occurs to free up resources.
        if driver:
            driver.quit()
            logger.info("WebDriver closed.")


if __name__ == "__main__":
    get_pocketoption_ssid()
