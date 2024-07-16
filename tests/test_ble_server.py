import sys

print(sys.path)

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from r3onboard.ble_server import (
    BleServer,
)


class TestBLEServer:
    @patch("r3onboard.ble_server.BlessServer")
    def setup_method(self, method, MockBlessServer):
        self.server = BleServer()
        self.server.server = MockBlessServer()


if __name__ == "__main__":
    pytest.main()
