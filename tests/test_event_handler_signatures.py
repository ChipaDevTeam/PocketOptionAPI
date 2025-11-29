"""
Test script for verifying event handler signatures are correct
This specifically tests the fix for issue #43: 
"Error in event handler for connected: AsyncPocketOptionClient._on_keep_alive_connected() 
takes 1 positional argument but 2 were given"
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_client():
    """Create a mock client for testing event handlers"""
    from pocketoptionapi_async.client import AsyncPocketOptionClient
    
    with patch.object(AsyncPocketOptionClient, '_setup_event_handlers'):
        client = AsyncPocketOptionClient(
            ssid='42["auth",{"session":"test","isDemo":1,"uid":0,"platform":1}]',
            is_demo=True,
            enable_logging=False,
        )
    return client


class TestEventHandlerSignatures:
    """Test that event handlers accept the correct parameters"""

    @pytest.mark.asyncio
    async def test_on_keep_alive_connected_accepts_data_parameter(self, mock_client):
        """Test that _on_keep_alive_connected accepts a data parameter"""
        # Mock _initialize_data to prevent actual initialization
        mock_client._initialize_data = AsyncMock()
        
        # Call with data parameter (as ConnectionKeepAlive._emit_event would)
        data = {"url": "wss://test.example.com", "region": "TEST"}
        
        # This should not raise TypeError
        await mock_client._on_keep_alive_connected(data)
        
        # Verify _initialize_data was called
        mock_client._initialize_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_keep_alive_connected_accepts_no_data(self, mock_client):
        """Test that _on_keep_alive_connected works without data parameter"""
        mock_client._initialize_data = AsyncMock()
        
        # Call without data parameter (default value)
        await mock_client._on_keep_alive_connected()
        
        mock_client._initialize_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_keep_alive_reconnected_accepts_data_parameter(self, mock_client):
        """Test that _on_keep_alive_reconnected accepts a data parameter"""
        mock_client._initialize_data = AsyncMock()
        
        # Call with data parameter (as ConnectionKeepAlive._emit_event would)
        data = {"attempt": 1, "url": "wss://test.example.com"}
        
        # This should not raise TypeError
        await mock_client._on_keep_alive_reconnected(data)
        
        mock_client._initialize_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_keep_alive_reconnected_accepts_no_data(self, mock_client):
        """Test that _on_keep_alive_reconnected works without data parameter"""
        mock_client._initialize_data = AsyncMock()
        
        await mock_client._on_keep_alive_reconnected()
        
        mock_client._initialize_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_keep_alive_message_accepts_data_dict(self, mock_client):
        """Test that _on_keep_alive_message accepts a data dictionary"""
        # Call with data dictionary (as ConnectionKeepAlive._emit_event would)
        data = {"message": "42[\"test\", {}]"}
        
        # This should not raise TypeError
        await mock_client._on_keep_alive_message(data)

    @pytest.mark.asyncio
    async def test_on_keep_alive_message_processes_message_correctly(self, mock_client):
        """Test that _on_keep_alive_message correctly extracts and processes messages"""
        mock_client._on_authenticated = AsyncMock()
        
        # Simulate a message from ConnectionKeepAlive
        data = {"message": '42["authenticated", {"status": "success"}]'}
        
        await mock_client._on_keep_alive_message(data)
        
        # Verify authentication handler was called
        mock_client._on_authenticated.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_keep_alive_message_handles_empty_data(self, mock_client):
        """Test that _on_keep_alive_message handles empty or None data"""
        # Should not raise an exception
        await mock_client._on_keep_alive_message(None)
        await mock_client._on_keep_alive_message({})
        await mock_client._on_keep_alive_message({"message": ""})

    @pytest.mark.asyncio
    async def test_event_handler_integration_with_emit(self):
        """Test that event handlers work correctly when called through _emit_event pattern"""
        from pocketoptionapi_async.client import AsyncPocketOptionClient
        
        with patch.object(AsyncPocketOptionClient, '_setup_event_handlers'):
            client = AsyncPocketOptionClient(
                ssid='42["auth",{"session":"test","isDemo":1,"uid":0,"platform":1}]',
                is_demo=True,
                enable_logging=False,
            )
        
        client._initialize_data = AsyncMock()
        
        # Simulate the emit pattern from ConnectionKeepAlive._emit_event
        handlers = [client._on_keep_alive_connected, client._on_keep_alive_reconnected]
        
        for handler in handlers:
            data = {"test": "data"}
            # This should work without raising TypeError
            if asyncio.iscoroutinefunction(handler):
                await handler(data)
            else:
                handler(data)


class TestEventCallbackPropagation:
    """Test that events are properly propagated to registered callbacks"""

    @pytest.mark.asyncio
    async def test_connected_event_callback_called(self, mock_client):
        """Test that connected event callback is called after _on_keep_alive_connected"""
        mock_client._initialize_data = AsyncMock()
        
        callback_called = False
        
        def on_connected():
            nonlocal callback_called
            callback_called = True
        
        mock_client.add_event_callback("connected", on_connected)
        
        await mock_client._on_keep_alive_connected({"url": "test", "region": "TEST"})
        
        assert callback_called is True

    @pytest.mark.asyncio
    async def test_reconnected_event_callback_called(self, mock_client):
        """Test that reconnected event callback is called after _on_keep_alive_reconnected"""
        mock_client._initialize_data = AsyncMock()
        
        callback_called = False
        
        def on_reconnected():
            nonlocal callback_called
            callback_called = True
        
        mock_client.add_event_callback("reconnected", on_reconnected)
        
        await mock_client._on_keep_alive_reconnected({"attempt": 1, "url": "test"})
        
        assert callback_called is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
