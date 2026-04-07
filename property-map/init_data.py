"""Copy initial data to persistent disk on first deploy."""
import os
import shutil

SRC = os.path.join(os.path.dirname(__file__), "data")
DST = "/data"

if os.path.isdir(DST) and not os.path.exists(os.path.join(DST, "workspaces.json")):
    # First deploy - copy initial data
    for item in os.listdir(SRC):
        src_path = os.path.join(SRC, item)
        dst_path = os.path.join(DST, item)
        if os.path.isdir(src_path):
            if not os.path.exists(dst_path):
                shutil.copytree(src_path, dst_path)
        else:
            if not os.path.exists(dst_path):
                shutil.copy2(src_path, dst_path)
    print("Initial data copied to /data")
else:
    print("Data already exists or /data not available, skipping init")
