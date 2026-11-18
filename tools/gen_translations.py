#!/usr/bin/env python3
"""Write the names from catalog.py into strings.json and translations/{en,nl}.json.

Run after adding a datapoint to catalog.py:  python3 tools/gen_translations.py
"""
import importlib
import json
import sys
import types
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "remeha_bluetooth"
pkg = types.ModuleType("remeha_pkg")
pkg.__path__ = [str(PKG)]
sys.modules["remeha_pkg"] = pkg
catalog = importlib.import_module("remeha_pkg.catalog")

TEXT = {
    "en": {
        "init_title": "Which sensors?",
        "init_desc": "**Simple**: the standard set (temperatures, COP, energy, status, power).\n\n**Advanced**: choose yourself from the full list of datapoints.",
        "mode": "Mode",
        "simple": "Simple (recommended)",
        "advanced": "Advanced: choose from the full list",
        "adv_title": "Choose datapoints",
        "adv_desc": "Tick what you want to see. Every extra item is one more Bluetooth read every 30 seconds. The code in brackets is the parameter code from the Remeha app.",
        "extras": "Datapoints",
    },
    "nl": {
        "init_title": "Welke sensoren?",
        "init_desc": "**Eenvoudig**: de standaardset (temperaturen, COP, energie, status, vermogen).\n\n**Geavanceerd**: kies zelf uit de volledige lijst met datapunten.",
        "mode": "Modus",
        "simple": "Eenvoudig (aanbevolen)",
        "advanced": "Geavanceerd: kies uit de volledige lijst",
        "adv_title": "Kies datapunten",
        "adv_desc": "Vink aan wat je wilt zien. Elk extra item is één Bluetooth-uitlezing extra per 30 seconden. De code tussen haakjes is de parametercode uit de Remeha-app.",
        "extras": "Datapunten",
    },
}


def update(path: Path, lang: str) -> None:
    data = json.loads(path.read_text())
    t = TEXT[lang]
    data["options"] = {
        "step": {
            "init": {"title": t["init_title"], "description": t["init_desc"],
                     "data": {"mode": t["mode"]}},
            "advanced": {"title": t["adv_title"], "description": t["adv_desc"],
                         "data": {"extras": t["extras"]}},
        }
    }
    labels = {}
    for e in catalog.EXTRAS:
        name = e.name_nl if lang == "nl" else e.name
        platform = "binary_sensor" if e.binary else "sensor"
        data["entity"].setdefault(platform, {})[e.key] = {"name": name}
        labels[e.key] = f"{name} ({e.code})" if e.code else name
    data["selector"] = {
        "mode": {"options": {"simple": t["simple"], "advanced": t["advanced"]}},
        "extras": {"options": labels},
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


update(PKG / "strings.json", "en")
update(PKG / "translations" / "en.json", "en")
update(PKG / "translations" / "nl.json", "nl")
print("ok")
