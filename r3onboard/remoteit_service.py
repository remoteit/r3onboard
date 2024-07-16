import json
import os
import asyncio
import logging
import re
import subprocess
import threading


# Enum for Registration Status
class RegistrationStatus:
    UNREGISTERED = "UNREGISTERED"
    REGISTERING = "REGISTERING"
    REGISTERED = "REGISTERED"


class RemoteItService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(name=__name__)
        self._registration_status = RegistrationStatus.UNREGISTERED
        self._device_id: str | None = None
        self.on_change_registration = lambda key, value: None

    @property
    def registration_status(self) -> str:
        return self._registration_status

    @registration_status.setter
    def registration_status(self, value: str) -> None:
        if value != self._registration_status:
            self._registration_status = value
            self.on_change_registration("registration_status", value)

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @device_id.setter
    def device_id(self, value: str) -> None:
        if value != self._device_id:
            self._device_id = value
            self.on_change_registration("device_id", value)

    def set_registered(self, device_id: str) -> None:
        if (
            self._registration_status == RegistrationStatus.REGISTERED
            and self._device_id == device_id
        ):
            return
        self._registration_status = RegistrationStatus.REGISTERED
        self._device_id = device_id
        self.on_change_registration(
            "registration_status", RegistrationStatus.REGISTERED
        )

    # Is Registered function
    # Check if the device is registered
    def is_registered(self) -> bool:
        return self.registration_status == RegistrationStatus.REGISTERED

    async def monitor_remoteit_logs(self) -> None:
        self.logger.info("Monitoring remoteit-agent logs")

        command = ["journalctl", "-f"]
        process = await asyncio.create_subprocess_exec(
            *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        while True:
            if process.stdout is not None:
                line = await process.stdout.readline()
                line_str = line.decode()
                line_str = line_str.strip()
                if not line_str:
                    break
                if "Updating remote.it configuration." in line_str:
                    self.registration_status = "REGISTERING"
                elif "Using device uid =" in line_str:
                    self.check_device_registration()

    def check_device_registration(
        self, config_file: str = "/etc/remoteit/config.json"
    ) -> None:
        # Check if the configuration file exists
        if os.path.isfile(config_file):
            try:
                # Try to open and read the configuration file
                with open(config_file, "r") as file:
                    config = json.load(file)

                # Try to extract the device id
                device_id = config.get("device", {}).get("id")

                if device_id:
                    # Device id found, return True along with the ID
                    self.logger.info(f"Device Registered: {device_id}")
                    self.set_registered(device_id)
                else:
                    # Device id not found in JSON
                    self.logger.warn("Device id not found in JSON")
                    self.registration_status = RegistrationStatus.UNREGISTERED
                    self.device_id = None

            except (json.JSONDecodeError, KeyError, IOError) as e:
                # Handle JSON parsing errors or file reading errors
                self.logger.warn(f"Error reading config file: {e}")
                self.registration_status = RegistrationStatus.UNREGISTERED
                self.device_id = None

        else:
            # No configuration file found
            self.logger.warn("No configuration file found")
            self.registration_status = RegistrationStatus.UNREGISTERED
            self.device_id = None

    async def install_remoteit_agent_async(
        self, registrationCode: str
    ) -> tuple[str, str]:
        # Prepare the command string with the registration code
        self.registration_status = RegistrationStatus.REGISTERING
        command = (
            f'R3_REGISTRATION_CODE="{registrationCode}" '
            'sh -c "$(curl -L https://downloads.remote.it/remoteit/install_agent.sh)"'
        )

        # Create the subprocess using asyncio's subprocess functions
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # You can wait for the process to complete, or handle it in another way depending on your needs
        stdout, stderr = await process.communicate()

        self.check_device_registration()

        # Here we simply return stdout and stderr, you might want to handle them differently
        return stdout.decode(), stderr.decode()
