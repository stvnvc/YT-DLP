import json
import os
import sys
from dataclasses import dataclass, asdict

# When frozen by PyInstaller, __file__ points to a temp folder.
# Resolve relative to the .exe so config.json lives next to it.
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(_APP_DIR, "config.json")


@dataclass
class Config:
    download_folder: str = ""
    cut_folder: str = ""

    @classmethod
    def load(cls) -> "Config":
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump(asdict(self), f, indent=2)
