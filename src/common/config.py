"""Proje yolları ve ayar dosyalarının okunması. Sabit mutlak yol yalnızca machine_config.json'da bulunur."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
INPUTS_DIR = ROOT / "inputs"
NOSE_DIR = INPUTS_DIR / "nose_cones"
MESH_DIR = ROOT / "meshes"
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
DOCS_DIR = ROOT / "docs"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_machine_config() -> dict:
    path = ROOT / "machine_config.json"
    if not path.exists():
        raise FileNotFoundError(
            "machine_config.json yok. machine_config.example.json dosyasını kopyalayıp bu makineye göre düzenleyin."
        )
    return _read_json(path)


def load_nose_params() -> dict:
    return _read_json(CONFIG_DIR / "nose_params.json")


def load_velocities() -> list[dict]:
    return _read_json(CONFIG_DIR / "velocities.json")["points"]
