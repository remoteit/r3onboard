import glob
import os
import shutil
import subprocess
import sys
import json

import requests
import toml

from package.package_pi_image import download_latest_pi_images, start_build_pi_images
from package.product_config import (
    ProductType,
    generate_checksum_file,
    load_config,
    post_new_release_to_webflow,
)

# Debian package path
package_debian_path = os.path.abspath("./package/debian")


####### Entry points
def versions():
    # Get the project version
    project_version = get_project_version()
    print("Current version: " + project_version)

    print_type_versions("beta")
    print_type_versions("rc")
    print_type_versions()


def version() -> str:
    # Get the first argument as change description
    if len(sys.argv) < 2:
        print(
            "No change description provided, which version do you want? Run with: poetry run version <change_description>"
        )
        exit(1)

    change_description = sys.argv[1]
    incr_version(change_description)


def push_to_pi() -> None:
    ip = sys.argv[1]
    port = sys.argv[2]

    # Build the debian package
    start_package_debian()

    # Copy the debian package to the pi
    project_version = get_project_version()
    subprocess.run(
        [
            "scp",
            f"-P {port}",
            f"./dist/v{project_version}/r3onboard_all.deb",
            f"pi@{ip}:/tmp",
        ],
        check=True,
    )

    # Install the debian package on the pi
    # Install the debian package on the pi
    subprocess.run(
        [
            "ssh",
            f"pi@{ip}",
            f"-p {port}",
            "sudo systemctl stop r3onboard && sudo apt install --reinstall /tmp/r3onboard_all.deb && sudo systemctl start r3onboard",
        ],
        check=True,
    )

    # poetry run package_debian && scp -P 33014 ./dist/r3commission_0.1.15_all.deb pi@r3commision-2-ssh.at.remote.it:/tmp && ssh pi@r3commision-2-ssh.at.remote.it -p 33014 'sudo systemctl stop r3commission && sudo apt install --reinstall /tmp/r3commission_0.1.15_all.deb && sudo systemctl start r3commission'


def package_debian() -> None:
    start_package_debian()
    incr_version("")


def package_pi() -> None:
    start_package_pi_images(beta=True)
    incr_version("")


def beta_release() -> None:
    start_package_pi_images(beta=True)
    upload_beta()
    mark_latest(get_project_version(), "beta")
    incr_version("")


def rc_release() -> None:
    set_debian_stable()
    start_package_pi_images()
    upload_rc()
    mark_latest(get_project_version(), "rc")
    incr_version("")


def release() -> None:
    # Get version from command line
    project_version = sys.argv[1]

    # If a v is not on the version, add the v
    if project_version[0] != "v":
        project_version = "v" + project_version

    # copy the rc version from /r3onboard/rc/v{project_version} to /r3onboard/v{project_version}
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            f"s3://downloads.remote.it/r3onboard/rc/{project_version}",
            f"s3://downloads.remote.it/r3onboard/{project_version}",
            "--recursive",
        ],
        check=True,
    )

    # load products
    products = load_config("package/products.json")

    # print("products", products)

    # post products to webflow
    for product in products:
        post_new_release_to_webflow(
            project_version,
            product.product_type,
            product.filename,
            product.architecture,
            product.platform_type,
            product.options,
        )

    # Set release redirect to this version
    mark_latest(project_version, "")


def test() -> None:
    # Define paths
    dockerfile_dir = os.path.join(os.path.dirname(__file__), "../tests/docker")

    # Build Docker image
    build_command = f"docker build -t test-r3onboard {dockerfile_dir}"
    print("Building Docker image with command:", build_command)
    subprocess.run(build_command, shell=True, check=True)

    # Run Docker container with volume mount
    run_command = "docker run -v $(pwd):/app test-r3onboard"
    print("Running Docker container with command:", run_command)
    subprocess.run(run_command, shell=True, check=True)


####### Helper funtions
def get_project_version() -> str:
    # Load the pyproject.toml file
    with open("pyproject.toml", "r") as f:
        pyproject = toml.load(f)

    # Get the version from the project section
    version = pyproject.get("tool", {}).get("poetry", {}).get("version")

    return version


def build_poetry_package() -> None:
    # Run poetry build r3onboard
    try:
        subprocess.run(["poetry", "build", "-f", "wheel"], check=True)
    except subprocess.CalledProcessError as e:
        print("Error:", e)
        exit(1)


def extract_whl_file(dist_dir: str) -> str:
    # Get the .whl file from the dist directory
    whl_files = [f for f in os.listdir(dist_dir) if f.endswith(".whl")]
    if not whl_files:
        print("No .whl files found in the dist directory.")
        exit(1)
    elif len(whl_files) > 1:
        print("Multiple .whl files found in the dist directory. Only one expected.")
        exit(1)
    else:
        return os.path.join(dist_dir, whl_files[0])


def start_package_debian() -> None:

    try:
        project_version = get_project_version()
        debian_build_dir = "./build/debian"
        debian_package_dir = "./package/debian"

        # Clean up the debian build directory
        if os.path.exists(debian_build_dir):
            shutil.rmtree(debian_build_dir)

        # Clean up the debian dist directory
        if os.path.exists("./dist"):
            shutil.rmtree("./dist")

        # ensure the debian build directory exists
        os.makedirs(debian_build_dir, exist_ok=True)

        # Build the poetry package
        build_poetry_package()

        # Get WHL file
        dist_dir = "dist"
        whl_file = extract_whl_file(dist_dir)

        # Ensure the versioned directory exists
        versioned_dist_dir = f"./dist/v{project_version}"
        os.makedirs(versioned_dist_dir, exist_ok=True)

        # Make build directory ./build
        if not os.path.exists("./build"):
            os.makedirs("./build")

        # Copy ./package/debian/postinst to ./build
        shutil.copy("./package/debian/postinst", debian_build_dir)

        # Replace <PACKSGE_VERSION> with project_version in ./build/postinst
        with open(f"{debian_build_dir}/postinst", "r") as f:
            postinst = f.read()
            postinst = postinst.replace("<PACKAGE_VERSION>", project_version)
        with open(f"{debian_build_dir}/postinst", "w") as f:
            f.write(postinst)

        # Define the command and options as a list
        command = [
            "fpm",
            "-s",
            "dir",
            "-t",
            "deb",
            "-n",
            "r3onboard",
            "-v",
            project_version,
            "--depends",
            "python3",
            "--depends",
            "python3-venv",
            "--description",
            "A package that installs a r3onboard python wheel and configures it to start at boot",
            "--architecture",
            "all",
            "--maintainer",
            "Evan Bowers <evan@remote.it>",
            "--url",
            "https://remote.it",
            "--vendor",
            "Remote.it",
            "--category",
            "net",
            "--after-install",
            f"{debian_build_dir}/postinst",
            "--before-remove",
            f"{debian_package_dir}/prerm",
            "--package",
            f"./dist/v{project_version}/r3onboard_all.deb",
            "--verbose",
            f"{whl_file}=/opt/r3onboard/",
            f"./LICENSE=/usr/share/doc/r3onboard/LICENSE",
            f"{debian_package_dir}/config.ini.default=/etc/r3onboard/config.ini.default",
            f"{debian_package_dir}/r3onboard.service=/lib/systemd/system/r3onboard.service",
            f"{debian_package_dir}/README.debian=/usr/share/doc/r3onboard/README.debian",
            f"{debian_package_dir}/changelog=/usr/share/doc/r3onboard/changelog",
        ]

        # Remove any debian packages from ./dist
        deb_files = glob.glob("./dist/v*/*.deb")
        for file in deb_files:
            os.remove(file)

        # Run the fpm
        print("Building debian package...")
        subprocess.run(command, check=True)
        generate_checksum_file(f"./dist/v{project_version}/r3onboard_all.deb")
        print("Package built successfully.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while building the package: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        # print trace
        print(e.with_traceback())


def start_package_pi_images(beta: bool = False) -> None:

    # Build the debian package
    start_package_debian()

    # Get the project version
    project_version = get_project_version()

    products = load_config("package/products.json")
    # Remove non image products
    products = [
        product
        for product in products
        if product.product_type == ProductType.R3_ONBOARD_IMG
        or product.product_type == ProductType.R3_ONBOARD_LITE_IMG
    ]

    if beta:
        products = [product for product in products if product.beta]

    # Download the latest pi image
    print("Downloading the latest Raspberry Pi image...")
    download_latest_pi_images(products)

    # Build the pi image
    print("Building the Raspberry Pi image...")
    start_build_pi_images(project_version, products)


def set_debian_stable() -> None:
    # Define the Docker image name
    image_name = "debian_dch:latest"
    build_dch_image(image_name)

    # Mark the version as released
    # Run the dch command in the Docker container to mark the version as released
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{package_debian_path}:/mnt/debian",
            image_name,
            "dch",
            "-r",
            "",
            "--distribution",
            "stable",
            "--no-force-save-on-release",
            "--check-dirname-level",
            "0",
        ],
        check=True,
    )


def incr_version(change_description) -> str:
    #

    # Get the project version
    project_version = get_project_version()

    # Split the version into parts
    parts = project_version.split(".")

    # Increment the patch version
    parts[-1] = str(int(parts[-1]) + 1)

    # Join the parts back together
    new_version = ".".join(parts)

    # Write the new version back to the pyproject.toml file
    with open("pyproject.toml", "r") as f:
        pyproject = toml.load(f)

    pyproject["tool"]["poetry"]["version"] = new_version

    with open("pyproject.toml", "w") as f:
        toml.dump(pyproject, f)

    # Define the Docker image name
    image_name = "debian_dch:latest"
    build_dch_image(image_name)

    # Run the dch command in the Docker container to update the version
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{package_debian_path}:/mnt/debian",
            image_name,
            "dch",
            "--newversion",
            new_version,
            change_description,
            "--check-dirname-level",
            "0",
        ],
        check=True,
    )

    return new_version


def build_dch_image(image_name: str) -> None:

    # Create the Dockerfile content
    dockerfile_content = """
    # Use an official Debian image as a parent image
    FROM debian:latest
    
    # Set environment variables
    ENV DEBIAN_FRONTEND=noninteractive
    
    # Install necessary packages
    RUN apt-get update && apt-get install -y \\
        devscripts \\
        && rm -rf /var/lib/apt/lists/*
    
    # Set the maintainer environment variables
    ENV DEBFULLNAME="Evan Bowers"
    ENV DEBEMAIL="evan@remote.it"
    
    # Set the working directory
    WORKDIR /mnt/debian
    
    # Command to keep the container running for interactive use
    CMD ["tail", "-f", "/dev/null"]
    """

    # Write the Dockerfile to a temporary file
    with open("Dockerfile", "w") as f:
        f.write(dockerfile_content)

    try:
        # Build the Docker image
        subprocess.run(["docker", "build", "-t", image_name, "."], check=True)
    finally:
        # Clean up the Dockerfile
        os.remove("Dockerfile")


def upload_beta() -> None:

    # Upload the versioned distribution directory (ex v0.1.0) to aws s3 for distribution
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            f"./dist/v{get_project_version()}",
            "s3://downloads.remote.it/r3onboard/beta/v" + get_project_version(),
            "--recursive",
        ],
        check=True,
    )


def upload_rc() -> None:

    # Upload the versioned distribution directory (ex v0.1.0) to aws s3 for distribution
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            f"./dist/v{get_project_version()}",
            "s3://downloads.remote.it/r3onboard/rc/v" + get_project_version(),
            "--recursive",
        ],
        check=True,
    )


def print_type_versions(type: str = None):
    name = "Released"
    if type:
        name = type.capitalize()

    extraPath = ""
    if type:
        extraPath = f"{type}/"

    # Get latest released version by looking at redirect in downloads.remote.it
    response = requests.head(
        f"https://downloads.remote.it/r3onboard/{extraPath}latest/r3onboard_all.deb"
    )
    # get the redirected url
    print(f"{name} Version: " + response.headers["Location"].split("/")[-2])

    print(f"{name} versions:")
    # Look on the remote.it downloads bucket for the latest versions of r3onboard
    result = subprocess.run(
        ["aws", "s3", "ls", f"s3://downloads.remote.it/r3onboard/{extraPath}"],
        capture_output=True,
        text=True,
        check=True,
    )
    # Split the result into lines and filter for directory names that start with v
    lines = result.stdout.split("\n")
    for line in lines:
        if "PRE" in line:
            # Extract the directory name
            directory_name = line.split()[-1]
            if directory_name[0] == "v":
                # strip the trailing /
                directory_name = directory_name[:-1]
                print("  " + directory_name)


def mark_latest(project_version: str, type: str = None) -> None:
    # Get the project version
    if project_version is None:
        print(
            "No project version provided, which version do you want? Run with: poetry run latest <version> (ex: poetry run latest v0.1.0)"
        )
        versions()

    # If a v is not on the version, add the v
    if project_version[0] != "v":
        project_version = "v" + project_version

    # Fetch the current website configuration
    result = subprocess.run(
        ["aws", "s3api", "get-bucket-website", "--bucket", "downloads.remote.it"],
        capture_output=True,
        text=True,
        check=True,
    )

    website_configuration = json.loads(result.stdout)

    project_folder = "r3onboard"
    # if type is not none, add the type to the project folder
    if type:
        project_folder = f"{project_folder}/{type}"

    # Update the r3onboard/latest redirect rule
    for rule in website_configuration.get("RoutingRules", []):
        if rule["Condition"].get("KeyPrefixEquals") == f"{project_folder}/latest":
            rule["Redirect"][
                "ReplaceKeyPrefixWith"
            ] = f"{project_folder}/{project_version}"
            break

    # Apply the updated website configuration to the S3 bucket
    subprocess.run(
        [
            "aws",
            "s3api",
            "put-bucket-website",
            "--bucket",
            "downloads.remote.it",
            "--website-configuration",
            json.dumps(website_configuration),
        ],
        check=True,
    )

    # Invalidate the cache for the r3onboard/latest/* redirect in cloudfront E35L88ZM84FDYO
    subprocess.run(
        [
            "aws",
            "cloudfront",
            "create-invalidation",
            "--distribution-id",
            "E35L88ZM84FDYO",
            "--paths",
            f"/{project_folder}/latest/*",
        ],
        check=True,
    )
