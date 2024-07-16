## About Bluetooth WiFi Onboarding

**Company:** Remote.It  
**Product Name:** Bluetooth WiFi Onboarding

Bluetooth WiFi Onboarding is a solution developed by Remote.It to simplify the process of setting up new devices. Our product leverages Bluetooth Low Energy (BLE) technology to allow users to easily connect and configure WiFi settings, ensuring seamless network integration. Additionally, it provides the capability to register devices with the Remote.It service, enabling remote access to various services on the device, such as SSH, VNC, and web servers.

### Key Features
- **Easy WiFi Configuration:** Connect via Bluetooth LE to configure WiFi settings and get your device on the network effortlessly.
- **Remote Access:** Register your device with the Remote.It service to gain remote access to essential services like SSH, VNC, and web servers.
- **Compatibility:** Designed to work with Bookworm Debian packages, with a primary focus on Raspberry Pi devices.
- **Python-Based:** The software is written in Python and sets up a GATT server to communicate WiFi and registration information.
- **Automatic WiFi Scanning:** Automatically scans available WiFi networks on boot-up to streamline the connection process.

Bluetooth WiFi Onboarding makes setting up and managing your devices simple and efficient. Experience the convenience of remote access and simplified network configuration with Remote.It.

### Additional Resources
- [How to use raspberry pi r3onboard image](https://link.remote.it/getting-started/rpi-ble-image)
- [How to Install r3onboard](https://link.remote.it/docs/ble)
- [Download latest Debian Package](https://link.remote.it/download/r3onboard_deb)

## Setup for Development

### Setup For building (on mac os)
```sh
brew install pyenv
brew install python3
brew install poetry

poetry install
```

### Setup for packaging (fpm)
```sh
brew install ruby
echo 'export PATH="/usr/local/opt/ruby/bin:$PATH"' >> /Users/ebowers/.bash_profile # On Mac
source ~/.bash_profile # On Mac

gem install fpm
```

## Poetry script commands

### To Run locally
```sh
poetry run r3onboard
```

### To build
```sh
poetry build
```

### To package 
```sh
poetry run package_debian
poetry run package_pi
```

### To beta release
```sh
poetry run beta_release
```

### To rc release
```sh
poetry run rc_release
```

### To release rc version
```sh
poetry run release <version>
```

### To Version the build
```sh
poetry run version "Enter what was updated here"
```

### To Test
```sh
poetry run test
```

## Useful info

### System commands
- How start the service
  ```sh
  sudo systemctl start r3onboard
  ```
- View logs
  ```sh
  journalctl -u r3onboard -n 100
  ```

### Gatt Service
BASE_UUID = "-6802-4573-858e-5587180c32ea"

COMMISSION_SERVICE_UUID = f"0000a000-{BASE_UUID}"

### Gatt Characteristics

#### Wifi Status (Read & Notify)
- UUID: `WIFI_STATUS_CHARACTERISTIC_UUID = f"0000a001{BASE_UUID}"`
- Returns JSON:
    ```json
    {
      "wlan": "DISCONNECTED",
      "eth": "DISCONNECTED",
      "ssid": "",
      "desired_ssid": null,
      "error": null,
      "scan": "COMPLETE"
    }
    ```

##### Fields:
- `wlan` - Enum<CONNECTED, CONNECTING, DISCONNECTED, FAILED_START, INVALID_PASSWORD, INVALID_SSID>
- `eth` - Enum<CONNECTED, DISCONNECTED>
- `ssid` - String (current ssid)
- `desired_ssid` - String (null or desired ssid)
- `error` - String (null or error code)
- `scan` - Enum<SCANNING, COMPLETE>

##### RemoteIt Status (Read & Notify)
- UUID: `REGISTRATION_STATUS_CHARACTERISTIC_UUID = f"0000a011{BASE_UUID}"`
- Returns JSON:
    ```json
    {
      "reg": "<status>",
      "id": "<id>"
    }
    ```

##### Fields:
- `regStatus` - Enum<UNREGISTERED, REGISTERING, REGISTERED>

#### Wifi List (Read)
- UUID: `WIFI_LIST_CHARACTERISTIC_UUID = f"0000a004{BASE_UUID}"`
- Returns JSON:
    ```json
    [
      {"ssid": "ssid", "signal": "signal"}
    ]
    ```

##### Fields:
- List of `ssid` and `signal`

#### COMMAND (Write)
- UUID: `CONNECT_CHARACTERISTIC_UUID = f"0000a020{BASE_UUID}"`
- Example JSON string:
    ```json
    {
      "command": "<command>",
      "<additional args>"
    }
    ```

#### Register (Write)
- Takes a registration code:
    ```json
    {
      "command": "R3_REGISTER",
      "code": "<code>"
    }
    ```

#### Connect Wifi (Write)
- Takes ssid and password:
    ```json
    {
      "command": "WIFI_CONNECT",
      "ssid": "<ssid>",
      "password": "<password>"
    }
    ```

#### Scan Wifi (Write)
- Command:
    ```json
    {
      "command": "WIFI_SCAN"
    }
    ```


### BLE Commands
- Wifi Scan: 
  ```sh
  [START]{"command": "WIFI_SCAN"}[END]
  ```
- Wifi Connect:
  ```sh
  [START]{"command": "WIFI_CONNECT", "ssid": "remoteit", "password": "password"}[END]
  ```
- Register:
  ```sh
  [START]{"command": "R3_REGISTER", "code": "<CODE>"}[END]
  ```