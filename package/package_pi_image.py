import time
import glob
import os
import shutil
import subprocess
import threading
from typing import List
import requests

# import load_config from product_config.py
from package.product_config import (
    ProductType,
    generate_checksum_file,
    ProductConfig,
)

# PI image cache folder (keep from downloading every time)
pi_cache_dir = "./build/base_images/pi"

print_lock = threading.Lock()


def get_final_url(url: str) -> str:
    # Get the final redirected URL
    response = requests.head(url, allow_redirects=True)
    return response.url


def download_image(product: ProductConfig) -> None:
    # Get the final redirected URL
    final_url = get_final_url(product.download_path)
    file_name = os.path.basename(final_url)
    final_file_path = os.path.join(pi_cache_dir, file_name)
    product.downloaded_filename = final_file_path
    # final_file_paths.append(final_file_path)

    # Check if the file already exists
    if not os.path.exists(final_file_path):
        # Download the file
        response = requests.get(final_url, stream=True)
        response.raise_for_status()
        with open(final_file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        with print_lock:
            print(f"Downloaded and saved as {final_file_path}")
    else:
        with print_lock:
            print(f"The file {file_name} already exists in the cache directory.")


def download_latest_pi_images(products: List[ProductConfig]) -> None:
    # Ensure the cache directory exists
    os.makedirs(pi_cache_dir, exist_ok=True)

    threads = []
    for product in products:
        if (
            product.product_type != ProductType.R3_ONBOARD_IMG
            and product.product_type != ProductType.R3_ONBOARD_LITE_IMG
        ):
            continue
        thread = threading.Thread(
            target=download_image,
            args=(product,),
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()


def start_build_pi_images(project_version: str, products) -> None:
    # Remove any images from ./dist
    img_files = glob.glob("./dist/v*/*.img")
    for file in img_files:
        os.remove(file)
        print(f"Removed {file}")

    # PI Build folder
    pi_build_dir = "./build/pi"

    # Clean up the pi build directory
    if os.path.exists(pi_build_dir):
        shutil.rmtree(pi_build_dir)

    # Run docker build command from ./pi directory
    pi_dir = "./package/pi"

    # PI Image folder
    img_dir = f"{pi_build_dir}/images"
    files_dir = f"{pi_build_dir}/files"

    # Ensure the directories exist
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(files_dir, exist_ok=True)

    # Copy .deb file to pi_build_dir
    src_deb = f"./dist/v{project_version}/r3onboard_all.deb"
    dest_deb = f"{files_dir}/r3onboard.deb"
    shutil.copy(src_deb, dest_deb)
    print(f"Copied {src_deb} to {dest_deb}")

    # Copy Dockerfile to pi_build_dir
    shutil.copy(f"{pi_dir}/Dockerfile", pi_build_dir)

    # Copy updateImage.sh to pi_build_dir
    shutil.copy(f"{pi_dir}/updateImage.sh", f"{pi_build_dir}/files/")

    # Build the docker image
    subprocess.run(
        ["docker", "build", "-t", "pi-image-modifier", "."],
        cwd=pi_build_dir,
        check=True,
    )

    print(f"Docker image built")

    def build_pi_image(product: ProductConfig) -> None:  # image_file: str) -> None:
        temp_build_dir = f"{pi_build_dir}_{os.path.basename(product.downloaded_filename).replace('.img.xz', '')}"

        # Clean up temporary build directory if exists
        if os.path.exists(temp_build_dir):
            shutil.rmtree(temp_build_dir)

        os.makedirs(temp_build_dir, exist_ok=True)

        # # Copy image to temporary build directory
        temp_img_dir = os.path.join(temp_build_dir, "images")
        os.makedirs(temp_img_dir, exist_ok=True)

        shutil.copy(product.downloaded_filename, temp_img_dir)

        # Run docker run command
        with print_lock:
            print(
                f"Docker Running image modification for {product.downloaded_filename}"
            )
        startTime = time.time()
        log_file_path = os.path.join(temp_build_dir, "docker_run.log")

        with open(log_file_path, "w") as log_file:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--privileged",
                    "-v",
                    f"{os.path.abspath(temp_img_dir)}:/images",
                    "-it",
                    "pi-image-modifier",
                ],
                cwd=temp_build_dir,
                check=True,
                stdout=log_file,
                stderr=log_file,
            )
        processingTime = time.time() - startTime
        with print_lock:
            print(
                f"Docker image modification completed for {product.downloaded_filename} in {processingTime} seconds"
            )

        # Ensure the versioned directory exists
        versioned_dist_dir = f"./dist/v{project_version}"
        os.makedirs(versioned_dist_dir, exist_ok=True)

        # Compress and Move the new .img file from temporary build directory to ./dist
        for filename in os.listdir(temp_img_dir):
            if filename.endswith(".img"):
                src_img_path = os.path.join(temp_img_dir, filename)
                # Set the new image filename to the product file name without the .xz extension
                new_image_filename = product.filename.replace(".xz", "")
                # new_image_filename = product.filename
                new_image_path = os.path.join(temp_img_dir, new_image_filename)
                # Rename src_img to dest_img
                shutil.move(src_img_path, new_image_path)
                # compress the image
                with print_lock:
                    print(f"Compressing {new_image_path}")
                startTime = time.time()
                subprocess.run(
                    ["xz", "-3", "-T0", "-k", new_image_path], check=True
                )  # faster but medium compression and multithreaded
                # subprocess.run(
                #     ["xz", "-0", "-T0", "-k", new_image_path], check=True
                # )  # faster but lower compression and multithreaded
                # subprocess.run(["xz", "-k", new_image_path], check=True) # slower but higher compression
                # move the compressed image to the versioned dist directory
                processingTime = time.time() - startTime
                with print_lock:
                    print(f"Compressed {new_image_path} in {processingTime} seconds")
                compressed_img = new_image_path + ".xz"
                generate_checksum_file(compressed_img)
                shutil.move(compressed_img, versioned_dist_dir)
                shutil.move(compressed_img + ".checksum", versioned_dist_dir)
                with print_lock:
                    print(f"Moved {compressed_img} to {versioned_dist_dir}")

                # Clean up temporary build directory
                shutil.rmtree(temp_build_dir)

    # Create and start threads for each image
    threads = []

    for product in products:
        thread = threading.Thread(
            # target=build_pi_image, args=(product.downloaded_filename,)
            target=build_pi_image,
            args=(product,),
        )
        thread.start()
        threads.append(thread)

    # Join all threads
    for thread in threads:
        thread.join()
