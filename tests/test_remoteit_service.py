import sys

print(sys.path)

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from r3onboard.remoteit_service import (
    RemoteItService,
    RegistrationStatus,
)


class TestRemoteItService:
    def setup_method(self, method):
        self.remoteit = RemoteItService()

    def test_property_setters(self):
        with patch.object(
            self.remoteit, "on_change_registration"
        ) as mock_notifyRegistration:
            self.remoteit.registration_status = RegistrationStatus.REGISTERED
            assert self.remoteit.registration_status == RegistrationStatus.REGISTERED
            mock_notifyRegistration.assert_called_once()

        with patch.object(
            self.remoteit, "on_change_registration"
        ) as mock_notifyRegistration:
            self.remoteit.device_id = "TestDeviceID"
            assert self.remoteit.device_id == "TestDeviceID"
            mock_notifyRegistration.assert_called_once()

    @patch("r3onboard.remoteit_service.os.path.isfile")
    @patch("r3onboard.remoteit_service.open")
    @patch("r3onboard.remoteit_service.json.load")
    def test_check_device_registration(self, mock_json_load, mock_open, mock_isfile):
        mock_isfile.return_value = True
        mock_open.return_value = MagicMock()
        mock_json_load.return_value = {"device": {"id": "TestDeviceID"}}

        self.remoteit.check_device_registration()
        assert self.remoteit.registration_status == RegistrationStatus.REGISTERED
        assert self.remoteit.device_id == "TestDeviceID"

    @pytest.mark.asyncio
    @patch(
        "r3onboard.remoteit_service.asyncio.create_subprocess_shell",
        new_callable=AsyncMock,
    )
    async def test_install_remoteit_agent_async(self, mock_create_subprocess_shell):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_create_subprocess_shell.return_value = mock_proc

        with patch.object(
            self.remoteit, "check_device_registration"
        ) as mock_check_device_registration:
            await self.remoteit.install_remoteit_agent_async("TestCode")
            assert self.remoteit.registration_status == RegistrationStatus.REGISTERING
            mock_check_device_registration.assert_called_once()


if __name__ == "__main__":
    pytest.main()
