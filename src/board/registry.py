"""Discovers agent definitions from a directory of *.json files (BOARD_AGENTS_DIR).
Adding an agent = dropping a file in; no code references any agent by name."""
import glob
import json
import os


def load_agents(directory):
    agents = []
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        with open(path) as f:
            data = json.load(f)
        for a in (data if isinstance(data, list) else [data]):
            if "name" in a:
                agents.append(a)
    return agents
