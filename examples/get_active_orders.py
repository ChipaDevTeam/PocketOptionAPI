from pocketoptionapi_async import AsyncPocketOptionClient

async def main():
    SSID = input("Enter your SSID: ")
    client = AsyncPocketOptionClient(SSID, is_demo=True, enable_logging=False)
    await client.connect()

    orders = await client.get_active_orders()
    if orders:
        print("Active Orders:")
        for order in orders:
            print(f"Order ID: {order.order_id}, Amount: {order.amount}, Status: {order.status}")
    else:
        print("No active orders found.")

    await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())