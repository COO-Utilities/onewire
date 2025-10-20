"""Perform basic tests."""
from onewire import ONEWIRE

def test_not_connected():
    """Test not connected."""
    controller = ONEWIRE()
    assert not controller.connected

def test_connection_fail():
    """Test connection failure."""
    controller = ONEWIRE()
    controller.connect("127.0.0.1", 9999)
    assert not controller.connected
