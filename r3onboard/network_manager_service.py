import asyncio
import subprocess
import logging
import json
from typing import Dict, List, Tuple, Callable

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import BusType


# Enum for Scan Status
class ScanStatus:
    SCANNING = "SCANNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# Enum for WiFi Status
class NetworkStatus:
    CONNECTED = "CONNECTED"
    NOT_CONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    FAILED_START = "FAILED_START"
    INVALID_PASSWORD = "INVALID_PASSWORD"
    INVALID_SSID = "INVALID_SSID"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class NetworkManagerService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(name=__name__)
        self.networks: List[Tuple[str, int]] = []
        self._scan_status = ScanStatus.SCANNING
        self._wifi_status = NetworkStatus.NOT_CONNECTED
        self._ethernet_status = NetworkStatus.NOT_CONNECTED
        self._error: str | None = None
        self._desired_ssid: str | None = None
        self.on_change_network: Callable[[str, str], None] = lambda x, y: None

    @property
    def desired_ssid(self) -> str | None:
        return self._desired_ssid

    @desired_ssid.setter
    def desired_ssid(self, value: str) -> None:
        self._desired_ssid = value
        self.on_change_network("desired_ssid", value)

    @property
    def scan_status(self) -> str:
        return self._scan_status

    @scan_status.setter
    def scan_status(self, value: str) -> None:
        self._scan_status = value
        self.on_change_network("scan_status", value)

    @property
    def wifi_status(self) -> str:
        return self._wifi_status

    @wifi_status.setter
    def wifi_status(self, value: str) -> None:
        self._wifi_status = value
        self.on_change_network("wifi_status", value)

    @property
    def ethernet_status(self) -> str:
        return self._ethernet_status

    @ethernet_status.setter
    def ethernet_status(self, value: str) -> None:
        self._ethernet_status = value
        self.on_change_network("ethernet_status", value)

    @property
    def error(self) -> str | None:
        return self._error

    @error.setter
    def error(self, value: str) -> None:
        self._error = value
        self.on_change_network("error", value)

    def get_current_ssid(self) -> str:
        try:
            self.logger.debug("Getting current SSID")

            iw_output = subprocess.run(["ip", "link"], capture_output=True, text=True)
            lines = iw_output.stdout.splitlines()
            interface = None
            for line in lines:
                if "state UP" in line and "wlan" in line:
                    interface = line.split(":")[
                        1
                    ].strip()  # Extracting the interface name
                    break

            if interface is None:
                # return "No active wireless interface found."
                return ""

            # Fetching the SSID using the identified wireless interface
            result = subprocess.run(
                ["iw", "dev", interface, "link"], capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                if "SSID" in line:
                    return line.split("SSID:")[1].strip()  # Extracting the SSID

            return ""
        except subprocess.CalledProcessError as e:
            return f"An error occurred: {str(e)}"

    async def scan_wifi_networks(self) -> None:
        retries = 5
        for attempt in range(retries):
            self.logger.debug("attempt")
            self.logger.debug(attempt)
            self.logger.debug("retries")
            self.logger.debug(retries)
            try:
                self.logger.debug("Scanning networks")
                self.scan_status = ScanStatus.SCANNING

                # # Force a rescan
                # rescan_process = await asyncio.create_subprocess_exec(
                #     "nmcli",
                #     "device",
                #     "wifi",
                #     "rescan",
                #     stdout=asyncio.subprocess.PIPE,
                #     stderr=asyncio.subprocess.PIPE,
                # )
                # # await rescan_process.communicate()
                # rescan_stdout, rescan_stderr = await rescan_process.communicate()
                # self.logger.debug(f"Rescan stdout: {rescan_stdout.decode('utf-8')}")
                # self.logger.debug(f"Rescan stderr: {rescan_stderr.decode('utf-8')}")

                process = await asyncio.create_subprocess_exec(
                    "sudo",
                    "nmcli",
                    "-t",
                    "-f",
                    "ssid,signal",
                    "device",
                    "wifi",
                    "list",
                    "--rescan",
                    "yes",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                # stdout, stderr = await process.communicate()
                stdout, stderr = await process.communicate()
                self.logger.debug(f"Scan stdout: {stdout.decode('utf-8')}")
                self.logger.debug(f"Scan stderr: {stderr.decode('utf-8')}")
                if process.returncode == 0 and stdout != b"":
                    stdout_text = stdout.decode("utf-8")
                    networks_dict: Dict[str, int] = (
                        {}
                    )  # Local dictionary to hold the network data

                    for line in stdout_text.splitlines():
                        fields = line.split(":")
                        if len(fields) == 2:
                            ssid, signal_str = fields
                            if ssid != "":
                                signal = int(signal_str)
                                if (
                                    ssid not in networks_dict
                                    or networks_dict[ssid] < signal
                                ):
                                    networks_dict[ssid] = signal

                    self.networks = sorted(
                        networks_dict.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )
                    self.scan_status = ScanStatus.COMPLETE
                    self.logger.debug("Sorted Networks:")
                    for essid, signal in self.networks:
                        self.logger.debug(f"ESSID: {essid}, Signal: {signal} dBm")
                    break
                else:
                    if attempt == retries - 1:
                        self.logger.debug("Failed to scan networks with error.")
                        self.scan_status = ScanStatus.FAILED
                        break
                    self.logger.error(
                        f'Error scanning networks: {stderr.decode("utf-8")}'
                    )
                    await asyncio.sleep(2)  # Wait for 2 seconds before retrying
            except Exception as e:
                if attempt == retries - 1:
                    self.logger.debug("Failed to scan networks with exception.")
                    self.scan_status = ScanStatus.FAILED
                    break
                self.logger.error(f"Exception while scanning networks: {str(e)}")
                await asyncio.sleep(5)

    def get_wifi_json(self) -> str:
        # Return the list of all networks as a JSON array
        networks_list = [
            {"ssid": ssid, "signal": signal} for ssid, signal in self.networks
        ]
        return json.dumps(networks_list)

    def is_wifi_connected(self) -> bool:
        self.logger.debug("Checking connection status in function.")

        try:
            process = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,STATE", "dev", "status"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            self.process_returncode(e.stderr)
            return False

        output = process.stdout.decode().strip()
        for line in output.split("\n"):
            device, state = line.split(":")
            # Check if the device is a wlan interface and if its state is connected
            if "wlan" in device and state == "connected":
                self.wifi_status = NetworkStatus.CONNECTED
                self.logger.info("Successfully connected to the WiFi network.")
                return True

        self.logger.debug("Disconnected from the WiFi network.")
        self.wifi_status = NetworkStatus.NOT_CONNECTED
        return False

    def is_ethernet_connected(self) -> bool:
        self.logger.debug("Checking Ethernet connection status in function.")

        try:
            process = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,STATE", "dev", "status"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            self.process_returncode(e.stderr)
            return False

        output = process.stdout.decode().strip()
        for line in output.split("\n"):
            device, state = line.split(":")
            # Check if the device is an Ethernet interface and if its state is connected
            self.logger.debug(f"Device: {device}, State: {state}")
            if "eth" in device and state == "connected":
                self.ethernet_status = NetworkStatus.CONNECTED
                self.logger.info("Successfully connected to the Ethernet network.")
                return True

        self.logger.debug("Disconnected from the Ethernet network.")
        self.ethernet_status = NetworkStatus.NOT_CONNECTED
        return False

    def process_returncode(self, stderr: bytes) -> None:
        error_message = stderr.decode().strip()
        if "No network with SSID" in error_message:
            self.logger.debug("SSID does not exist.")
            self.wifi_status = NetworkStatus.INVALID_SSID
            self.error = NetworkStatus.INVALID_SSID
        elif "Secrets were required" in error_message:
            self.logger.debug("Bad password or authentication failure.")
            self.wifi_status = NetworkStatus.INVALID_PASSWORD
            self.error = NetworkStatus.INVALID_PASSWORD
        else:
            self.logger.debug(f"Failed to connect to the WiFi network: {error_message}")
            self.wifi_status = NetworkStatus.FAILED_START
            self.error = NetworkStatus.FAILED_START
            self.restart_network_manager()
        self.is_wifi_connected()
        self.is_ethernet_connected()

    def restart_network_manager(self) -> None:
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", "NetworkManager"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.logger.info("NetworkManager restarted successfully.")
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"Failed to restart NetworkManager: {e.stderr.decode().strip()}"
            )

    async def configure_wifi_async(self, ssid: str | None, password: str) -> bool:
        if ssid:
            self.wifi_status = NetworkStatus.CONNECTING
            self.desired_ssid = ssid
            process = await asyncio.create_subprocess_exec(
                "nmcli",
                "dev",
                "wifi",
                "connect",
                ssid,
                "password",
                password,
                "hidden",
                "yes",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await process.communicate()

            if process.returncode != 0:
                self.process_returncode(stderr)
                return False
        else:
            self.logger.debug("SSID is None")
            return False

        self.logger.debug("Connection attempt started.")
        return True

    def create_state_changed_handler(
        self, device_type: str, device_interface: str
    ) -> Callable[[int, int, int], None]:
        def state_changed_handler(state: int, _: int, reason: int) -> None:
            status = None
            if state == 100:
                self.logger.debug(
                    f"{device_type} device {device_interface} is up (activated)."
                )
                status = NetworkStatus.CONNECTED
            elif state == 40:
                self.logger.debug(
                    f"{device_type} device {device_interface} is connecting."
                )
                status = NetworkStatus.CONNECTING
            elif state == 30:
                self.logger.debug(
                    f"{device_type} device {device_interface} is down (disconnected)."
                )
                status = NetworkStatus.NOT_CONNECTED
            elif state == 20:
                self.logger.debug(
                    f"{device_type} device {device_interface} is disconnected."
                )
                status = NetworkStatus.NOT_CONNECTED
            else:
                self.logger.debug(
                    f"{device_type} device {device_interface} changed state to {state} with reason: {reason}."
                )

            if reason == (2, 7):  # Invalid SSID
                self.logger.debug(
                    f"{device_type} device {device_interface}: Connection failed: Invalid SSID."
                )
                self.error = NetworkStatus.INVALID_SSID
            elif reason == (2, 8):  # Invalid password
                self.logger.debug(
                    f"{device_type} device {device_interface}: Connection failed: Invalid password."
                )
                self.error = NetworkStatus.INVALID_PASSWORD
            if status:
                if "wlan" in device_interface:
                    self.wifi_status = status
                elif "eth" in device_interface:
                    self.ethernet_status = status

        return state_changed_handler

    async def monitor_wifi_status(self) -> None:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        introspection = await bus.introspect(
            "org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager"
        )
        proxy_object = bus.get_proxy_object(
            "org.freedesktop.NetworkManager",
            "/org/freedesktop/NetworkManager",
            introspection,
        )
        nm_interface = proxy_object.get_interface("org.freedesktop.NetworkManager")
        devices = await nm_interface.call_get_devices()  # type: ignore

        for device_path in devices:
            introspection = await bus.introspect(
                "org.freedesktop.NetworkManager", device_path
            )
            device_object = bus.get_proxy_object(
                "org.freedesktop.NetworkManager", device_path, introspection
            )
            device_interface = device_object.get_interface(
                "org.freedesktop.NetworkManager.Device"
            )

            device_type_variant = await device_interface.get_device_type()  # type: ignore
            device_type = (
                "eth"
                if device_type_variant == 1
                else "wlan" if device_type_variant == 2 else None
            )
            if device_type:
                device_interface_name = await device_interface.get_interface()  # type: ignore
                self.logger.debug(
                    f"Monitoring {device_type} device: {device_interface_name}"
                )

                properties_changed_handler = self.create_state_changed_handler(
                    device_type, device_interface_name
                )
                device_interface.on_state_changed(properties_changed_handler)  # type: ignore
