from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import json
import os
import boto3

import requests

# webflow collection id
collection_id = "65bbd2d218a55f6a2cf1c2d7"


# Define a enum for product types
class ProductType(StrEnum):
    R3_ONBOARD_PACKAGE = "66722df47be42af4f0aba08a"
    R3_ONBOARD_IMG = "667e0b60bfdd018309dde819"
    R3_ONBOARD_LITE_IMG = "668dadff3b307af899020f6a"


class SubType(StrEnum):
    IMG = "img"
    LITE_IMG = "lite-img"
    PACKAGE = "package"


# Define a enum for platform types
class PlatformType(StrEnum):
    PI = "65bbd2d218a55f6a2cf1c510"
    DEBIAN = "65bbd2d218a55f6a2cf1c5b3"


class Platform(StrEnum):
    PI = "raspberry pi"
    LINUX = "linux"


class Target(StrEnum):
    DEBIAN = "debian"
    PI = "pi"


class FileName(StrEnum):
    IMG_ARM64_LITE = "raspios-bookworm-arm64-lite-r3onboard.img.xz"
    PACKAGE = "r3onboard_all.deb"


class Architecture(StrEnum):
    ARM64 = "arm64"
    ARMHF = "armhf"
    ALL = "all"


class Docs:
    PACKAGE = "https://link.remote.it/docs/ble"
    IMG = "https://link.remote.it/getting-started/rpi-ble-image"


@dataclass
class ProductConfig:
    product_type: ProductType
    filename: str

    architecture: Architecture
    platform_type: PlatformType
    options: str = None  # Optional field
    beta: bool = None  # Optional field
    download_path: str = None  # Optional field
    downloaded_filename: str = None  # Optional field


def load_config(config_file) -> list[ProductConfig]:
    with open(config_file, "r") as f:
        data = json.load(f)
        return [
            ProductConfig(
                ProductType[item["product_type"]],
                item["filename"],
                Architecture[item["architecture"]],
                PlatformType[item["platform_type"]],
                item.get("options") or "-",
                item.get("beta"),
                item.get("download_path"),
            )
            for item in data
        ]


def post_new_release_to_webflow(
    version: str,
    productType: ProductType,
    filename: str,
    arch: str,
    hwPlatformType: PlatformType,
    options: str = "-",
) -> None:

    # Default Debian
    target = Target.DEBIAN
    platform = Platform.LINUX

    if hwPlatformType == PlatformType.PI:
        # if pi set the target and platform to pi
        target = Target.PI
        platform = Platform.PI

    # Default Package Type
    sub_type = SubType.PACKAGE
    description = f"Remote.It Wifi Onboarding Package for {platform}"
    documentation = Docs.PACKAGE

    if (
        productType == ProductType.R3_ONBOARD_IMG
        or productType == ProductType.R3_ONBOARD_LITE_IMG
    ):
        if productType == ProductType.R3_ONBOARD_LITE_IMG:
            sub_type = SubType.LITE_IMG
        else:
            sub_type = SubType.IMG
        description = f"Remote.It Wifi Onboarding Image for {platform} {arch}"
        documentation = Docs.IMG

    # package
    md5, size, date = read_s3_checksum_file(
        "downloads.remote.it", f"r3onboard/rc/{version}/{filename}.checksum"
    )

    # generate a name in the format r3onboard platform target - version
    name = f"r3onboard {sub_type} {platform} {target} {arch} - {version}"
    slug = (
        f"r3onboard-{sub_type}-{platform}-{target}-{arch}".lower()
        .replace(" ", "-")
        .replace(".", "-")
    )

    url = f"https://downloads.remote.it/r3onboard/latest/{filename}"

    entry_data = {
        "Name": name,
        "Slug": slug,
        "HW Platform": hwPlatformType,
        "Product Type": productType,
        "Product": "r3onboard",
        "Platform": platform,
        "Target": target,
        "Architecture": arch,
        "CPU": options,
        "Options": options,
        "Version": version,
        "URL": url,
        "Size": size,
        "Date": date,
        "MD5": md5,
        "Visible": 1,
        "Description": description,
        "Documentation": documentation,
    }

    print("entry_data")
    print(entry_data)

    delete_response = find_and_delete_item_by_slug(slug)
    print("delete_response")
    print(delete_response)

    response = post_cms_entry_to_webflow(entry_data)
    print("webflow response")
    print(response)


def find_and_delete_item_by_slug(slug):
    api_key = os.getenv("WEBFLOW_API_KEY")

    # URL to get items with the given slug
    get_url = (
        f"https://api.webflow.com/v2/collections/{collection_id}/items?slug={slug}"
    )

    headers = {"Authorization": f"Bearer {api_key}", "accept": "application/json"}

    # Find the item by slug
    response = requests.get(get_url, headers=headers)

    if response.status_code != 200:
        return f"Error fetching item: {response.text}"

    items = response.json().get("items", [])
    if not items:
        return f"No items found with slug: {slug}"

    item_id = items[0].get("id")
    if not item_id:
        return f"Item with slug {slug} does not have a valid ID."

    print(f"Item with slug {slug} found with ID {item_id}")

    # URL to delete the item by ID
    delete_url = (
        f"https://api.webflow.com/v2/collections/{collection_id}/items/{item_id}"
    )

    # Delete the item
    delete_response = requests.delete(delete_url, headers=headers)

    if delete_response.status_code == 200 or delete_response.status_code == 204:
        return f"Item with slug {slug} and ID {item_id} deleted successfully."
    else:
        return f"Error deleting item: {delete_response.text}"


def post_cms_entry_to_webflow(entry_data):
    api_key = os.getenv("WEBFLOW_API_KEY")
    url = f"https://api.webflow.com/v2/collections/{collection_id}/items"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept-version": "1.0.0",
        "Content-Type": "application/json",
    }

    data = {
        "isDraft": True,
        "fieldData": {
            "name": entry_data.get("Name"),
            "slug": entry_data.get("Slug"),
            "_cid": collection_id,
            "_id": entry_data.get("Item ID"),
            "created-on": entry_data.get("Created On"),
            "updated-on": entry_data.get("Updated On"),
            "published-on": entry_data.get("Published On"),
            "hw-platform": entry_data.get("HW Platform"),
            "product-type": entry_data.get("Product Type"),
            "product": entry_data.get("Product"),
            "platform": entry_data.get("Platform"),
            "target": entry_data.get("Target"),
            "architecture": entry_data.get("Architecture"),
            "cpu": entry_data.get("CPU"),
            "options": entry_data.get("Options"),
            "version": entry_data.get("Version"),
            "url": entry_data.get("URL"),
            "size": entry_data.get("Size"),
            "date": entry_data.get("Date"),
            "md5": entry_data.get("MD5"),
            "visisble": entry_data.get("Visible"),
            "description": entry_data.get("Description"),
            "documentation": entry_data.get("Documentation"),
        },
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        return response.json()
    else:
        return response.text


def read_s3_checksum_file(bucket_name, file_key, region_name="us-west-2"):
    # Retrieve AWS credentials from environment variables
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    # Set default region if not provided
    if region_name is None:
        region_name = "us-west-2"

    # Initialize the S3 client
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name,
    )

    # Get the checksum file from S3
    response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
    checksum_file_content = response["Body"].read().decode("utf-8")

    # Parse the checksum file content
    lines = checksum_file_content.splitlines()
    checksum = None
    file_size = None
    file_date = None

    for line in lines:
        if line.startswith("SHA-256:"):
            checksum = line.split(": ")[1].strip()
        elif line.startswith("Size:"):
            file_size = int(line.split(": ")[1].strip().split()[0])
        elif line.startswith("Date:"):
            file_date = line.split(": ")[1].strip()

    return checksum, file_size, file_date


def generate_checksum_file(file_path):
    # Calculate SHA-256 checksum
    sha256_hash = hashlib.sha256()
    file_size = 0

    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
            file_size += len(byte_block)

    checksum = sha256_hash.hexdigest()

    # Get file modification date
    file_mod_time = os.path.getmtime(file_path)
    file_date = datetime.fromtimestamp(file_mod_time).strftime("%Y-%m-%d")

    # Prepare checksum file content
    checksum_file_content = (
        f"SHA-256: {checksum}\n" f"Size: {file_size} bytes\n" f"Date: {file_date}\n"
    )

    # Write to checksum file
    checksum_file_path = f"{file_path}.checksum"
    with open(checksum_file_path, "w") as checksum_file:
        checksum_file.write(checksum_file_content)

    print(f"Checksum file generated: {checksum_file_path}")


# # Example usage
# config = load_config('product_config.json')
# for item in config:
#     print(item)
