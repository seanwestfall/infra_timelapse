import csv
import os
import json
import requests
from datetime import datetime
from config import *

BASE_URL = "https://maps.googleapis.com/maps/api/staticmap"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch_satellite_image(port):
    date_tag = datetime.utcnow().strftime("%Y-%m-%d")

    port_dir = os.path.join(OUTPUT_DIR, port["name"])
    os.makedirs(port_dir, exist_ok=True)

    filename = f"{date_tag}.png"
    filepath = os.path.join(port_dir, filename)

    params = {
        "center": f'{port["lat"]},{port["lon"]}',
        "zoom": port["zoom"],
        "size": IMAGE_SIZE,
        "maptype": MAP_TYPE,
        "key": API_KEY
    }

    r = requests.get(BASE_URL, params=params, timeout=30)
    r.raise_for_status()

    with open(filepath, "wb") as f:
        f.write(r.content)

    return filepath

def log_metadata(port, filepath):
    entry = {
        "port": port["name"],
        "bloc": port["bloc"],
        "lat": port["lat"],
        "lon": port["lon"],
        "image": filepath,
        "timestamp": datetime.utcnow().isoformat()
    }

    metadata_file = "metadata.json"

    if os.path.exists(metadata_file):
        with open(metadata_file, "r") as f:
            data = json.load(f)
    else:
        data = []

    data.append(entry)

    with open(metadata_file, "w") as f:
        json.dump(data, f, indent=2)

def main():
    with open("ports.csv", newline="") as f:
        reader = csv.DictReader(f)
        for port in reader:
            print(f"Fetching {port['name']}...")
            img_path = fetch_satellite_image(port)
            log_metadata(port, img_path)

if __name__ == "__main__":
    main()
