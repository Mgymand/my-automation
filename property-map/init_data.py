"""Copy initial data to working directory on deploy."""
import os
import shutil

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
    if not os.path.exists(os.path.join(DST, "workspaces.json")):
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
    else:
        print(f"Data already exists at {DST}")
else:
    print("Using local data directory")
