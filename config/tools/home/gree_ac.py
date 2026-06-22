"""
GREE AC tools: control GREE/EWPE WiFi air conditioners over their native UDP protocol.

Implements the GREE wire protocol (AES-128-ECB v1 / AES-128-GCM v2 encryption,
scan/bind/status/command flow) from scratch, based on marcinn2/gree-ac-mcp.
"""

import base64
import json
import socket
import time
from datetime import UTC, datetime
from os import getenv
from pathlib import Path
from typing import Annotated, Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv
from langchain.tools import tool
from pydantic import Field

load_dotenv()

# ---- Protocol constants ----

BROADCAST = "255.255.255.255"
UDP_PORT = 7000
GENERIC_KEY_V1 = b"a3K8Bx%2r8Y7#xDh"
GENERIC_KEY_V2 = b"{yxAHAY_Lm6pbC/<"
IV_V2 = bytes([0x54, 0x40, 0x78, 0x44, 0x49, 0x67, 0x5A, 0x51, 0x6C, 0x5E, 0x63, 0x13])
AAD_V2 = b"qualcomm-test"
TEMSEN_OFFSET = 40

FIELDS = {
    "power": "Pow",
    "mode": "Mod",
    "targetTemp": "SetTem",
    "tempUnit": "TemUn",
    "tempRec": "TemRec",
    "tempSensor": "TemSen",
    "fanSpeed": "WdSpd",
    "swingHorizontal": "SwingLfRig",
    "swingVertical": "SwUpDn",
    "xFan": "Blo",
    "freshAir": "Air",
    "health": "Health",
    "sleep": "SwhSlp",
    "sleepMode": "SlpMod",
    "light": "Lig",
    "quiet": "Quiet",
    "turbo": "Tur",
    "noFrost": "StHt",
    "heatCoolType": "HeatCoolType",
    "energySaving": "SvSt",
}
MODE = {"auto": 0, "cool": 1, "dry": 2, "fan": 3, "heat": 4}
FAN_SPEED = {
    "auto": 0,
    "low": 1,
    "mediumLow": 2,
    "medium": 3,
    "mediumHigh": 4,
    "high": 5,
}
VALID_FAN_SPEEDS = [*list(FAN_SPEED), "quiet", "turbo"]
QUIET = {"off": 0, "on": 2}
ON_OFF = {"off": 0, "on": 1}
TEMP_UNIT = {"celsius": 0, "fahrenheit": 1}
SWING_VERTICAL = {
    "default": 0,
    "full": 1,
    "fixed-top": 2,
    "fixed-upper-middle": 3,
    "fixed-middle": 4,
    "fixed-lower-middle": 5,
    "fixed-bottom": 6,
    "swing-bottom": 7,
    "swing-lower-middle": 8,
    "swing-middle": 9,
    "swing-upper-middle": 10,
    "swing-top": 11,
}
SWING_HORIZONTAL = {
    "default": 0,
    "full": 1,
    "fixed-left": 2,
    "fixed-center-left": 3,
    "fixed-center": 4,
    "fixed-center-right": 5,
    "fixed-right": 6,
}
STATUS_COLS = [v for k, v in FIELDS.items() if k != "tempSensor"] + [
    FIELDS["tempSensor"]
]

# ---- Config ----

_device_cache: dict[str, dict[str, Any]] = {}


def _norm_mac(mac: str) -> str:
    return mac.lower().replace(":", "").replace("-", "")


_config_path = getenv("GREE_MCP_CONFIG", "")


def _load_config() -> dict[str, dict[str, Any]]:
    """Load per-device overrides keyed by MAC from config JSON."""
    if not _config_path:
        return {}
    p = Path(_config_path)
    if not p.exists():
        return {}
    cfg = json.loads(p.read_text())
    overrides: dict[str, dict[str, Any]] = {}
    for d in cfg.get("devices", []):
        overrides[_norm_mac(d["mac"])] = d
    return overrides


def _scan_all(timeout: float = 3.0) -> dict[str, dict[str, Any]]:
    """Broadcast scan and collect all responding GREE devices."""
    discovered: dict[str, dict[str, Any]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(b'{"t":"scan"}', (BROADCAST, UDP_PORT))
        sock.settimeout(timeout)
        while True:
            try:
                data, rinfo = sock.recvfrom(4096)
                parsed = _unpack_message(data.decode("utf-8"))
                p = parsed["pack"]
                if str(p.get("t", "")).lower() == "dev":
                    mac = str(p.get("mac", p.get("cid", ""))).lower()
                    if mac and mac not in discovered:
                        discovered[mac] = {
                            "mac": mac,
                            "address": rinfo[0],
                            "name": p.get("name", mac),
                            "model": p.get("model"),
                            "encryptionVersion": 0,
                        }
            except TimeoutError:
                break
            except Exception:  # noqa: S112
                continue
    finally:
        sock.close()
    return discovered


def _build_devices() -> dict[str, dict[str, Any]]:
    """Scan LAN for devices, merge with config overrides, restore cached status."""
    discovered = _scan_all()
    for mac, override in _device_overrides.items():
        if mac in discovered:
            discovered[mac].update(override)
        else:
            discovered[mac] = override
        last = override.get("lastStatus")
        if last and mac not in _device_cache:
            _device_cache[mac] = {
                "key": b"",
                "address": override.get("address", BROADCAST),
                "port": UDP_PORT,
                "version": override.get("encryptionVersion", 0) or 1,
                "status": _encode_status(last),
                "last_seen": 0,
            }
    return discovered


def _persist_config() -> None:
    """Write all discovered device info + last-known decoded status back to config JSON."""
    if not _config_path:
        return
    devs = _device_state.get("devices", {})
    device_list = []
    for d in devs.values():
        entry = {k: v for k, v in d.items() if v is not None and k != "lastStatus"}
        mac_n = _norm_mac(d["mac"])
        cache = _device_cache.get(mac_n, {})
        st = cache.get("status", {})
        if st:
            decoded = _decode_status(d, st)
            decoded.pop("lastSeen", None)
            entry["lastStatus"] = decoded
        if "last_seen" in cache:
            entry["lastSeen"] = datetime.fromtimestamp(
                cache["last_seen"], tz=UTC
            ).isoformat()
        if entry:
            device_list.append(entry)
    cfg = {"devices": device_list}
    Path(_config_path).write_text(json.dumps(cfg, indent=2) + "\n")


_device_overrides = _load_config()
_device_state: dict[str, Any] = {"devices": {}, "loaded": False}


def _ensure_devices() -> None:
    """Lazy-load devices via LAN scan on first access."""
    if not _device_state["loaded"]:
        _device_state["devices"] = _build_devices()
        _device_state["loaded"] = True


# ---- Crypto ----


def _pkcs7_pad(data: bytes) -> bytes:
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    return data[: -data[-1]]


def _encrypt_v1(data: dict, key: bytes) -> str:
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305
    enc = cipher.encryptor()
    ct = enc.update(_pkcs7_pad(json.dumps(data).encode("utf-8"))) + enc.finalize()
    return base64.b64encode(ct).decode("ascii")


def _decrypt_v1(packed: str, key: bytes) -> dict:
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305
    dec = cipher.decryptor()
    pt = dec.update(base64.b64decode(packed)) + dec.finalize()
    return json.loads(_pkcs7_unpad(pt))


def _encrypt_v2(data: dict, key: bytes) -> tuple[str, str]:
    ct = AESGCM(key).encrypt(IV_V2, json.dumps(data).encode("utf-8"), AAD_V2)
    return base64.b64encode(ct[:-16]).decode("ascii"), base64.b64encode(
        ct[-16:]
    ).decode("ascii")


def _decrypt_v2(packed: str, tag: str, key: bytes) -> dict:
    ct = base64.b64decode(packed) + base64.b64decode(tag)
    pt = AESGCM(key).decrypt(IV_V2, ct, AAD_V2)
    return json.loads(pt)


# ---- Pack / Unpack ----


def _pack_message(
    message: dict, tcid: str, version: int, key: bytes | None = None
) -> str:
    i = 1 if key is None else 0
    if version == 1:
        k = key or GENERIC_KEY_V1
        pack = _encrypt_v1(message, k)
        return json.dumps(
            {"tcid": tcid, "uid": 0, "t": "pack", "pack": pack, "i": i, "cid": "app"}
        )
    k = key or GENERIC_KEY_V2
    pack, tag = _encrypt_v2(message, k)
    return json.dumps(
        {
            "tcid": tcid,
            "uid": 0,
            "t": "pack",
            "pack": pack,
            "i": i,
            "tag": tag,
            "cid": "app",
        }
    )


def _unpack_message(raw: str, key: bytes | None = None) -> dict:
    msg = json.loads(raw)
    if "pack" not in msg:
        raise ValueError("no pack field")
    i = msg.get("i", 0)
    if "tag" not in msg:
        k = GENERIC_KEY_V1 if i == 1 else (key or GENERIC_KEY_V1)
        return {"pack": _decrypt_v1(msg["pack"], k), "version": 1, "i": i}
    k = GENERIC_KEY_V2 if i == 1 else (key or GENERIC_KEY_V2)
    return {"pack": _decrypt_v2(msg["pack"], msg["tag"], k), "version": 2, "i": i}


# ---- Device communication ----


def _resolve_device(mac: str | None = None, name: str | None = None) -> dict | None:
    devs = _device_state["devices"]
    if mac:
        return devs.get(_norm_mac(mac))
    if name:
        for d in devs.values():
            if d["name"].lower() == name.lower():
                return d
    return None


def _handshake(device: dict) -> dict | None:
    """Bind to device (scan already done by _scan_all). Return cache entry or None."""
    mac = _norm_mac(device["mac"])
    addr = device.get("address", BROADCAST)
    enc_cfg = device.get("encryptionVersion", 0)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if addr == BROADCAST:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        try_versions = [enc_cfg] if enc_cfg in (1, 2) else [1, 2]
        for ver in try_versions:
            bind_msg = _pack_message({"mac": mac, "t": "bind", "uid": 0}, mac, ver)
            sock.sendto(bind_msg.encode("utf-8"), (addr, UDP_PORT))
            sock.settimeout(2.0)
            try:
                data, _ = sock.recvfrom(4096)
                parsed = _unpack_message(data.decode("utf-8"))
                p = parsed["pack"]
                if str(p.get("t", "")).lower() == "bindok":
                    return {
                        "key": str(p.get("key", "")).encode("utf-8"),
                        "address": addr,
                        "port": UDP_PORT,
                        "version": ver,
                        "status": {},
                        "last_seen": time.time(),
                        "info": device.get("info", {}),
                    }
            except Exception:  # noqa: S112
                continue
        return None
    finally:
        sock.close()


def _fetch_status(mac: str, cache: dict) -> dict | None:
    """Send status request, return raw status dict or None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        msg = _pack_message(
            {"mac": mac, "t": "status", "cols": STATUS_COLS},
            mac,
            cache["version"],
            cache["key"],
        )
        sock.sendto(msg.encode("utf-8"), (cache["address"], cache["port"]))
        sock.settimeout(2.0)
        try:
            data, _ = sock.recvfrom(4096)
            parsed = _unpack_message(data.decode("utf-8"), cache["key"])
            p = parsed["pack"]
            t = str(p.get("t", "")).lower()
            if t == "dat":
                return dict(zip(p.get("cols", []), p.get("dat", [])))
            if t == "res":
                return dict(zip(p.get("opt", []), p.get("p", p.get("val", []))))
        except Exception:
            return None
        return None
    finally:
        sock.close()


def _send_cmd(mac: str, cache: dict, cmd: dict) -> None:
    """Fire-and-forget command to device."""
    opt = list(cmd.keys())
    p = [cmd[k] for k in opt]
    for k in opt:
        cache["status"][k] = cmd[k]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        msg = _pack_message(
            {"t": "cmd", "opt": opt, "p": p}, mac, cache["version"], cache["key"]
        )
        sock.sendto(msg.encode("utf-8"), (cache["address"], cache["port"]))
    finally:
        sock.close()


def _send_and_verify(
    device: dict, cache: dict, cmd: dict, expected: dict
) -> dict[str, Any]:
    """Send command, re-fetch status, verify expected field values. Returns decoded status."""
    mac = _norm_mac(device["mac"])
    _send_cmd(mac, cache, cmd)
    time.sleep(0.5)
    st = _fetch_status(mac, cache)
    if st is not None:
        cache["status"] = st
        cache["last_seen"] = time.time()
    st = cache.get("status", {})
    all_ok = all(st.get(f) == v for f, v in expected.items())
    _persist_config()
    result = _decode_status(device, st)
    result["verified"] = all_ok
    return result


def _resolve_and_bind(
    mac: str | None = None, name: str | None = None, refresh: bool = False
) -> tuple[dict, dict] | str:
    """Resolve device and ensure bound. Returns (device, cache) or error string."""
    _ensure_devices()
    devs = _device_state["devices"]
    if not devs:
        return "No GREE devices found. Check config and network."
    if not mac and not name:
        if len(devs) == 1:
            device = next(iter(devs.values()))
        else:
            return "Multiple devices found. Provide 'mac' or 'name' to select one."
    else:
        device = _resolve_device(mac, name)
        if not device:
            return f"No configured device matches '{mac or name}'."
    return _bind_device(device, refresh)


def _bind_device(device: dict, refresh: bool) -> tuple[dict, dict] | str:
    """Ensure device is bound and return (device, cache) or error string."""
    mac_n = _norm_mac(device["mac"])
    cache = _device_cache.get(mac_n)

    if (
        cache
        and cache.get("key")
        and not refresh
        and time.time() - cache.get("last_seen", 0) < 60
    ):
        return (device, cache)

    if cache and cache.get("key"):
        st = _fetch_status(mac_n, cache)
        if st is not None:
            cache["status"] = st
            cache["last_seen"] = time.time()
            return (device, cache)

    cache = _handshake(device)
    if cache is None:
        return f"Device {mac_n} ({device['name']}) is not reachable."
    _device_cache[mac_n] = cache
    st = _fetch_status(mac_n, cache)
    if st is not None:
        cache["status"] = st
        cache["last_seen"] = time.time()
    return (device, cache)


# ---- Status decoding ----


def _name_for_value(mapping: dict, value: int | None) -> str | None:
    if value is None:
        return None
    for name, v in mapping.items():
        if v == value:
            return name
    return None


def _decode_temp(device: dict, status: dict) -> tuple[float | None, bool]:
    raw = status.get(FIELDS["tempSensor"])
    if raw is not None and 0 < raw < 100:
        return raw - TEMSEN_OFFSET + device.get("sensorOffset", 0), False
    if device.get("fakeSensor", False):
        return (
            status.get(FIELDS["targetTemp"], 25) + device.get("sensorOffset", 0),
            True,
        )
    return None, False


def _decode_status(device: dict, status: dict) -> dict:
    mac = _norm_mac(device["mac"])
    cache = _device_cache.get(mac, {})

    def _bool(code: str) -> bool | None:
        return status[code] == ON_OFF["on"] if code in status else None

    temp, est = _decode_temp(device, status)
    return {
        "mac": mac,
        "name": device["name"],
        "room": device.get("room"),
        "model": device.get("model") or (cache.get("info") or {}).get("model"),
        "online": bool(cache.get("key")),
        "bound": bool(cache.get("key")),
        "address": cache.get("address"),
        "power": _bool(FIELDS["power"]),
        "mode": _name_for_value(MODE, status.get(FIELDS["mode"])),
        "targetTemperature": status.get(FIELDS["targetTemp"]),
        "temperatureUnit": _name_for_value(TEMP_UNIT, status.get(FIELDS["tempUnit"])),
        "tempRec": status.get(FIELDS["tempRec"]),
        "currentTemperature": temp,
        "currentTemperatureEstimated": est,
        "fanSpeed": _name_for_value(FAN_SPEED, status.get(FIELDS["fanSpeed"])),
        "quiet": (
            status[FIELDS["quiet"]] == QUIET["on"]
            if FIELDS["quiet"] in status
            else None
        ),
        "turbo": _bool(FIELDS["turbo"]),
        "swingVertical": _name_for_value(
            SWING_VERTICAL, status.get(FIELDS["swingVertical"])
        ),
        "swingHorizontal": _name_for_value(
            SWING_HORIZONTAL, status.get(FIELDS["swingHorizontal"])
        ),
        "xFan": _bool(FIELDS["xFan"]),
        "light": _bool(FIELDS["light"]),
        "health": _bool(FIELDS["health"]),
        "sleep": _bool(FIELDS["sleep"]),
        "sleepMode": _bool(FIELDS["sleepMode"]),
        "freshAir": _bool(FIELDS["freshAir"]),
        "energySaving": _bool(FIELDS["energySaving"]),
        "noFrost": _bool(FIELDS["noFrost"]),
        "heatCoolType": status.get(FIELDS["heatCoolType"]),
        "lastSeen": (
            datetime.fromtimestamp(cache["last_seen"], tz=UTC).isoformat()
            if cache.get("last_seen")
            else None
        ),
    }


# Field encode spec: (decoded_key, field_key, reverse_map or None for passthrough)
_ENCODE_BOOL_FIELDS = [
    ("power", "power"),
    ("turbo", "turbo"),
    ("xFan", "xFan"),
    ("light", "light"),
    ("health", "health"),
    ("sleep", "sleep"),
    ("sleepMode", "sleepMode"),
    ("freshAir", "freshAir"),
    ("energySaving", "energySaving"),
    ("noFrost", "noFrost"),
]
_ENCODE_MAP_FIELDS = [
    ("mode", "mode", MODE),
    ("fanSpeed", "fanSpeed", FAN_SPEED),
    ("temperatureUnit", "tempUnit", TEMP_UNIT),
    ("swingVertical", "swingVertical", SWING_VERTICAL),
    ("swingHorizontal", "swingHorizontal", SWING_HORIZONTAL),
]
_ENCODE_PASSTHROUGH_FIELDS = [
    ("targetTemperature", "targetTemp"),
    ("tempRec", "tempRec"),
    ("heatCoolType", "heatCoolType"),
]


def _encode_status(decoded: dict) -> dict:
    """Convert human-readable decoded status back to raw field codes for cache."""
    raw: dict[str, Any] = {}
    for dk, fk in _ENCODE_BOOL_FIELDS:
        if decoded.get(dk) is not None:
            raw[FIELDS[fk]] = 1 if decoded[dk] else 0
    if decoded.get("quiet") is not None:
        raw[FIELDS["quiet"]] = 2 if decoded["quiet"] else 0
    for dk, fk, mapping in _ENCODE_MAP_FIELDS:
        if decoded.get(dk) is not None:
            raw[FIELDS[fk]] = mapping.get(decoded[dk], 0)
    if decoded.get("currentTemperature") is not None:
        raw[FIELDS["tempSensor"]] = int(decoded["currentTemperature"]) + TEMSEN_OFFSET
    for dk, fk in _ENCODE_PASSTHROUGH_FIELDS:
        if decoded.get(dk) is not None:
            raw[FIELDS[fk]] = decoded[dk]
    return raw


def _fan_speed_cmd(speed: str, steps: int) -> dict:
    if speed == "quiet":
        return {
            FIELDS["quiet"]: QUIET["on"],
            FIELDS["turbo"]: ON_OFF["off"],
            FIELDS["fanSpeed"]: FAN_SPEED["auto"],
        }
    if speed == "turbo":
        return {FIELDS["turbo"]: ON_OFF["on"], FIELDS["quiet"]: QUIET["off"]}
    # 3-step units map medium-low->low, medium-high->high
    m = {
        "auto": FAN_SPEED["auto"],
        "low": FAN_SPEED["low"],
        "medium-low": FAN_SPEED["low"] if steps == 3 else FAN_SPEED["mediumLow"],
        "medium": FAN_SPEED["medium"],
        "medium-high": FAN_SPEED["high"] if steps == 3 else FAN_SPEED["mediumHigh"],
        "high": FAN_SPEED["high"],
    }
    return {
        FIELDS["fanSpeed"]: m[speed],
        FIELDS["quiet"]: QUIET["off"],
        FIELDS["turbo"]: ON_OFF["off"],
    }


# ---- Tools ----

_mac_desc = "Device MAC address (12 hex digits). Omit if only one device."
_name_desc = "Device name. Omit if only one device."


@tool
def list_gree_ac_devices() -> dict[str, Any]:
    """List all GREE AC units with live status (power, mode, temp, fan, swing)."""
    _ensure_devices()
    devices = []
    for mac, d in _device_state["devices"].items():
        result = _bind_device(d, refresh=True)
        if isinstance(result, str):
            devices.append({"mac": mac, "name": d["name"], "error": result})
        else:
            _, cache = result
            devices.append(_decode_status(d, cache.get("status", {})))
    _persist_config()
    return {"devices": devices}


@tool
def get_gree_ac_device_status(
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Get full live status of one AC unit: power, mode, temps, fan, swing, flags."""
    result = _resolve_and_bind(mac, name, refresh=True)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    return _decode_status(device, cache.get("status", {}))


@tool
def get_gree_ac_room_temperature(
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Get current room temperature in °C from the AC's built-in sensor."""
    result = _resolve_and_bind(mac, name, refresh=True)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    celsius, estimated = _decode_temp(device, cache.get("status", {}))
    mac_n = _norm_mac(device["mac"])
    if celsius is None:
        return {
            "mac": mac_n,
            "name": device["name"],
            "temperature": None,
            "estimated": False,
            "note": "No usable sensor and fakeSensor is disabled.",
        }
    return {
        "mac": mac_n,
        "name": device["name"],
        "temperature": round(celsius * 10) / 10,
        "unit": "C",
        "estimated": estimated,
    }


@tool
def set_gree_ac_power(
    on: Annotated[bool, Field(description="true = power on, false = power off")],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Power an AC unit on or off."""
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    power_val = ON_OFF["on"] if on else ON_OFF["off"]
    return _send_and_verify(
        device, cache, {FIELDS["power"]: power_val}, {FIELDS["power"]: power_val}
    )


@tool
def set_gree_ac_mode(
    mode: Annotated[str, Field(description="Mode: auto, cool, dry, fan, or heat")],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Set AC operating mode. Also powers the unit on."""
    if mode not in MODE:
        return {"error": f"Invalid mode '{mode}'. Valid: {list(MODE)}"}
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    mode_val = MODE[mode]
    power_val = ON_OFF["on"]
    return _send_and_verify(
        device,
        cache,
        {FIELDS["mode"]: mode_val, FIELDS["power"]: power_val},
        {FIELDS["mode"]: mode_val, FIELDS["power"]: power_val},
    )


@tool
def set_gree_ac_target_temperature(
    temperature: Annotated[
        float, Field(description="Target temperature in °C (16-30)")
    ],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Set target cooling/heating temperature in °C."""
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    mac_n = _norm_mac(device["mac"])
    min_t = device.get("minimumTargetTemperature", 16)
    max_t = device.get("maximumTargetTemperature", 30)
    if temperature < min_t or temperature > max_t:
        return {
            "error": f"Temperature {temperature}C is out of range for {mac_n} (allowed {min_t}-{max_t}C)."
        }
    set_tem = round(temperature)
    return _send_and_verify(
        device,
        cache,
        {FIELDS["targetTemp"]: set_tem, FIELDS["tempUnit"]: TEMP_UNIT["celsius"]},
        {FIELDS["targetTemp"]: set_tem, FIELDS["tempUnit"]: TEMP_UNIT["celsius"]},
    )


@tool
def set_gree_ac_fan_speed(
    speed: Annotated[
        str,
        Field(
            description="Fan speed: auto, quiet, low, medium-low, medium, medium-high, high, turbo"
        ),
    ],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Set fan speed. 'quiet' and 'turbo' are dedicated modes."""
    if speed not in VALID_FAN_SPEEDS:
        return {"error": f"Invalid speed '{speed}'. Valid: {VALID_FAN_SPEEDS}"}
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    steps = device.get("speedSteps", 5)
    cmd = _fan_speed_cmd(speed, steps)
    return _send_and_verify(device, cache, cmd, cmd)


@tool
def set_gree_ac_oscillation(
    on: Annotated[bool, Field(description="true = louver swing on, false = fixed")],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Enable/disable louver swing (vertical and horizontal)."""
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    osc = device.get("oscillation", {})
    positions = osc.get("on" if on else "off", {})
    vert = positions.get("vertical", "full" if on else "default")
    horiz = positions.get("horizontal", "full" if on else "default")
    cmd = {}
    if vert in SWING_VERTICAL:
        cmd[FIELDS["swingVertical"]] = SWING_VERTICAL[vert]
    if horiz in SWING_HORIZONTAL:
        cmd[FIELDS["swingHorizontal"]] = SWING_HORIZONTAL[horiz]
    if not cmd:
        return {"error": "No valid swing positions configured for this device."}
    return _send_and_verify(device, cache, cmd, cmd)


@tool
def set_gree_ac_xfan(
    on: Annotated[bool, Field(description="true = enable, false = disable")],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Toggle X-Fan: keeps fan running after power-off to dry the coil."""
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    mac_n = _norm_mac(device["mac"])
    if not device.get("xFan", False):
        return {
            "error": f'X-Fan is not enabled for {mac_n} ({device["name"]}); set "xFan": true in config to use it.'
        }
    xfan_val = ON_OFF["on"] if on else ON_OFF["off"]
    return _send_and_verify(
        device, cache, {FIELDS["xFan"]: xfan_val}, {FIELDS["xFan"]: xfan_val}
    )


@tool
def set_gree_ac_light(
    on: Annotated[bool, Field(description="true = display on, false = display off")],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Toggle the front-panel display LED on/off."""
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    mac_n = _norm_mac(device["mac"])
    if not device.get("lightControl", False):
        return {
            "error": f'Light control is not enabled for {mac_n} ({device["name"]}); set "lightControl": true in config.'
        }
    light_val = ON_OFF["on"] if on else ON_OFF["off"]
    return _send_and_verify(
        device, cache, {FIELDS["light"]: light_val}, {FIELDS["light"]: light_val}
    )


@tool
def set_gree_ac_quiet_mode(
    on: Annotated[bool, Field(description="true = enable, false = disable")],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Toggle quiet mode (lowers fan noise). Disables turbo when enabled."""
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    cmd: dict[str, int] = {FIELDS["quiet"]: QUIET["on"] if on else QUIET["off"]}
    if on:
        cmd[FIELDS["turbo"]] = ON_OFF["off"]
    return _send_and_verify(device, cache, cmd, cmd)


@tool
def set_gree_ac_turbo_mode(
    on: Annotated[bool, Field(description="true = enable, false = disable")],
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Toggle turbo mode (max fan power). Disables quiet when enabled."""
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    cmd: dict[str, int] = {FIELDS["turbo"]: ON_OFF["on"] if on else ON_OFF["off"]}
    if on:
        cmd[FIELDS["quiet"]] = QUIET["off"]
    return _send_and_verify(device, cache, cmd, cmd)


# ---- High-level convenience tools ----


@tool
def list_home_ac() -> dict[str, Any]:
    """List all home AC units with live status. Use this first to discover available units."""
    return list_gree_ac_devices.invoke({})


@tool
def status_home_ac(
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Get full live status of a home AC unit. Omit mac/name if only one unit."""
    return get_gree_ac_device_status.invoke({"mac": mac, "name": name})


@tool
def set_home_ac(
    power: Annotated[
        bool | None,
        Field(description="Power on/off. Omit to leave unchanged.", default=None),
    ] = None,
    mode: Annotated[
        str | None,
        Field(
            description="Mode: auto, cool, dry, fan, heat. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    temperature: Annotated[
        int | None,
        Field(
            description="Target temperature in °C (16-30). Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    fan_speed: Annotated[
        str | None,
        Field(
            description="Fan speed: auto, quiet, low, medium-low, medium, medium-high, high, turbo. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    oscillation: Annotated[
        bool | None,
        Field(
            description="Louver swing on/off. Omit to leave unchanged.", default=None
        ),
    ] = None,
    xfan: Annotated[
        bool | None,
        Field(
            description="X-Fan (coil drying) on/off. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    light: Annotated[
        bool | None,
        Field(description="Display LED on/off. Omit to leave unchanged.", default=None),
    ] = None,
    quiet: Annotated[
        bool | None,
        Field(description="Quiet mode on/off. Omit to leave unchanged.", default=None),
    ] = None,
    turbo: Annotated[
        bool | None,
        Field(description="Turbo mode on/off. Omit to leave unchanged.", default=None),
    ] = None,
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """
    Set one or more AC settings at once. Only provided parameters are applied.
    Prefer this over individual set_* tools when changing multiple settings.
    """
    result = _resolve_and_bind(mac, name)
    if isinstance(result, str):
        return {"error": result}
    device, cache = result
    cmd: dict[str, int] = {}
    expected: dict[str, int] = {}
    errors: list[str] = []

    if power is not None:
        v = ON_OFF["on"] if power else ON_OFF["off"]
        cmd[FIELDS["power"]] = v
        expected[FIELDS["power"]] = v

    if mode is not None:
        if mode not in MODE:
            errors.append(f"Invalid mode '{mode}'. Valid: {list(MODE)}")
        else:
            cmd[FIELDS["mode"]] = MODE[mode]
            cmd[FIELDS["power"]] = ON_OFF["on"]
            expected[FIELDS["mode"]] = MODE[mode]
            expected[FIELDS["power"]] = ON_OFF["on"]

    if temperature is not None:
        min_t = device.get("minimumTargetTemperature", 16)
        max_t = device.get("maximumTargetTemperature", 30)
        if temperature < min_t or temperature > max_t:
            errors.append(f"Temperature {temperature} out of range ({min_t}-{max_t}).")
        else:
            set_tem = round(temperature)
            cmd[FIELDS["targetTemp"]] = set_tem
            cmd[FIELDS["tempUnit"]] = TEMP_UNIT["celsius"]
            expected[FIELDS["targetTemp"]] = set_tem

    if fan_speed is not None:
        if fan_speed not in VALID_FAN_SPEEDS:
            errors.append(f"Invalid fan_speed '{fan_speed}'. Valid: {VALID_FAN_SPEEDS}")
        else:
            steps = device.get("speedSteps", 5)
            fan_cmd = _fan_speed_cmd(fan_speed, steps)
            cmd.update(fan_cmd)
            expected.update(fan_cmd)

    if oscillation is not None:
        osc = device.get("oscillation", {})
        positions = osc.get("on" if oscillation else "off", {})
        vert = positions.get("vertical", "full" if oscillation else "default")
        horiz = positions.get("horizontal", "full" if oscillation else "default")
        if vert in SWING_VERTICAL:
            cmd[FIELDS["swingVertical"]] = SWING_VERTICAL[vert]
            expected[FIELDS["swingVertical"]] = SWING_VERTICAL[vert]
        if horiz in SWING_HORIZONTAL:
            cmd[FIELDS["swingHorizontal"]] = SWING_HORIZONTAL[horiz]
            expected[FIELDS["swingHorizontal"]] = SWING_HORIZONTAL[horiz]

    if xfan is not None:
        if not device.get("xFan", False):
            errors.append("X-Fan not enabled for this device.")
        else:
            v = ON_OFF["on"] if xfan else ON_OFF["off"]
            cmd[FIELDS["xFan"]] = v
            expected[FIELDS["xFan"]] = v

    if light is not None:
        if not device.get("lightControl", False):
            errors.append("Light control not enabled for this device.")
        else:
            v = ON_OFF["on"] if light else ON_OFF["off"]
            cmd[FIELDS["light"]] = v
            expected[FIELDS["light"]] = v

    if quiet is not None:
        cmd[FIELDS["quiet"]] = QUIET["on"] if quiet else QUIET["off"]
        expected[FIELDS["quiet"]] = cmd[FIELDS["quiet"]]
        if quiet:
            cmd[FIELDS["turbo"]] = ON_OFF["off"]

    if turbo is not None:
        cmd[FIELDS["turbo"]] = ON_OFF["on"] if turbo else ON_OFF["off"]
        expected[FIELDS["turbo"]] = cmd[FIELDS["turbo"]]
        if turbo:
            cmd[FIELDS["quiet"]] = QUIET["off"]

    if errors:
        return {"error": "; ".join(errors)}
    if not cmd:
        return {"error": "No settings provided. Specify at least one parameter."}

    return _send_and_verify(device, cache, cmd, expected)


if __name__ == "__main__":
    import json as _json

    print("=== list_home_ac ===")
    r = list_home_ac.invoke({})
    print(_json.dumps(r, indent=2, default=str))

    print("\n=== status_home_ac ===")
    r = status_home_ac.invoke({})
    print(_json.dumps(r, indent=2, default=str))
