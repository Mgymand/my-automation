"""Copy initial data to working directory on deploy, and restore from GitHub."""
import os
import shutil
import json
import ssl
import base64
import urllib.request

SRC = os.path.join(os.path.dirname(__file__), "data")

# Determine destination
if os.path.isdir("/data") and os.access("/data", os.W_OK):
    DST = "/data"
elif os.environ.get("RENDER"):
    DST = "/tmp/property-data"
else:
    DST = SRC  # local dev, already in place

if DST != SRC:
    os.makedirs(DST, exist_ok=True)
    # Copy bundled data first
    for item in os.listdir(SRC):
        src_path = os.path.join(SRC, item)
        dst_path = os.path.join(DST, item)
        if os.path.isdir(src_path):
            if not os.path.exists(dst_path):
                shutil.copytree(src_path, dst_path)
        else:
            if not os.path.exists(dst_path):
                shutil.copy2(src_path, dst_path)
    print(f"Initial data copied to {DST}")

    # Restore from GitHub (overwrite with latest data + PDFs)
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "Mgymand/my-automation")
    GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "claude/frosty-swartz")
    if GITHUB_TOKEN:
        print("Restoring data from GitHub...")
        SSL_CTX = ssl.create_default_context()
        SSL_CTX.check_hostname = False
        SSL_CTX.verify_mode = ssl.CERT_NONE

        def gh_api(path):
            url = f"https://api.github.com{path}"
            req = urllib.request.Request(url, headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PropertyMapApp/1.0",
            })
            try:
                with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"  GitHub API error: {e}")
                return None

        def restore_dir(gh_path, local_dir):
            data = gh_api(f"/repos/{GITHUB_REPO}/contents/{gh_path}?ref={GITHUB_BRANCH}")
            if not data or not isinstance(data, list):
                return
            for item in data:
                local_path = os.path.join(local_dir, item["name"])
                if item["type"] == "dir":
                    os.makedirs(local_path, exist_ok=True)
                    restore_dir(item["path"], local_path)
                elif item["type"] == "file":
                    if not os.path.exists(local_path) or item["name"].endswith(".json"):
                        # Always overwrite JSON (latest data), skip existing PDFs
                        try:
                            file_data = gh_api(f"/repos/{GITHUB_REPO}/contents/{item['path']}?ref={GITHUB_BRANCH}")
                            if file_data and "content" in file_data:
                                content = base64.b64decode(file_data["content"])
                                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                                with open(local_path, "wb") as f:
                                    f.write(content)
                                print(f"  Restored: {item['name']}")
                        except Exception as e:
                            print(f"  Error restoring {item['name']}: {e}")

        restore_dir("property-map/data", DST)
        print("GitHub restore complete.")
    else:
        print("No GITHUB_TOKEN, skipping GitHub restore.")
else:
    print("Using local data directory")
