import sys

print(sys.path)

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from r3onboard.network_manager_service import (
    NetworkManagerService,
    ScanStatus,
    NetworkStatus,
)


class TestNetworkManagerService:
    def setup_method(self, method):
        self.network_manager = NetworkManagerService()

    def test_property_setters(self):
        with patch.object(self.network_manager, "on_change_network") as mock_notifyWifi:
            self.network_manager.desired_ssid = "TestSSID"
            assert self.network_manager.desired_ssid == "TestSSID"
            mock_notifyWifi.assert_called_once()

        with patch.object(self.network_manager, "on_change_network") as mock_notifyWifi:
            self.network_manager.scan_status = ScanStatus.SCANNING
            assert self.network_manager.scan_status == ScanStatus.SCANNING
            mock_notifyWifi.assert_called_once()

        with patch.object(self.network_manager, "on_change_network") as mock_notifyWifi:
            self.network_manager.wifi_status = NetworkStatus.CONNECTED
            assert self.network_manager.wifi_status == NetworkStatus.CONNECTED
            mock_notifyWifi.assert_called_once()

    @patch("r3onboard.network_manager_service.subprocess.run")
    def test_get_current_ssid(self, mock_run):
        # mock_run.return_value.stdout = "SSID: TestSSID\n"
        mock_run.side_effect = [
            # MagicMock(stdout=""),
            MagicMock(
                stdout="""\
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: eth0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc mq state DOWN mode DEFAULT group default qlen 1000
    link/ether dc:a6:32:93:99:a6 brd ff:ff:ff:ff:ff:ff
3: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP mode DORMANT group default qlen 1000
    link/ether dc:a6:32:93:99:a7 brd ff:ff:ff:ff:ff:ff
"""
            ),
            MagicMock(
                stdout="""\
Connected to 68:d7:9a:4c:28:06 (on wlan0)
	SSID: Artemis
	freq: 2437
	RX: 227930195 bytes (539146 packets)
	TX: 2130923 bytes (20221 packets)
	signal: -55 dBm
	rx bitrate: 65.0 MBit/s
	tx bitrate: 65.0 MBit/s

	bss flags:	short-preamble
	dtim period:	1
	beacon int:	100  
"""
            ),
        ]
        ssid = self.network_manager.get_current_ssid()
        assert ssid == "Artemis"

    @pytest.mark.asyncio
    @patch(
        "r3onboard.network_manager_service.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
    )
    async def test_scan_wifi_networks(self, mock_create_subprocess_exec):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(
                b"""
Artemis:39
""",
                b"",
            )
        )
        mock_create_subprocess_exec.return_value = mock_proc

        await self.network_manager.scan_wifi_networks()
        assert self.network_manager.scan_status == ScanStatus.COMPLETE
        assert self.network_manager.networks == [("Artemis", 39)]

    @patch(
        "r3onboard.network_manager_service.subprocess.run",
    )
    def test_is_wifi_connected(self, mock_run):
        # mock_proc.communicate = AsyncMock(return_value=(b"wlan0:connected\n", b""))
        mock_run.side_effect = [
            MagicMock(stdout=b"wlan0:connected\n"),
        ]

        result = self.network_manager.is_wifi_connected()
        assert result
        assert self.network_manager.wifi_status == NetworkStatus.CONNECTED

    @pytest.mark.asyncio
    @patch(
        "r3onboard.network_manager_service.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
    )
    async def test_configure_wifi_async(self, mock_create_subprocess_exec):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_create_subprocess_exec.return_value = mock_proc

        result = await self.network_manager.configure_wifi_async("TestSSID", "password")
        assert result
        assert self.network_manager.wifi_status == NetworkStatus.CONNECTING


if __name__ == "__main__":
    pytest.main()
