"""
Test script to verify the check_win functionality
Tests that the server ID to request ID mapping works correctly
"""

import asyncio
from datetime import datetime, timedelta
from pocketoptionapi_async import AsyncPocketOptionClient, OrderDirection
from pocketoptionapi_async.models import OrderResult, OrderStatus


async def test_check_win_id_mapping():
    """Test that server deal IDs are properly mapped to client request IDs"""
    
    # Create a client with a dummy SSID (we won't connect, just test internal logic)
    dummy_ssid = r'42["auth",{"session":"test_session","isDemo":1,"uid":12345,"platform":1}]'
    client = AsyncPocketOptionClient(ssid=dummy_ssid, is_demo=True, enable_logging=False)
    
    print("Testing check_win ID mapping fix")
    print("=" * 50)
    
    # Test 1: Verify the mapping dictionary exists
    print("\nTest 1: Verify _server_id_to_request_id mapping exists")
    assert hasattr(client, '_server_id_to_request_id'), "Client should have _server_id_to_request_id dict"
    assert isinstance(client._server_id_to_request_id, dict), "Should be a dictionary"
    print("   ✅ PASS: _server_id_to_request_id mapping exists")
    
    # Test 2: Simulate order creation with server ID mapping
    print("\nTest 2: Simulate order data with both requestId and server id")
    
    client_request_id = "abc-123-def-456"  # Our client-generated UUID
    server_deal_id = "98765432"  # Server-assigned ID
    
    # Simulate the server response that includes both IDs
    order_data = {
        "requestId": client_request_id,
        "id": server_deal_id,
        "asset": "EURUSD_otc",
        "amount": 10.0,
        "command": 0,  # CALL
        "time": 60
    }
    
    # Call the handler that processes order data
    await client._on_json_data(order_data)
    
    # Verify the order was added to active orders with request_id
    assert client_request_id in client._active_orders, "Order should be in active orders with request_id"
    print(f"   ✅ PASS: Order added to active orders with request_id: {client_request_id}")
    
    # Verify the server ID mapping was created
    assert server_deal_id in client._server_id_to_request_id, "Server ID should be mapped to request_id"
    assert client._server_id_to_request_id[server_deal_id] == client_request_id, "Mapping should point to request_id"
    print(f"   ✅ PASS: Server ID {server_deal_id} mapped to request_id {client_request_id}")
    
    # Test 3: Simulate deal completion using server's deal ID
    print("\nTest 3: Simulate deal completion with server's deal ID")
    
    deal_data = {
        "deals": [
            {
                "id": server_deal_id,  # Server uses its own ID
                "profit": 8.5,
                "payout": 85.0
            }
        ]
    }
    
    # Call the handler that processes deal completion
    await client._on_json_data(deal_data)
    
    # Verify the order was moved from active to completed
    assert client_request_id not in client._active_orders, "Order should be removed from active orders"
    assert client_request_id in client._order_results, "Order should be in order_results with request_id"
    print(f"   ✅ PASS: Order moved from active to completed using request_id")
    
    # Verify the result data is correct
    result = client._order_results[client_request_id]
    assert result.order_id == client_request_id, "Result order_id should match request_id"
    assert result.profit == 8.5, f"Profit should be 8.5, got {result.profit}"
    assert result.status == OrderStatus.WIN, f"Status should be WIN, got {result.status}"
    print(f"   ✅ PASS: Order result has correct profit ({result.profit}) and status ({result.status})")
    
    # Verify the server ID mapping was cleaned up
    assert server_deal_id not in client._server_id_to_request_id, "Server ID mapping should be cleaned up"
    print("   ✅ PASS: Server ID mapping was cleaned up after order completion")
    
    # Test 4: Test check_win function can find the completed order
    print("\nTest 4: Verify check_win finds the completed order")
    
    check_result = await client.check_win(client_request_id, max_wait_time=1.0)
    
    assert check_result is not None, "check_win should return a result"
    assert check_result["completed"], "Order should be completed"
    assert check_result["result"] == "win", f"Result should be 'win', got {check_result['result']}"
    assert check_result["profit"] == 8.5, f"Profit should be 8.5, got {check_result['profit']}"
    print(f"   ✅ PASS: check_win returned correct result: {check_result}")
    
    # Test 5: Test check_order_result function
    print("\nTest 5: Verify check_order_result finds the completed order")
    
    order_result = await client.check_order_result(client_request_id)
    
    assert order_result is not None, "check_order_result should return a result"
    assert order_result.order_id == client_request_id, "Order ID should match"
    assert order_result.profit == 8.5, "Profit should be correct"
    print(f"   ✅ PASS: check_order_result returned correct result")
    
    print("\n" + "=" * 50)
    print("🎉 ALL TESTS PASSED! check_win ID mapping fix is working!")
    
    return True


async def test_check_win_loss_scenario():
    """Test that loss orders are correctly handled"""
    
    dummy_ssid = r'42["auth",{"session":"test_session","isDemo":1,"uid":12345,"platform":1}]'
    client = AsyncPocketOptionClient(ssid=dummy_ssid, is_demo=True, enable_logging=False)
    
    print("\nTesting check_win with loss scenario")
    print("=" * 50)
    
    client_request_id = "loss-order-123"
    server_deal_id = "88888888"
    
    # Create order
    order_data = {
        "requestId": client_request_id,
        "id": server_deal_id,
        "asset": "EURUSD_otc",
        "amount": 10.0,
        "command": 1,  # PUT
        "time": 60
    }
    await client._on_json_data(order_data)
    
    # Complete order with a loss
    deal_data = {
        "deals": [
            {
                "id": server_deal_id,
                "profit": -10.0,  # Lost the trade
                "payout": 0
            }
        ]
    }
    await client._on_json_data(deal_data)
    
    # Verify check_win returns loss
    check_result = await client.check_win(client_request_id, max_wait_time=1.0)
    
    assert check_result["result"] == "loss", f"Result should be 'loss', got {check_result['result']}"
    assert check_result["profit"] == -10.0, f"Profit should be -10.0, got {check_result['profit']}"
    print(f"   ✅ PASS: check_win correctly identifies loss: {check_result}")
    
    return True


async def test_check_win_fallback_without_mapping():
    """Test that check_win still works if server ID happens to match request ID (backward compatibility)"""
    
    dummy_ssid = r'42["auth",{"session":"test_session","isDemo":1,"uid":12345,"platform":1}]'
    client = AsyncPocketOptionClient(ssid=dummy_ssid, is_demo=True, enable_logging=False)
    
    print("\nTesting check_win fallback (no mapping scenario)")
    print("=" * 50)
    
    # Simulate a case where the order was added directly with the server ID
    # (e.g., if server returns request matching what we sent)
    order_id = "direct-order-789"
    
    # Directly add to active orders (simulating order placement)
    order_result = OrderResult(
        order_id=order_id,
        asset="GBPUSD_otc",
        amount=5.0,
        direction=OrderDirection.CALL,
        duration=60,
        status=OrderStatus.ACTIVE,
        placed_at=datetime.now(),
        expires_at=datetime.now() + timedelta(seconds=60),
    )
    client._active_orders[order_id] = order_result
    
    # Complete the order using the same ID (no mapping needed)
    deal_data = {
        "deals": [
            {
                "id": order_id,  # Using the same ID
                "profit": 4.25,
                "payout": 85.0
            }
        ]
    }
    await client._on_json_data(deal_data)
    
    # Verify order was completed
    check_result = await client.check_win(order_id, max_wait_time=1.0)
    
    assert check_result["result"] == "win", f"Result should be 'win', got {check_result['result']}"
    print(f"   ✅ PASS: Fallback without mapping works correctly")
    
    return True


async def run_all_tests():
    """Run all check_win tests"""
    all_passed = True
    
    try:
        all_passed = await test_check_win_id_mapping() and all_passed
    except Exception as e:
        print(f"❌ FAIL: test_check_win_id_mapping - {e}")
        all_passed = False
    
    try:
        all_passed = await test_check_win_loss_scenario() and all_passed
    except Exception as e:
        print(f"❌ FAIL: test_check_win_loss_scenario - {e}")
        all_passed = False
    
    try:
        all_passed = await test_check_win_fallback_without_mapping() and all_passed
    except Exception as e:
        print(f"❌ FAIL: test_check_win_fallback_without_mapping - {e}")
        all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL CHECK_WIN TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(run_all_tests())
