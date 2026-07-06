import os, struct, json

asar_path = "D:/code/manbo/dist/manbo/resources/app.asar"
if not os.path.exists(asar_path):
    print("asar not found, trying alternate paths...")
    import glob
    asar_files = glob.glob("D:/code/manbo/dist/**/app.asar", recursive=True)
    if asar_files:
        asar_path = asar_files[0]
        print(f"found: {asar_path}")
    else:
        print("no asar found anywhere")
        # Check dist directory
        for root, dirs, files in os.walk("D:/code/manbo/dist"):
            for f in files:
                if f.endswith(".asar"):
                    print(f"  {os.path.join(root, f)}")
        exit()

with open(asar_path, "rb") as f:
    head = f.read(4)
    header_size = struct.unpack("<I", head)[0]
    head_json = f.read(header_size)
    # Pad to 4 bytes
    pad = (4 - header_size % 4) % 4
    f.read(pad)
    data_start = f.tell()
    
    meta = json.loads(head_json)
    
    # Find index.html recursively
    def find_file(tree, target):
        if isinstance(tree, dict):
            if "files" in tree:
                for name, content in tree["files"].items():
                    if name == target:
                        return content
                    result = find_file(content, target)
                    if result:
                        return result
            elif "offset" in tree and "size" in tree:
                pass  # leaf file, not our target
        return None
    
    entry = find_file(meta, "index.html")
    if entry and entry.get("offset") is not None:
        offset = entry["offset"]
        size = entry["size"]
        f.seek(data_start + offset)
        content = f.read(size)
        out_path = "D:/code/manbo/renderer/index.html"
        with open(out_path, "wb") as out:
            out.write(content)
        print(f"recovered {size} bytes to {out_path}")
    else:
        print("index.html entry not found in asar header")
        print("Available files:")
        def list_files(tree, prefix=""):
            if isinstance(tree, dict):
                if "files" in tree:
                    for name, content in tree["files"].items():
                        if isinstance(content, dict) and "files" in content:
                            list_files(content, prefix + name + "/")
                        else:
                            print(f"  {prefix}{name}")
        list_files(meta)