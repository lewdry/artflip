import json

with open("delete.json") as f:
    data = [line.strip().replace('.jpg', '') for line in f if line.strip()]

with open("output.json", "w") as f:
    json.dump(data, f, indent=2)
