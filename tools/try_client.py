#!/usr/bin/env python3
"""Try the integration's client code from a laptop (no Home Assistant needed).

    python3 tools/try_client.py              # scan for EHC-16_*, read once
    PIN=123456 python3 tools/try_client.py   # also bond with the PIN if needed

Loads custom_components/remeha_bluetooth/{protocol,client,pairing}.py without the
HA package __init__, so it tests exactly the code that runs in Home Assistant.
"""
import asyncio
import importlib
import os
import sys
import types
from pathlib import Path

from bleak import BleakClient, BleakScanner

PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "remeha_bluetooth"
pkg = types.ModuleType("remeha_pkg")
pkg.__path__ = [str(PKG_DIR)]
sys.modules["remeha_pkg"] = pkg
client_mod = importlib.import_module("remeha_pkg.client")
pairing = importlib.import_module("remeha_pkg.pairing")


async def main() -> None:
    dev = await BleakScanner.find_device_by_filter(
        lambda d, a: (a.local_name or d.name or "").startswith("EHC-16"), timeout=15)
    if not dev:
        print("No EHC-16 gateway found")
        return
    print("found", dev.name)
    pin = os.environ.get("PIN")
    if pin:
        await pairing.async_ensure_paired(dev.address, pin)
    print("bonded:", await pairing.async_is_paired(dev.address))
    async with BleakClient(dev, timeout=20) as c:
        s = client_mod.RemehaSession(c)
        await s.authenticate()
        data = await s.read_all()
        for k, v in data.values.items():
            print(f"  {k:28s} {v}")


asyncio.run(main())
