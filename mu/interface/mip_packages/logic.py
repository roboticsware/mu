"""
MicroPython package manager logic (mip-style host-side install).
"""
import os
import sys
import logging
import json
import urllib.request
import tempfile
import zipfile
import tarfile
import subprocess
import shutil

logger = logging.getLogger(__name__)

def fetch_micropython_index():
    """Fetches the micropython-lib v2 index."""
    try:
        url = "https://micropython.org/pi/v2/index.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("packages", [])
    except Exception as e:
        logger.error(f"Failed to fetch micropython index: {e}")
        return []

def search_pypi(query):
    """Simple PyPI search via JSON API for a specific exact match."""
    try:
        url = f"https://pypi.org/pypi/{query}/json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("info", {})
    except Exception as e:
        logger.error(f"Failed to fetch from PyPI: {e}")
        return None

def get_package_info(package_name):
    """
    Finds package metadata. Prioritizes micropython-lib, then PyPI.
    Returns a dict with package info or None if not found.
    """
    # 1. Check micropython-lib
    index = fetch_micropython_index()
    match = None
    for pkg in index:
        if pkg.get("name") == package_name:
            match = pkg
            break
            
    if match:
        version = match.get("version", "latest")
        return {
            "name": package_name,
            "version": version,
            "summary": "Official MicroPython library",
            "author": "MicroPython",
            "homepage": "https://github.com/micropython/micropython-lib",
            "pypi_url": "",
            "source": "micropython-lib"
        }
        
    # 2. Check PyPI
    info = search_pypi(package_name)
    if info:
        return {
            "name": info.get("name", package_name),
            "version": info.get("version", ""),
            "summary": info.get("summary", ""),
            "author": info.get("author", ""),
            "homepage": info.get("home_page", ""),
            "pypi_url": info.get("package_url", ""),
            "source": "PyPI"
        }
        
    return None

def download_from_pypi(package_name, target_dir):
    """
    Downloads a package from PyPI into target_dir using pip download.
    Returns the path to the downloaded file.
    """
    try:
        # We use python -m pip download
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--no-deps",
            "--dest",
            target_dir,
            package_name
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Find the downloaded file
        files = os.listdir(target_dir)
        if not files:
            return None
        return os.path.join(target_dir, files[0])
    except subprocess.CalledProcessError as e:
        logger.error(f"pip download failed: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Failed to download from PyPI: {e}")
        return None

def extract_package(file_path, extract_dir):
    """Extracts a .whl or .tar.gz file."""
    try:
        if file_path.endswith('.whl') or file_path.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            return True
        elif file_path.endswith('.tar.gz') or file_path.endswith('.tgz'):
            with tarfile.open(file_path, 'r:gz') as tar_ref:
                tar_ref.extractall(extract_dir)
            # Find inner dir if it exists
            return True
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
    return False

def get_installable_files(extract_dir, package_name):
    """
    Identifies files to copy and their destination directories on the device.
    Returns a list of tuples: (absolute_local_path, remote_target_directory)
    """
    installables = []
    items = os.listdir(extract_dir)
    
    # If it's a single directory extraction (tar.gz usually)
    if len(items) == 1 and os.path.isdir(os.path.join(extract_dir, items[0])):
        root_dir = os.path.join(extract_dir, items[0])
        inner_items = os.listdir(root_dir)
        
        # Standard layout: package folder exists inside
        if package_name in inner_items:
            return [(os.path.join(root_dir, package_name), "/lib")]
        if package_name + ".py" in inner_items:
            return [(os.path.join(root_dir, package_name + ".py"), "/lib")]
            
        if "src" in inner_items:
            src_dir = os.path.join(root_dir, "src")
            if os.path.isdir(os.path.join(src_dir, package_name)):
                return [(os.path.join(src_dir, package_name), "/lib")]

        # Flat layout: files are at the root of the repo
        # Wrap everything in /lib/{package_name} to fulfill expectations
        for item in inner_items:
            if item.endswith(".py") or os.path.isdir(os.path.join(root_dir, item)):
                if not item.startswith(".") and "setup" not in item.lower():
                    installables.append((os.path.join(root_dir, item), f"/lib/{package_name}"))
        if installables:
            return installables

    # Wheel extraction (flat)
    valid_items = []
    top_levels = set()
    for item in items:
        if item.endswith(".dist-info") or item.endswith(".egg-info"):
            tl_path = os.path.join(extract_dir, item, "top_level.txt")
            if os.path.exists(tl_path):
                with open(tl_path, "r") as f:
                    for line in f:
                        if line.strip():
                            top_levels.add(line.strip())
            continue
        if item.startswith("."):
            continue
        valid_items.append(item)
        
    # If top_level.txt explicitly defines the modules, trust it
    if top_levels:
        for tl in top_levels:
            if tl in valid_items:
                installables.append((os.path.join(extract_dir, tl), "/lib"))
            elif tl + ".py" in valid_items:
                installables.append((os.path.join(extract_dir, tl + ".py"), "/lib"))
        if installables:
            return installables

    # If top level has the exact package name, it's standard
    if package_name in valid_items:
        return [(os.path.join(extract_dir, package_name), "/lib")]
    if package_name + ".py" in valid_items:
        return [(os.path.join(extract_dir, package_name + ".py"), "/lib")]
        
    # Broken/Flat wheel: wrap its contents in /lib/{package_name}
    for item in valid_items:
        installables.append((os.path.join(extract_dir, item), f"/lib/{package_name}"))
        
    return installables

def install_mip_package(package_name, version, file_manager, log_callback):
    """Installs a package from micropython-lib v2 index."""
    try:
        # 1. Fetch manifest
        variant = "py" # Prefer source
        manifest_url = f"https://micropython.org/pi/v2/package/{variant}/{package_name}/{version}.json"
        log_callback(f"Fetching manifest from {manifest_url}...")
        
        req = urllib.request.Request(manifest_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            manifest = json.loads(response.read().decode('utf-8'))
        
        # 2. Download and upload files
        urls = manifest.get("urls", [])
        deps = manifest.get("deps", [])
        
        if deps:
            log_callback(f"Note: This package has dependencies: {', '.join(deps)}. Installing them is not yet automated in this step.")

        for dest, source_url in urls:
            # source_url might be "github:org/repo/path" or a full URL
            if source_url.startswith("github:"):
                # Convert github:org/repo/path to raw github user content URL
                parts = source_url[7:].split("/", 2)
                if len(parts) == 3:
                    org, repo, path = parts
                    # We assume master/main branch, mip usually knows which one to use but here we'll guess master or use a specific ref if available
                    source_url = f"https://raw.githubusercontent.com/{org}/{repo}/master/{path}"
            
            log_callback(f"Downloading {source_url} -> {dest}...")
            req = urllib.request.Request(source_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                file_data = response.read()
            
            # Ensure target directory exists on device
            remote_path = dest.lstrip("/") # Use relative path for microfs
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                _ensure_remote_dir(file_manager, remote_dir, log_callback)
            
            log_callback(f"Uploading to {remote_path}...")
            # Save to temporary local file first because FileManager.put expects a path
            with tempfile.NamedTemporaryFile(delete=False) as tf:
                tf.write(file_data)
                temp_name = tf.name
            try:
                file_manager.put(temp_name, remote_path)
            finally:
                if os.path.exists(temp_name):
                    os.remove(temp_name)
            
        return True, f"Successfully installed {package_name} {version} from micropython-lib."
    except Exception as e:
        logger.error(f"mip installation failed: {e}")
        return False, f"Failed to install from micropython-lib: {e}"

def _ensure_remote_dir(file_manager, remote_dir, log_callback):
    """Ensures a directory exists on the device, recursively."""
    parts = remote_dir.strip("/").split("/")
    current = ""
    for part in parts:
        if current:
            current += "/" + part
        else:
            current = part
        try:
            file_manager.mkdir(current)
            log_callback(f"Created directory {current}")
        except Exception:
            pass # Already exists or error
