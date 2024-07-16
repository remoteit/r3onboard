import asyncio

import socket
import sys
from configobj import ConfigObj
from dbus_next.aio import MessageBus
from dbus_next import InterfaceNotFoundError, Variant
from dbus_next.constants import BusType
import json
import logging
import os
from typing import Any, Dict, Optional

from bless import BlessServer  # type: ignore
from bless.backends.characteristic import (
    BlessGATTCharacteristic,
    GATTAttributePermissions,
    GATTCharacteristicProperties,
)

from r3onboard.ble_agent_service import BleAgentService

from .network_manager_service import NetworkManagerService
from .remoteit_service import RemoteItService

CONFIG_FILE = "/etc/r3onboard/config.ini"
DEFAULT_CONFIG_FILE = "/etc/r3onboard/config.ini.default"

DEFAULT_SETTINGS = {
    "Settings": {
        "Duration": "5min",
        "LogLevel": "info",
    }
}


# Commands
class Commands:
    WIFI_SCAN = "WIFI_SCAN"
    WIFI_CONNECT = "WIFI_CONNECT"
    R3_REGISTER = "R3_REGISTER"
    IS_CONNECTED = "IS_CONNECTED"


class BleServer:

    BASE_UUID = "-6802-4573-858e-5587180c32ea"
    ONBOARD_SERVICE_UUID = f"0000a000{BASE_UUID}"

    WIFI_STATUS_CHARACTERISTIC_UUID = f"0000a001{BASE_UUID}"
    WIFI_LIST_CHARACTERISTIC_UUID = f"0000a004{BASE_UUID}"
    REGISTRATION_STATUS_CHARACTERISTIC_UUID = f"0000a011{BASE_UUID}"
    COMMAND_CHARACTERISTIC_UUID = f"0000a020{BASE_UUID}"

    START_MARKER = "[START]"
    END_MARKER = "[END]"

    def __init__(self, duration: str) -> None:
        # Get the current time and add the duration to calculate the end time
        self.duration_sec = duration_to_seconds(duration)
        if duration == "-1":
            self.end_time = -1
        else:
            # Get current time from system and add the duration to calculate the end time
            self.end_time = int(asyncio.get_event_loop().time()) + self.duration_sec
        logging.basicConfig(level=logging.DEBUG)
        host_name = socket.gethostname()
        self.server = BlessServer(name=f"{host_name} Remote.It Onboard")
        self.logger = logging.getLogger(name=__name__)
        self.ble_agent = BleAgentService()
        self.network_manager = NetworkManagerService()
        self.network_manager.on_change_network = self.on_change_network
        self.remoteit_registration = RemoteItService()
        self.remoteit_registration.on_change_registration = self.on_change_registration
        self.buffers: dict = {}
        self.receiving_states: dict = {}

    def on_change_network(self, var_name: str, value: str) -> None:
        self.logger.debug(f"{var_name} has been updated to {value}")
        asyncio.create_task(self.run_notify_wifi())

    def on_change_registration(self, var_name: str, value: str) -> None:
        self.logger.debug(f"{var_name} has been updated to {value}")
        asyncio.create_task(self.run_notify_registration())

    async def run_notify_wifi(self) -> None:
        def notify_wifi() -> None:
            self.logger.debug("Setting Wifi Status Characteristic")
            self.notify(
                self.WIFI_STATUS_CHARACTERISTIC_UUID, self.create_wifi_status_json()
            )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, notify_wifi)

    async def run_notify_registration(self) -> None:
        def notify_registration() -> None:
            self.logger.debug("Setting Registration Status Characteristic")
            registration_status = {
                "reg": self.remoteit_registration.registration_status,
                "id": self.remoteit_registration.device_id,
            }
            self.notify(
                self.REGISTRATION_STATUS_CHARACTERISTIC_UUID,
                json.dumps(registration_status),
            )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, notify_registration)

    def create_wifi_status_json(self) -> str:
        self.logger.debug("Creating WiFi Status JSON.")
        wifi_status_json = {
            "wlan": self.network_manager.wifi_status,
            "eth": self.network_manager.ethernet_status,
            "ssid": self.network_manager.get_current_ssid(),
            "desired_ssid": self.network_manager.desired_ssid,
            "error": self.network_manager.error,
            "scan": self.network_manager.scan_status,
        }
        return json.dumps(wifi_status_json)

    def write_request(
        self,
        characteristic: BlessGATTCharacteristic,
        value: bytearray,
        **kwargs: dict[str, Any],
    ) -> None:
        self.logger.debug("characteristic")
        self.logger.debug(characteristic)
        self.logger.debug("value")
        self.logger.debug(value)

        self.end_time = int(asyncio.get_event_loop().time()) + self.duration_sec

        self.logger.debug(f"Received write on {characteristic.uuid}: {value}")
        # Decode value from byte array to string

        decoded_value = value.decode("utf-8")
        self.logger.debug(f"Decoded value: {decoded_value}")

        if characteristic.uuid not in self.buffers:
            self.buffers[characteristic.uuid] = ""
            self.receiving_states[characteristic.uuid] = False

        if self.START_MARKER in decoded_value:
            if self.receiving_states[characteristic.uuid]:
                # Cancel/Fail the current transmission if already receiving
                self.logger.error(
                    f"Transmission error: New start marker received before finishing the current message on {characteristic.uuid}."
                )
                self.buffers[characteristic.uuid] = ""
                self.receiving_states[characteristic.uuid] = False
                return

            self.receiving_states[characteristic.uuid] = True
            self.buffers[characteristic.uuid] = ""
            decoded_value = decoded_value.replace(self.START_MARKER, "")

        if self.receiving_states[characteristic.uuid]:
            if self.END_MARKER in decoded_value:
                self.receiving_states[characteristic.uuid] = False
                decoded_value = decoded_value.replace(self.END_MARKER, "")
                self.buffers[characteristic.uuid] += decoded_value
                self.process_full_message(characteristic)
            else:
                self.buffers[characteristic.uuid] += decoded_value

    def process_full_message(self, characteristic: BlessGATTCharacteristic) -> None:
        full_message = self.buffers[characteristic.uuid]
        self.logger.debug(
            f"Full message received on {characteristic.uuid}: {full_message}"
        )

        try:
            if characteristic.uuid == self.COMMAND_CHARACTERISTIC_UUID:
                self.logger.debug("Command received.")
                data = json.loads(full_message)
                command = data["command"]
                self.logger.debug(f"Command: {command}")
                if command == Commands.WIFI_SCAN:
                    self.logger.info("Scan WiFi command received.")
                    asyncio.create_task(self.network_manager.scan_wifi_networks())
                elif command == Commands.WIFI_CONNECT:
                    self.logger.info("Connect to WiFi command received.")
                    self.error = None
                    self.desired_ssid = data["ssid"]
                    asyncio.create_task(
                        self.network_manager.configure_wifi_async(
                            self.desired_ssid, data["password"]
                        )
                    )
                elif command == Commands.R3_REGISTER:
                    code = data["code"]
                    # If code is blank, return
                    if len(code) == 0:
                        self.logger.warning("Received empty registration code.")
                        return

                    self.logger.info(f"Setting Remote.It Registration Code to: {code}")
                    asyncio.create_task(
                        self.remoteit_registration.install_remoteit_agent_async(code)
                    )
                elif command == Commands.IS_CONNECTED:
                    self.logger.info("Checking connection status.")
                    self.network_manager.is_wifi_connected()
                    self.network_manager.is_ethernet_connected()
                else:
                    self.logger.warning(f"Unhandled command: {command}")
            else:
                self.logger.warning(
                    f"Unhandled characteristic UUID: {characteristic.uuid}"
                )
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            self.logger.error(f"Buffer content: {full_message}")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")

        # Clear the buffer after processing the full message
        self.buffers[characteristic.uuid] = ""

    def notify(self, characteristic_uuid: str, value: str) -> None:
        self.create_buffer(characteristic_uuid, value)

        while characteristic_uuid in self.buffers:
            characteristic = self.server.get_characteristic(characteristic_uuid)
            if characteristic is not None:
                characteristic.value = self.get_next_chunk(characteristic_uuid)
                self.server.update_value(self.ONBOARD_SERVICE_UUID, characteristic_uuid)

    def read_request(
        self, characteristic: BlessGATTCharacteristic, **kwargs: dict[str, Any]
    ) -> bytearray:
        self.end_time = int(asyncio.get_event_loop().time()) + self.duration_sec

        if self.buffers.get(characteristic.uuid) is not None:
            return self.get_next_chunk(characteristic.uuid)

        if characteristic.uuid == self.WIFI_STATUS_CHARACTERISTIC_UUID:
            self.logger.info("Reading WiFi Status")
            self.create_buffer(characteristic.uuid, self.create_wifi_status_json())
        elif characteristic.uuid == self.WIFI_LIST_CHARACTERISTIC_UUID:
            self.logger.info("Reading WiFi List")
            # ssid = self.getNextWifi()
            wifiList = self.network_manager.get_wifi_json()
            self.logger.debug("ssids available: " + wifiList)
            self.create_buffer(characteristic.uuid, wifiList)
        elif characteristic.uuid == self.REGISTRATION_STATUS_CHARACTERISTIC_UUID:
            self.logger.info("Reading Remote.It Registration Status")
            # self.remoteit_registration.check_device_registration()
            registration_status_json = {
                "reg": self.remoteit_registration.registration_status,
                "id": self.remoteit_registration.device_id,
            }
            self.create_buffer(
                characteristic.uuid, json.dumps(registration_status_json)
            )

        return self.get_next_chunk(characteristic.uuid)

    def get_next_chunk(self, characteristic_uuid: str) -> bytearray:
        buffer = self.buffers[characteristic_uuid]
        chunk_size = 248  # Adjust as needed
        data = buffer["data"]
        chunk = ""

        if buffer["index"] == -1:
            chunk += self.START_MARKER
            buffer["index"] = 0
            # Get the remaining size after the start marker

        if buffer["index"] < len(data):
            remaining_size = chunk_size - len(chunk)
            chunk += data[buffer["index"] : buffer["index"] + remaining_size]
            buffer["index"] += remaining_size

        if buffer["index"] >= len(data):
            remaining_size = chunk_size - len(chunk)
            if remaining_size > len(self.END_MARKER):
                chunk += self.END_MARKER
                self.buffers.pop(characteristic_uuid)

        return bytearray(chunk.encode("utf-8"))

    def create_buffer(self, characteristic_uuid: str, data: str) -> None:
        self.buffers[characteristic_uuid] = {"data": data, "index": -1}

    async def setup_gatt_server(self) -> None:
        gatt: dict[str, dict[str, Any]] = {
            self.ONBOARD_SERVICE_UUID: {
                self.WIFI_STATUS_CHARACTERISTIC_UUID: {
                    "Properties": (
                        GATTCharacteristicProperties.notify
                        | GATTCharacteristicProperties.read
                    ),
                    "Permissions": GATTAttributePermissions.readable,
                    "Value": None,
                },
                self.WIFI_LIST_CHARACTERISTIC_UUID: {
                    "Properties": GATTCharacteristicProperties.read,
                    "Permissions": GATTAttributePermissions.readable,
                    "Value": None,
                },
                self.COMMAND_CHARACTERISTIC_UUID: {
                    "Properties": GATTCharacteristicProperties.write,
                    "Permissions": GATTAttributePermissions.writeable,
                    "Value": None,
                },
                self.REGISTRATION_STATUS_CHARACTERISTIC_UUID: {
                    "Properties": (
                        GATTCharacteristicProperties.notify
                        | GATTCharacteristicProperties.read
                    ),
                    "Permissions": GATTAttributePermissions.readable,
                    "Value": None,
                },
            }
        }
        self.server.read_request_func = self.read_request
        self.server.write_request_func = self.write_request

        await self.server.add_gatt(gatt)

    async def start(self) -> None:
        await self.setup_gatt_server()
        await self.server.start()
        await self.ble_agent.register_agent()
        self.logger.info("BLE Server started.")
        self.remoteit_registration.check_device_registration()
        asyncio.create_task(self.remoteit_registration.monitor_remoteit_logs())
        self.network_manager.is_wifi_connected()
        self.network_manager.is_ethernet_connected()
        asyncio.create_task(self.network_manager.scan_wifi_networks())
        asyncio.create_task(self.network_manager.monitor_wifi_status())
        self.logger.info("Tasks started.")

    async def disconnect_all_clients(self) -> None:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        # Get the object manager
        introspect = await bus.introspect("org.bluez", "/")
        obj = bus.get_proxy_object("org.bluez", "/", introspect)
        manager = obj.get_interface("org.freedesktop.DBus.ObjectManager")

        # Get all managed objects
        objects = await manager.call_get_managed_objects()  # type: ignore

        for path, interfaces in objects.items():
            if "org.bluez.Device1" in interfaces:
                # Get the device object and interface
                try:
                    introspect_device = await bus.introspect("org.bluez", path)
                    device_obj = bus.get_proxy_object(
                        "org.bluez", path, introspect_device
                    )
                    device = device_obj.get_interface("org.bluez.Device1")

                    # Check if the device is connected
                    connected = await device.get_connected()  # type: ignore
                    if connected:
                        print(
                            f"Disconnecting device {interfaces['org.bluez.Device1']['Address']}"
                        )
                        await device.call_disconnect()  # type: ignore
                except InterfaceNotFoundError:
                    continue

    async def stop_server(self) -> None:
        await self.disconnect_all_clients()
        await self.server.stop()
        await self.ble_agent.unregister_all_agents()


def create_default_config() -> None:
    # Create the default configuration file with predefined settings.
    default_config = ConfigObj(DEFAULT_CONFIG_FILE)
    default_config.update(DEFAULT_SETTINGS)
    default_config.write()


def merge_configs(default_config: ConfigObj, existing_config: ConfigObj) -> ConfigObj:
    # Merge existing config values into the default config.
    for section in default_config.keys():
        if section not in existing_config:
            existing_config[section] = {}

        for key in default_config[section].keys():
            if key in existing_config[section]:
                default_config[section][key] = existing_config[section][key]

    return default_config


def read_config() -> Dict[str, Any]:
    # Create the default configuration if it doesn't exist
    if not os.path.exists(DEFAULT_CONFIG_FILE):
        create_default_config()

    # Load default configuration
    default_config = ConfigObj(DEFAULT_CONFIG_FILE)

    # Load existing configuration if it exists
    if os.path.exists(CONFIG_FILE):
        existing_config = ConfigObj(CONFIG_FILE)
        # Merge existing configuration values into the default configuration
        merged_config = merge_configs(default_config, existing_config)
    else:
        merged_config = default_config

    # Write the merged configuration back to the config file
    merged_config.filename = CONFIG_FILE
    merged_config.write()

    return {section: dict(merged_config[section]) for section in merged_config}


def duration_to_seconds(duration: str) -> int:
    if duration == "-1":
        return -1
    # Convert a duration string like '5m' or '10s' to seconds.
    unit = duration[-1]
    if unit == "s":
        return int(duration[:-1])
    elif unit == "m":
        return int(duration[:-1]) * 60
    elif unit == "h":
        return int(duration[:-1]) * 3600
    else:
        raise ValueError("Invalid duration format. Use 's', 'm', or 'h'.")


async def shutdown_after_delay(delay: int) -> None:
    logging.info(f"Shutting down the application in {delay} seconds...")
    await asyncio.sleep(delay)
    logging.info("Shutting down the application...")
    os.system("shutdown now")


def setup_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")


async def main() -> None:

    # If argument update-config is passed, create a new default config file
    # and exit the application
    if len(sys.argv) > 1 and sys.argv[1] == "update-config":
        read_config()
        sys.exit(0)

    settings = read_config()["Settings"]

    setup_logging(settings["LogLevel"])

    logging.info("Starting Onboard Server...")

    server = BleServer(settings["Duration"])
    await server.start()

    logging.info("Startup complete.")

    # Schedule shutdown
    if server.end_time == "-1":
        await asyncio.Event().wait()
    else:
        # Sleep for 1 minute and check if the end time has been reached
        while asyncio.get_event_loop().time() < server.end_time:
            await asyncio.sleep(60)

        while (
            await server.server.is_connected()
            and not server.remoteit_registration.is_registered()
        ):
            await asyncio.sleep(10)

    await server.stop_server()


def app() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Interupted by keyboard, Exiting")
