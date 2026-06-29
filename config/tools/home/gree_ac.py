"""GREE AC control: EWPE/UDP protocol, telemetry, and graphing."""

import logging
from atexit import register
from base64 import b64decode, b64encode
from bisect import bisect_left
from contextlib import suppress
from datetime import datetime, timedelta, tzinfo
from json import JSONDecodeError, dumps, loads
from pathlib import Path
from re import match
from signal import SIGTERM, signal
from socket import AF_INET, SO_BROADCAST, SO_REUSEADDR, SOCK_DGRAM, SOL_SOCKET, socket
from threading import Event, Lock, RLock, Thread
from typing import Annotated, Any

logging.getLogger("matplotlib").setLevel(logging.WARNING)

import matplotlib.pyplot as plt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv
from langchain.tools import tool
from matplotlib import use
from matplotlib.collections import LineCollection
from matplotlib.dates import DateFormatter, DayLocator, date2num
from matplotlib.lines import Line2D
from pydantic import BaseModel, Field

use("Agg")
load_dotenv()


# ============================================================
# CONSTANTS
# ============================================================

BROADCAST = "255.255.255.255"
UDP_PORT = 7000
GENERIC_KEY_V1 = b"a3K8Bx%2r8Y7#xDh"
GENERIC_KEY_V2 = b"{yxAHAY_Lm6pbC/<"
IV_V2 = bytes([0x54, 0x40, 0x78, 0x44, 0x49, 0x67, 0x5A, 0x51, 0x6C, 0x5E, 0x63, 0x13])
AAD_V2 = b"qualcomm-test"
TEMSEN_OFFSET = 40

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "gree_ac"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
with suppress(PermissionError):
    _DATA_DIR.chmod(0o777)


def _device_dir(mac: str) -> Path:
    """Return per-device data directory, ensuring subdirs exist."""
    d = _DATA_DIR / mac.lower().replace(":", "").replace("-", "")
    for sub in ("", "telemetry", "graphs"):
        p = d / sub if sub else d
        p.mkdir(parents=True, exist_ok=True)
        with suppress(PermissionError):
            p.chmod(0o777)
    return d


def _local_tz() -> tzinfo | None:
    """Return the local system timezone."""
    return datetime.now().astimezone().tzinfo


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
    "time": "time",
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

_FIELDS_REV = {v: k for k, v in FIELDS.items()}
_MODE_REV = {v: k for k, v in MODE.items()}
_FAN_REV = {v: k for k, v in FAN_SPEED.items()}


class ScheduleConfig(BaseModel):
    """Create or update a scheduled timer on the AC unit."""

    hour: int = Field(description="Hour (0-23)")
    minute: int = Field(description="Minute (0-59)")
    power_on: bool = Field(
        description="True = turn AC on at scheduled time, False = turn off"
    )
    weekdays: list[int] | None = Field(
        default=None,
        description="Days of week to repeat: 0=Sun..6=Sat. Default: weekdays.",
    )
    schedule_id: int | None = Field(
        default=None,
        description="Schedule ID (0-15) to update. Auto-assigned if omitted.",
    )


# ============================================================
# API CLIENT
# ============================================================


class GREEACClient:
    """Low-level GREE/EWPE wire protocol client (UDP + AES)."""

    def __init__(self) -> None:
        """Initialize client: load per-device config overrides, prepare device cache."""
        self._cache: dict[str, dict[str, Any]] = {}
        self._schedules: dict[str, list[dict[str, Any]]] = {}
        self._state: dict[str, Any] = {"devices": {}, "loaded": False}
        self._overrides: dict[str, dict[str, Any]] = {}
        for config_path in _DATA_DIR.glob("*/config.json"):
            with suppress(JSONDecodeError, OSError):
                raw = config_path.read_bytes().rstrip(b"\x00").decode("utf-8")
                for d in loads(raw).get("devices", []):
                    self._overrides[self._norm(d["mac"])] = d
        self._lock = RLock()

    @staticmethod
    def _norm(mac: str) -> str:
        """Normalize MAC address: lowercase, strip separators."""
        return mac.lower().replace(":", "").replace("-", "")

    # ---- Crypto ----

    @staticmethod
    def _pad(data: bytes) -> bytes:
        """PKCS7 pad to 16-byte block."""
        n = 16 - (len(data) % 16)
        return data + bytes([n] * n)

    @staticmethod
    def _unpad(data: bytes) -> bytes:
        """Remove PKCS7 padding."""
        return data[: -data[-1]]

    def _enc_v1(self, data: dict, key: bytes) -> str:
        """AES-128-ECB encrypt + base64 encode."""
        c = Cipher(algorithms.AES(key), modes.ECB())
        e = c.encryptor()
        return b64encode(
            e.update(self._pad(dumps(data).encode("utf-8"))) + e.finalize()
        ).decode("ascii")

    def _dec_v1(self, packed: str, key: bytes) -> dict:
        """Base64 decode + AES-128-ECB decrypt."""
        c = Cipher(algorithms.AES(key), modes.ECB())
        d = c.decryptor()
        return loads(self._unpad(d.update(b64decode(packed)) + d.finalize()))

    def _enc_v2(self, data: dict, key: bytes) -> tuple[str, str]:
        """AES-128-GCM encrypt, return (ciphertext, tag) as base64."""
        ct = AESGCM(key).encrypt(IV_V2, dumps(data).encode("utf-8"), AAD_V2)
        return b64encode(ct[:-16]).decode("ascii"), b64encode(ct[-16:]).decode("ascii")

    def _dec_v2(self, packed: str, tag: str, key: bytes) -> dict:
        """Base64 decode + AES-128-GCM decrypt."""
        return loads(
            AESGCM(key).decrypt(IV_V2, b64decode(packed) + b64decode(tag), AAD_V2)
        )

    def _pack(
        self, message: dict, tcid: str, version: int, key: bytes | None = None
    ) -> str:
        """Encrypt + wrap message in GREE wire protocol envelope."""
        i = 1 if key is None else 0
        if version == 1:
            k = key or GENERIC_KEY_V1
            p = self._enc_v1(message, k)
            return dumps(
                {"tcid": tcid, "uid": 0, "t": "pack", "pack": p, "i": i, "cid": "app"}
            )
        k = key or GENERIC_KEY_V2
        p, tag = self._enc_v2(message, k)
        return dumps(
            {
                "tcid": tcid,
                "uid": 0,
                "t": "pack",
                "pack": p,
                "i": i,
                "tag": tag,
                "cid": "app",
            }
        )

    def _unpack(self, raw: str, key: bytes | None = None) -> dict:
        """Parse wire envelope, detect version, decrypt inner pack."""
        msg = loads(raw)
        if "pack" not in msg:
            raise ValueError("no pack field")
        i = msg.get("i", 0)
        if "tag" not in msg:
            k = GENERIC_KEY_V1 if i == 1 else (key or GENERIC_KEY_V1)
            return {"pack": self._dec_v1(msg["pack"], k), "version": 1, "i": i}
        k = GENERIC_KEY_V2 if i == 1 else (key or GENERIC_KEY_V2)
        return {"pack": self._dec_v2(msg["pack"], msg["tag"], k), "version": 2, "i": i}

    # ---- Network ----

    def _send(self, addr: str, data: dict, timeout: float = 2.0) -> dict | None:
        """Low-level UDP send, returns response pack or None."""
        _key = data.pop("_key", None)
        _ver = data.pop("_ver", 1)
        sock = socket(AF_INET, SOCK_DGRAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        try:
            msg = self._pack(data, addr, _ver, _key)
            sock.sendto(msg.encode("utf-8"), (addr, UDP_PORT))
            sock.settimeout(timeout)
            try:
                parsed = self._unpack(sock.recvfrom(4096)[0].decode("utf-8"), _key)
                return parsed["pack"]
            except TimeoutError:
                return None
        finally:
            sock.close()

    def _udp_send(
        self, addr: str, payload: bytes, timeout: float = 2.0
    ) -> bytes | None:
        """Raw UDP send (for scan/bind which use generic keys)."""
        sock = socket(AF_INET, SOCK_DGRAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        if addr == BROADCAST:
            sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        try:
            sock.sendto(payload, (addr, UDP_PORT))
            sock.settimeout(timeout)
            try:
                return sock.recvfrom(4096)[0]
            except TimeoutError:
                return None
        finally:
            sock.close()

    # ---- Device discovery ----

    def discover(self) -> dict[str, dict[str, Any]]:
        """Broadcast scan, return dict of discovered devices keyed by MAC."""
        found: dict[str, dict[str, Any]] = {}
        sock = socket(AF_INET, SOCK_DGRAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        try:
            sock.sendto(b'{"t":"scan"}', (BROADCAST, UDP_PORT))
            sock.settimeout(3.0)
            while True:
                try:
                    data, rinfo = sock.recvfrom(4096)
                    parsed = self._unpack(data.decode("utf-8"))
                    p = parsed["pack"]
                    if str(p.get("t", "")).lower() == "dev":
                        mac = str(p.get("mac", p.get("cid", ""))).lower()
                        if mac and mac not in found:
                            found[mac] = {
                                "mac": mac,
                                "address": rinfo[0],
                                "name": p.get("name", mac),
                                "model": p.get("model"),
                                "encryptionVersion": 0,
                                "info": dict(p),
                            }
                except TimeoutError:
                    break
                except Exception:
                    continue
        finally:
            sock.close()
        return found

    def _bind(self, device: dict, version_hint: int = 0) -> dict | None:
        """Bind to device, return cache entry or None."""
        mac = self._norm(device["mac"])
        addr = device.get("address", BROADCAST)
        for ver in [version_hint] if version_hint else [1, 2]:
            payload = self._pack({"mac": mac, "t": "bind", "uid": 0}, mac, ver).encode(
                "utf-8"
            )
            resp = self._udp_send(addr, payload)
            if resp is None:
                continue
            try:
                p = self._unpack(resp.decode("utf-8"))["pack"]
                if str(p.get("t", "")).lower() == "bindok":
                    return {
                        "key": str(p.get("key", "")).encode("utf-8"),
                        "address": addr,
                        "port": UDP_PORT,
                        "version": ver,
                        "status": {},
                        "last_seen": datetime.now(_local_tz()).timestamp(),
                        "info": device.get("info", {}),
                    }
            except Exception:
                continue
        return None

    def _status(
        self, mac: str, cache: dict, cols: list[str] | None = None
    ) -> dict | None:
        """Fetch status for given cols. Returns decoded {field: value} or None."""
        d = {
            "mac": mac,
            "t": "status",
            "cols": cols or STATUS_COLS,
            "_ver": cache["version"],
            "_key": cache["key"],
        }
        st = self._send(cache["address"], d)
        if st is None:
            return None
        t = str(st.get("t", "")).lower()
        if t == "dat":
            return dict(zip(st.get("cols", []), st.get("dat", [])))
        if t == "res":
            return dict(zip(st.get("opt", []), st.get("p", st.get("val", []))))
        return None

    def _query_timers(self, mac: str, cache: dict) -> list[dict] | None:
        """
        Query all scheduled timers via the 'queryT' command.

        The Gree protocol uses a dedicated 'queryT' message type to read
        back timer/schedule entries — a status request with cols=['schedules']
        does not return schedule data.

        Some firmware versions (e.g. V1.x) accept setT but don't respond to
        queryT. In that case we fall back to the local schedule cache that is
        maintained by set_schedule/delete_schedule.
        """
        d = {
            "mac": mac,
            "t": "queryT",
            "count": 16,
            "index": 0,
            "_ver": cache["version"],
            "_key": cache["key"],
        }
        resp = self._send(cache["address"], d)
        if resp is not None:
            for key in ("tlist", "timers", "list"):
                if key in resp and isinstance(resp[key], list):
                    return resp[key]
            if isinstance(resp, list):
                return resp
            return []
        # Device didn't respond to queryT — use local cache
        return self._schedules.get(mac, [])

    def _cmd(
        self, _mac: str, cache: dict, opt: list[str], p: list, sub: str | None = None
    ) -> dict | None:
        """Send command, return response. Optional 'sub' for time sync."""
        cmd = {
            "t": "cmd",
            "opt": opt,
            "p": p,
            "_ver": cache["version"],
            "_key": cache["key"],
        }
        if sub:
            cmd["sub"] = sub
        resp = self._send(cache["address"], cmd)
        if resp is not None:
            for idx, k in enumerate(opt):
                cache["status"][k] = p[idx]
        return resp

    def _resolve_one(
        self, mac: str | None = None, name: str | None = None, refresh: bool = False
    ) -> tuple[dict, dict]:
        """Resolve device to (device, cache). Raises string on failure."""
        r = self.resolve(mac, name, refresh=refresh)
        if isinstance(r, str):
            raise ValueError(r)  # noqa: TRY004
        return r

    def _ensure(self) -> None:
        """Lazy-init: scan + merge config overrides."""
        if not self._state["loaded"]:
            discovered = self.discover()
            for mac, override in self._overrides.items():
                if mac in discovered:
                    discovered[mac].update(override)
                else:
                    discovered[mac] = override
                last = override.get("lastStatus")
                if mac not in self._cache:
                    self._cache[mac] = {
                        "key": b"",
                        "address": override.get("address", BROADCAST),
                        "port": UDP_PORT,
                        "version": override.get("encryptionVersion", 0) or 1,
                        "status": self._encode(last) if last else {},
                        "last_seen": 0,
                    }
            for mac in self._overrides:
                self._load_schedules(mac)
            self._state["devices"] = discovered
            self._state["loaded"] = True

    def _load_schedules(self, mac: str) -> None:
        """Load persisted local schedule cache for a device."""
        path = _device_dir(mac) / "schedules.json"
        with suppress(JSONDecodeError, OSError):
            self._schedules[mac] = loads(
                path.read_bytes().rstrip(b"\x00").decode("utf-8")
            )
        if mac not in self._schedules:
            self._schedules[mac] = []

    def _save_schedules(self, mac: str) -> None:
        """Persist local schedule cache for a device."""
        path = _device_dir(mac) / "schedules.json"
        path.write_text(dumps(self._schedules.get(mac, []), indent=2) + "\n")
        with suppress(PermissionError):
            path.chmod(0o666)

    def _dev(self, mac: str | None = None, name: str | None = None) -> dict | None:
        """Look up device by MAC or name."""
        devs = self._state["devices"]
        if mac:
            return devs.get(self._norm(mac))
        if name:
            for d in devs.values():
                if d["name"].lower() == name.lower():
                    return d
        return None

    def resolve(
        self, mac: str | None = None, name: str | None = None, refresh: bool = False
    ) -> tuple[dict, dict] | str:
        """Resolve device + bind + get status. Returns (device, cache) or error string."""
        with self._lock:
            self._ensure()
            devs = self._state["devices"]
            if not devs:
                return "No GREE devices found. Check config and network."
            if not mac and not name:
                if len(devs) == 1:
                    device = next(iter(devs.values()))
                else:
                    return (
                        "Multiple devices found. Provide 'mac' or 'name' to select one."
                    )
            else:
                device = self._dev(mac, name)
                if not device:
                    return f"No configured device matches '{mac or name}'."
            return self._bind_dev(device, refresh)

    def _bind_dev(self, device: dict, refresh: bool) -> tuple[dict, dict] | str:
        """Bind to device if not cached, or refresh status. Returns (device, cache) or error."""
        mac_n = self._norm(device["mac"])
        cache = self._cache.get(mac_n)
        if (
            cache
            and cache.get("key")
            and not refresh
            and datetime.now(_local_tz()).timestamp() - cache.get("last_seen", 0) < 60
        ):
            return (device, cache)
        if cache and cache.get("key"):
            st = self._status(mac_n, cache)
            if st is not None:
                cache["status"] = st
                cache["last_seen"] = datetime.now(_local_tz()).timestamp()
                return (device, cache)
        cache = self._bind(device)
        if cache is None:
            return f"Device {mac_n} ({device['name']}) is not reachable."
        self._cache[mac_n] = cache
        self._sync_device_time(mac_n, cache)
        st = self._status(mac_n, cache)
        if st is not None:
            cache["status"] = st
            cache["last_seen"] = datetime.now(_local_tz()).timestamp()
        return (device, cache)

    # ---- Status encoding/decoding ----

    def decode(
        self, device: dict, cache: dict, status: dict, skip: set[str] | None = None
    ) -> dict:
        """Convert raw status dict to human-readable format."""
        skip = skip or set()
        mac_n = self._norm(device["mac"])
        info = cache.get("info") or {}
        temp, est = self._decode_temp(device, status)
        device_time = status.get(FIELDS["time"])
        if isinstance(device_time, str):
            device_time = device_time.strip()

        def b(code: str) -> bool | None:
            return status[code] == ON_OFF["on"] if code in status else None

        def n(mapping: dict, value: int | None) -> str | None:
            if value is None:
                return None
            for k, v in mapping.items():
                if v == value:
                    return k
            return None

        pairs = [
            ("mac", mac_n),
            ("name", device["name"]),
            ("room", device.get("room")),
            ("model", device.get("model") or info.get("model")),
            ("firmwareVersion", info.get("ver")),
            ("firmwareId", info.get("hid")),
            ("brand", info.get("brand")),
            ("catalog", info.get("catalog")),
            ("series", info.get("series")),
            ("vender", info.get("vender")),
            ("mid", info.get("mid")),
            ("online", bool(cache.get("key"))),
            ("bound", bool(cache.get("key"))),
            ("address", cache.get("address")),
            ("power", b(FIELDS["power"])),
            ("mode", n(MODE, status.get(FIELDS["mode"]))),
            ("targetTemperature", status.get(FIELDS["targetTemp"])),
            ("temperatureUnit", n(TEMP_UNIT, status.get(FIELDS["tempUnit"]))),
            ("tempRec", status.get(FIELDS["tempRec"])),
            ("currentTemperature", temp),
            ("currentTemperatureEstimated", est),
            ("fanSpeed", n(FAN_SPEED, status.get(FIELDS["fanSpeed"]))),
            (
                "quiet",
                (
                    status[FIELDS["quiet"]] == QUIET["on"]
                    if FIELDS["quiet"] in status
                    else None
                ),
            ),
            ("turbo", b(FIELDS["turbo"])),
            ("swingVertical", n(SWING_VERTICAL, status.get(FIELDS["swingVertical"]))),
            (
                "swingHorizontal",
                n(SWING_HORIZONTAL, status.get(FIELDS["swingHorizontal"])),
            ),
            ("xFan", b(FIELDS["xFan"])),
            ("light", b(FIELDS["light"])),
            ("health", b(FIELDS["health"])),
            ("sleep", b(FIELDS["sleep"])),
            ("sleepMode", b(FIELDS["sleepMode"])),
            ("freshAir", b(FIELDS["freshAir"])),
            ("energySaving", b(FIELDS["energySaving"])),
            ("noFrost", b(FIELDS["noFrost"])),
            ("heatCoolType", status.get(FIELDS["heatCoolType"])),
            ("deviceTime", device_time),
            (
                "lastSeen",
                (
                    datetime.fromtimestamp(
                        cache["last_seen"], tz=_local_tz()
                    ).isoformat()
                    if cache.get("last_seen")
                    else None
                ),
            ),
        ]
        return {k: v for k, v in pairs if k not in skip}

    def _decode_temp(self, device: dict, status: dict) -> tuple[float | None, bool]:
        """Decode temperature sensor value, return (celsius, estimated)."""
        raw = status.get(FIELDS["tempSensor"])
        if raw is not None and 0 < raw < 100:
            return raw - TEMSEN_OFFSET + device.get("sensorOffset", 0), False
        if device.get("fakeSensor", False):
            return (
                status.get(FIELDS["targetTemp"], 25) + device.get("sensorOffset", 0),
                True,
            )
        return None, False

    def _encode(self, decoded: dict) -> dict:
        """Convert human-readable status dict to raw wire format."""
        raw: dict[str, Any] = {}
        for dk, fk in [
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
        ]:
            if decoded.get(dk) is not None:
                raw[FIELDS[fk]] = 1 if decoded[dk] else 0
        if decoded.get("quiet") is not None:
            raw[FIELDS["quiet"]] = 2 if decoded["quiet"] else 0
        for dk, fk, m in [
            ("mode", "mode", MODE),
            ("fanSpeed", "fanSpeed", FAN_SPEED),
            ("temperatureUnit", "tempUnit", TEMP_UNIT),
            ("swingVertical", "swingVertical", SWING_VERTICAL),
            ("swingHorizontal", "swingHorizontal", SWING_HORIZONTAL),
        ]:
            if decoded.get(dk) is not None:
                raw[FIELDS[fk]] = m.get(decoded[dk], 0)
        if decoded.get("currentTemperature") is not None:
            raw[FIELDS["tempSensor"]] = (
                int(decoded["currentTemperature"]) + TEMSEN_OFFSET
            )
        for dk, fk in [
            ("targetTemperature", "targetTemp"),
            ("tempRec", "tempRec"),
            ("heatCoolType", "heatCoolType"),
        ]:
            if decoded.get(dk) is not None:
                raw[FIELDS[fk]] = decoded[dk]
        return raw

    def _persist(self, _device: dict | None = None, _cache: dict | None = None) -> None:
        """Write per-device config JSON files."""
        with self._lock:
            devs = self._state.get("devices", {})
            for d in devs.values():
                entry = {
                    k: v for k, v in d.items() if v is not None and k != "lastStatus"
                }
                mn = self._norm(d["mac"])
                c = self._cache.get(mn, {})
                st = c.get("status", {})
                if st:
                    decoded = self.decode(d, c, st)
                    decoded.pop("lastSeen", None)
                    entry["lastStatus"] = decoded
                if "last_seen" in c:
                    entry["lastSeen"] = (
                        datetime.fromtimestamp(
                            c["last_seen"], tz=_local_tz()
                        ).isoformat()
                        if c["last_seen"]
                        else None
                    )
                if entry:
                    config_path = _device_dir(mn) / "config.json"
                    config_path.write_text(dumps({"devices": [entry]}, indent=2) + "\n")
                    with suppress(PermissionError):
                        config_path.chmod(0o666)

    # ---- Public command helpers ----

    def _fan_cmd(self, speed: str, steps: int) -> dict:
        """Build fan speed command dict. Handles quiet/turbo special modes."""
        if speed == "quiet":
            return {
                FIELDS["quiet"]: QUIET["on"],
                FIELDS["turbo"]: ON_OFF["off"],
                FIELDS["fanSpeed"]: FAN_SPEED["auto"],
            }
        if speed == "turbo":
            return {FIELDS["turbo"]: ON_OFF["on"], FIELDS["quiet"]: QUIET["off"]}
        m = {
            "auto": FAN_SPEED["auto"],
            "low": FAN_SPEED["low"],
            "mediumLow": FAN_SPEED["low"] if steps == 3 else FAN_SPEED["mediumLow"],
            "medium": FAN_SPEED["medium"],
            "mediumHigh": FAN_SPEED["high"] if steps == 3 else FAN_SPEED["mediumHigh"],
            "high": FAN_SPEED["high"],
        }
        return {
            FIELDS["fanSpeed"]: m[speed],
            FIELDS["quiet"]: QUIET["off"],
            FIELDS["turbo"]: ON_OFF["off"],
        }

    def status(
        self, mac: str | None = None, name: str | None = None, refresh: bool = True
    ) -> dict[str, Any]:
        """Get decoded status including schedules. Returns error dict on failure."""
        try:
            device, cache = self._resolve_one(mac, name, refresh=refresh)
        except ValueError as e:
            return {"error": str(e)}
        result = self.decode(device, cache, cache.get("status", {}))
        mn = self._norm(device["mac"])
        timers = self._query_timers(mn, cache)
        result["schedules"] = timers if timers is not None else []
        return result

    def room_temp(
        self, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Get current room temperature from AC sensor. Returns {temperature, estimated, unit}."""
        try:
            device, cache = self._resolve_one(mac, name, refresh=True)
        except ValueError as e:
            return {"error": str(e)}
        celsius, estimated = self._decode_temp(device, cache.get("status", {}))
        mn = self._norm(device["mac"])
        if celsius is None:
            return {
                "mac": mn,
                "name": device["name"],
                "temperature": None,
                "estimated": False,
                "note": "No usable sensor and fakeSensor is disabled.",
            }
        return {
            "mac": mn,
            "name": device["name"],
            "temperature": round(celsius * 10) / 10,
            "unit": "C",
            "estimated": estimated,
        }

    def set_power(
        self, on: bool, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Power AC on or off. Returns decoded status."""
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        return self._cmd_verify(
            device, cache, {FIELDS["power"]: ON_OFF["on"] if on else ON_OFF["off"]}
        )

    def set_mode(
        self, mode: str, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Set AC operating mode. Also powers unit on. Returns decoded status."""
        if mode not in MODE:
            return {"error": f"Invalid mode '{mode}'. Valid: {list(MODE)}"}
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        return self._cmd_verify(
            device, cache, {FIELDS["mode"]: MODE[mode], FIELDS["power"]: ON_OFF["on"]}
        )

    def set_temp(
        self, temperature: float, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Set target temperature. Validates range, rounds to int. Returns decoded status."""
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        mn = self._norm(device["mac"])
        min_t = device.get("minimumTargetTemperature", 16)
        max_t = device.get("maximumTargetTemperature", 30)
        if temperature < min_t or temperature > max_t:
            return {
                "error": f"Temperature {temperature}C is out of range for {mn} (allowed {min_t}-{max_t}C)."
            }
        return self._cmd_verify(
            device,
            cache,
            {
                FIELDS["targetTemp"]: round(temperature),
                FIELDS["tempUnit"]: TEMP_UNIT["celsius"],
            },
        )

    def set_fan(
        self, speed: str, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Set fan speed. Validates speed, handles quiet/turbo. Returns decoded status."""
        speed = {"medium-low": "mediumLow", "medium-high": "mediumHigh"}.get(
            speed, speed
        )
        if speed not in VALID_FAN_SPEEDS:
            return {"error": f"Invalid speed '{speed}'. Valid: {VALID_FAN_SPEEDS}"}
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        return self._cmd_verify(
            device, cache, self._fan_cmd(speed, device.get("speedSteps", 5))
        )

    def set_swing(
        self, on: bool, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Enable/disable louver swing. Uses device oscillation config. Returns decoded status."""
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
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
        return self._cmd_verify(device, cache, cmd)

    def set_xfan(
        self, on: bool, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Toggle X-Fan (coil drying). Checks device capability. Returns decoded status."""
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        mn = self._norm(device["mac"])
        if not device.get("xFan", False):
            return {
                "error": f'X-Fan is not enabled for {mn} ({device["name"]}); set "xFan": true in config.'
            }
        return self._cmd_verify(
            device, cache, {FIELDS["xFan"]: ON_OFF["on"] if on else ON_OFF["off"]}
        )

    def set_light(
        self, on: bool, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Toggle front-panel display LED. Checks device capability. Returns decoded status."""
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        mn = self._norm(device["mac"])
        if not device.get("lightControl", False):
            return {
                "error": f'Light control is not enabled for {mn} ({device["name"]}); set "lightControl": true in config.'
            }
        return self._cmd_verify(
            device, cache, {FIELDS["light"]: ON_OFF["on"] if on else ON_OFF["off"]}
        )

    def set_quiet(
        self, on: bool, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Toggle quiet mode. Disables turbo when enabled. Returns decoded status."""
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        cmd: dict[str, int] = {FIELDS["quiet"]: QUIET["on"] if on else QUIET["off"]}
        if on:
            cmd[FIELDS["turbo"]] = ON_OFF["off"]
        return self._cmd_verify(device, cache, cmd)

    def set_turbo(
        self, on: bool, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Toggle turbo mode. Disables quiet when enabled. Returns decoded status."""
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        cmd: dict[str, int] = {FIELDS["turbo"]: ON_OFF["on"] if on else ON_OFF["off"]}
        if on:
            cmd[FIELDS["quiet"]] = QUIET["off"]
        return self._cmd_verify(device, cache, cmd)

    def get_time(
        self, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Fetch AC unit's internal clock. Returns deviceTime string."""
        try:
            device, cache = self._resolve_one(mac, name, refresh=True)
        except ValueError as e:
            return {"error": str(e)}
        mn = self._norm(device["mac"])
        st = self._status(mn, cache, ["time"])
        if st is None:
            return {"error": "Could not fetch time from device.", "mac": mn}
        return {"mac": mn, "name": device["name"], "deviceTime": st.get("time")}

    def set_time(
        self,
        time_str: str | None = None,
        mac: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Set AC clock. Defaults to current local time if time_str omitted."""
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        mn = self._norm(device["mac"])
        if time_str is None:
            time_str = datetime.now(_local_tz()).strftime("%Y-%m-%d %H:%M:%S")
        resp = self._cmd(mn, cache, ["time"], [time_str], sub=mn)
        _record_event(mn, "set_time", time=time_str)
        return {
            "mac": mn,
            "name": device["name"],
            "setTime": time_str,
            "response": resp,
        }

    def list_schedules(
        self, mac: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """List all scheduled timer events on the AC unit."""
        try:
            device, cache = self._resolve_one(mac, name, refresh=True)
        except ValueError as e:
            return {"error": str(e)}
        mn = self._norm(device["mac"])
        timers = self._query_timers(mn, cache)
        return {
            "mac": mn,
            "name": device["name"],
            "schedules": timers if timers is not None else [],
        }

    def set_schedule(
        self,
        hour: int,
        minute: int,
        power_on: bool,
        weekdays: list[int] | None = None,
        schedule_id: int | None = None,
        mac: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a scheduled timer event on the AC unit."""
        if hour < 0 or hour > 23:
            return {"error": "Hour must be 0-23"}
        if minute < 0 or minute > 59:
            return {"error": "Minute must be 0-59"}
        if schedule_id is not None and (schedule_id < 0 or schedule_id > 15):
            return {"error": "schedule_id must be 0-15"}
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        mn = self._norm(device["mac"])
        schedule = {
            "cmd": [{"mac": [mn], "opt": ["Pow"], "p": [1 if power_on else 0]}],
            "enable": 1,
            "hr": hour,
            "id": schedule_id or 0,
            "min": minute,
            "name": "5363686564756c65",
            "sec": 0,
            "t": "setT",
            "tz": 1,
            "week": weekdays or [0, 1, 1, 1, 1, 1, 0],
        }
        schedule["_ver"] = cache["version"]
        schedule["_key"] = cache["key"]
        resp = self._send(cache["address"], schedule)
        _record_event(mn, "set_schedule", hour=hour, minute=minute, power_on=power_on)
        # Maintain local schedule cache for devices that don't support queryT
        if resp is not None and resp.get("r") == 200:
            sid = schedule_id or 0
            entry = {
                "id": sid,
                "hour": hour,
                "minute": minute,
                "power_on": power_on,
                "weekdays": weekdays or [0, 1, 1, 1, 1, 1, 0],
                "enable": 1,
            }
            with self._lock:
                scheds = self._schedules.setdefault(mn, [])
                scheds = [s for s in scheds if s.get("id") != sid]
                scheds.append(entry)
                self._schedules[mn] = scheds
                self._save_schedules(mn)
        return {
            "mac": mn,
            "name": device["name"],
            "schedule": {k: v for k, v in schedule.items() if not k.startswith("_")},
            "response": resp,
        }

    def delete_schedule(
        self,
        schedule_id: int,
        mac: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Delete a scheduled timer event by its ID."""
        if schedule_id < 0 or schedule_id > 15:
            return {"error": "schedule_id must be 0-15"}
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        mn = self._norm(device["mac"])
        schedule = {
            "cmd": [{"mac": [mn], "opt": ["Pow"], "p": [0]}],
            "enable": 0,
            "hr": 0,
            "id": schedule_id,
            "min": 0,
            "name": "5363686564756c65",
            "sec": 0,
            "t": "setT",
            "tz": 1,
            "week": [0, 0, 0, 0, 0, 0, 0],
        }
        schedule["_ver"] = cache["version"]
        schedule["_key"] = cache["key"]
        resp = self._send(cache["address"], schedule)
        _record_event(mn, "delete_schedule", schedule_id=schedule_id)
        # Remove from local schedule cache
        if resp is not None and resp.get("r") == 200:
            with self._lock:
                self._schedules[mn] = [
                    s for s in self._schedules.get(mn, []) if s.get("id") != schedule_id
                ]
                self._save_schedules(mn)
        return {
            "mac": mn,
            "name": device["name"],
            "deletedScheduleId": schedule_id,
            "response": resp,
        }

    def set_multiple(self, **kwargs: Any) -> dict[str, Any]:
        """Set multiple AC parameters at once. kwargs match set_home_ac tool params."""
        mac = kwargs.pop("mac", None)
        name = kwargs.pop("name", None)
        schedule: ScheduleConfig | None = kwargs.pop("schedule", None)
        delete_schedule_id: int | None = kwargs.pop("delete_schedule_id", None)
        try:
            device, cache = self._resolve_one(mac, name)
        except ValueError as e:
            return {"error": str(e)}
        cmd: dict[str, int] = {}
        errors: list[str] = []

        if (power := kwargs.get("power")) is not None:
            cmd[FIELDS["power"]] = ON_OFF["on"] if power else ON_OFF["off"]
        if (mode := kwargs.get("mode")) is not None:
            if mode not in MODE:
                errors.append(f"Invalid mode '{mode}'. Valid: {list(MODE)}")
            else:
                cmd[FIELDS["mode"]] = MODE[mode]
                cmd[FIELDS["power"]] = ON_OFF["on"]
        if (temperature := kwargs.get("temperature")) is not None:
            min_t = device.get("minimumTargetTemperature", 16)
            max_t = device.get("maximumTargetTemperature", 30)
            if temperature < min_t or temperature > max_t:
                errors.append(
                    f"Temperature {temperature} out of range ({min_t}-{max_t})."
                )
            else:
                cmd[FIELDS["targetTemp"]] = round(temperature)
                cmd[FIELDS["tempUnit"]] = TEMP_UNIT["celsius"]
        if (fan_speed := kwargs.get("fan_speed")) is not None:
            if fan_speed not in VALID_FAN_SPEEDS:
                errors.append(
                    f"Invalid fan_speed '{fan_speed}'. Valid: {VALID_FAN_SPEEDS}"
                )
            else:
                cmd.update(self._fan_cmd(fan_speed, device.get("speedSteps", 5)))
        if (oscillation := kwargs.get("oscillation")) is not None:
            osc = device.get("oscillation", {})
            positions = osc.get("on" if oscillation else "off", {})
            vert = positions.get("vertical", "full" if oscillation else "default")
            horiz = positions.get("horizontal", "full" if oscillation else "default")
            if vert in SWING_VERTICAL:
                cmd[FIELDS["swingVertical"]] = SWING_VERTICAL[vert]
            if horiz in SWING_HORIZONTAL:
                cmd[FIELDS["swingHorizontal"]] = SWING_HORIZONTAL[horiz]
        if (swing_vertical := kwargs.get("swing_vertical")) is not None:
            if swing_vertical in SWING_VERTICAL:
                cmd[FIELDS["swingVertical"]] = SWING_VERTICAL[swing_vertical]
            else:
                errors.append(
                    f"Invalid swing_vertical '{swing_vertical}'. Valid: {list(SWING_VERTICAL)}"
                )
        if (swing_horizontal := kwargs.get("swing_horizontal")) is not None:
            if swing_horizontal in SWING_HORIZONTAL:
                cmd[FIELDS["swingHorizontal"]] = SWING_HORIZONTAL[swing_horizontal]
            else:
                errors.append(
                    f"Invalid swing_horizontal '{swing_horizontal}'. Valid: {list(SWING_HORIZONTAL)}"
                )
        if (xfan := kwargs.get("xfan")) is not None:
            if not device.get("xFan", False):
                errors.append("X-Fan not enabled for this device.")
            else:
                cmd[FIELDS["xFan"]] = ON_OFF["on"] if xfan else ON_OFF["off"]
        if (light := kwargs.get("light")) is not None:
            if not device.get("lightControl", False):
                errors.append("Light control not enabled for this device.")
            else:
                cmd[FIELDS["light"]] = ON_OFF["on"] if light else ON_OFF["off"]
        if (quiet := kwargs.get("quiet")) is not None:
            cmd[FIELDS["quiet"]] = QUIET["on"] if quiet else QUIET["off"]
            if quiet:
                cmd[FIELDS["turbo"]] = ON_OFF["off"]
        if (turbo := kwargs.get("turbo")) is not None:
            cmd[FIELDS["turbo"]] = ON_OFF["on"] if turbo else ON_OFF["off"]
            if turbo:
                cmd[FIELDS["quiet"]] = QUIET["off"]
        if (fresh_air := kwargs.get("fresh_air")) is not None:
            cmd[FIELDS["freshAir"]] = ON_OFF["on"] if fresh_air else ON_OFF["off"]
        if (health := kwargs.get("health")) is not None:
            cmd[FIELDS["health"]] = ON_OFF["on"] if health else ON_OFF["off"]
        if (sleep := kwargs.get("sleep")) is not None:
            cmd[FIELDS["sleep"]] = ON_OFF["on"] if sleep else ON_OFF["off"]
        if (sleep_mode := kwargs.get("sleep_mode")) is not None:
            cmd[FIELDS["sleepMode"]] = ON_OFF["on"] if sleep_mode else ON_OFF["off"]
        if (no_frost := kwargs.get("no_frost")) is not None:
            cmd[FIELDS["noFrost"]] = ON_OFF["on"] if no_frost else ON_OFF["off"]
        if (energy_saving := kwargs.get("energy_saving")) is not None:
            cmd[FIELDS["energySaving"]] = (
                ON_OFF["on"] if energy_saving else ON_OFF["off"]
            )
        if (heat_cool_type := kwargs.get("heat_cool_type")) is not None:
            cmd[FIELDS["heatCoolType"]] = heat_cool_type
        if errors:
            return {"error": "; ".join(errors)}

        # Validate schedule params before executing any schedule ops
        if delete_schedule_id is not None:
            if delete_schedule_id < 0 or delete_schedule_id > 15:
                errors.append("delete_schedule_id must be 0-15")
        if schedule is not None:
            if schedule.hour < 0 or schedule.hour > 23:
                errors.append("schedule.hour must be 0-23")
            if schedule.minute < 0 or schedule.minute > 59:
                errors.append("schedule.minute must be 0-59")
            if schedule.schedule_id is not None and (
                schedule.schedule_id < 0 or schedule.schedule_id > 15
            ):
                errors.append("schedule.schedule_id must be 0-15")
        if errors:
            return {"error": "; ".join(errors)}

        result: dict[str, Any] = {}
        warnings: list[str] = []

        # Handle schedule deletion
        if delete_schedule_id is not None:
            del_result = self.delete_schedule(delete_schedule_id, mac, name)
            if "error" in del_result:
                warnings.append(del_result["error"])
            else:
                result["deletedSchedule"] = del_result

        # Handle schedule creation/update
        if schedule is not None:
            sched_result = self.set_schedule(
                schedule.hour,
                schedule.minute,
                schedule.power_on,
                schedule.weekdays,
                schedule.schedule_id,
                mac,
                name,
            )
            if "error" in sched_result:
                warnings.append(sched_result["error"])
            else:
                result["schedule"] = sched_result

        if not cmd and not result:
            if warnings:
                return {"error": "; ".join(warnings)}
            return {"error": "No settings provided. Specify at least one parameter."}
        _record_event(
            self._norm(device["mac"]),
            "set_multiple",
            params={k: v for k, v in kwargs.items() if v is not None},
            schedule=schedule.model_dump() if schedule else None,
            delete_schedule_id=delete_schedule_id,
        )
        if cmd:
            status_result = self._cmd_verify(device, cache, cmd)
            result.update(status_result)
        else:
            # Only schedule ops — return current status too
            with self._lock:
                mn = self._norm(device["mac"])
                st = self._status(mn, cache)
                if st is not None:
                    cache["status"] = st
                    cache["last_seen"] = datetime.now(_local_tz()).timestamp()
                self._persist(device, cache)
                result.update(self.decode(device, cache, cache.get("status", {})))
            result["schedules"] = self._query_timers(mn, cache) or []
        if warnings:
            result["warnings"] = warnings
        return result

    def _cmd_verify(self, device: dict, cache: dict, cmd: dict) -> dict[str, Any]:
        """Send command, try best-effort status re-fetch, return decoded status."""
        with self._lock:
            mac = self._norm(device["mac"])
            old_status = dict(cache.get("status", {}))
            self._cmd(mac, cache, list(cmd.keys()), list(cmd.values()))
            changes = {}
            for code, raw_val in cmd.items():
                if old_status.get(code) == raw_val:
                    continue
                name = _FIELDS_REV.get(code, code)
                decoded = raw_val
                if name == "mode":
                    decoded = _MODE_REV.get(raw_val, raw_val)
                elif name == "fanSpeed":
                    decoded = _FAN_REV.get(raw_val, raw_val)
                changes[name] = decoded
            if changes:
                _record_event(mac, "cmd", changes=changes)
            st = self._status(mac, cache)
            if st is not None:
                cache["status"] = st
                cache["last_seen"] = datetime.now(_local_tz()).timestamp()
            self._persist(device, cache)
            return self.decode(device, cache, cache.get("status", {}))

    def _sync_device_time(
        self, mac: str, cache: dict, status: dict | None = None
    ) -> None:
        """
        Sync AC clock to local time if off by >60s.

        If *status* is provided it must be a RAW status dict (as returned by
        ``_status``, keyed by ``FIELDS["time"]``), not a ``decode``d one — pass it
        to reuse an already-fetched status instead of a separate UDP round-trip.
        """
        if status is None:
            status = self._status(mac, cache, ["time"])
            if status is None:
                return
        dt_raw = status.get(FIELDS["time"])
        if not isinstance(dt_raw, str) or not dt_raw.strip():
            return
        try:
            dt = datetime.strptime(dt_raw.strip(), "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=_local_tz()
            )
        except (ValueError, TypeError):
            return
        local = datetime.now(_local_tz())
        if abs((local - dt).total_seconds()) > 60:
            self._cmd(
                mac, cache, ["time"], [local.strftime("%Y-%m-%d %H:%M:%S")], sub=mac
            )


_client = GREEACClient()


# ============================================================
# TELEMETRY & GRAPHING
# ============================================================

_telemetry_lock = Lock()
_collector_thread: Thread | None = None
_stop_event = Event()


def _record_event(mac: str, action: str, **details: Any) -> None:
    """Append a user action event to the per-device telemetry stream."""
    tdir = _device_dir(mac) / "telemetry"
    path = tdir / f"{datetime.now(_local_tz()).strftime('%Y-%m-%d')}.jsonl"
    event = {
        "deviceTime": datetime.now(_local_tz()).strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        **details,
    }
    with _telemetry_lock, path.open("a", encoding="utf-8") as f:
        f.write(dumps(event, default=str) + "\n")
    with suppress(PermissionError):
        path.chmod(0o666)


def _telemetry_fetch(mac: str | None = None) -> dict | None:
    """Fetch current AC status for telemetry logging. Returns decoded status or error dict."""
    r = _client.resolve(mac=mac, refresh=True)
    if isinstance(r, str):
        return {"error": r}
    device, cache = r[0], r[1]
    decoded = _client.decode(
        device,
        cache,
        cache.get("status", {}),
        skip={
            "name",
            "lastSeen",
            "room",
            "model",
            "firmwareVersion",
            "firmwareId",
            "brand",
            "catalog",
            "series",
            "vender",
            "mid",
            "temperatureUnit",
            "address",
            "tempRec",
            "heatCoolType",
            "online",
            "bound",
        },
    )
    decoded["mac"] = _client._norm(device["mac"])  # noqa: SLF001
    return decoded


def _save_reading(reading: dict) -> None:
    """Append a telemetry reading to today's per-device JSONL file."""
    mac = reading.get("mac", "unknown")
    tdir = _device_dir(mac) / "telemetry"
    path = tdir / f"{datetime.now(_local_tz()).strftime('%Y-%m-%d')}.jsonl"
    with _telemetry_lock, path.open("a", encoding="utf-8") as f:
        f.write(dumps(reading, default=str) + "\n")
    with suppress(PermissionError):
        path.chmod(0o666)


def _collect() -> None:
    """Background loop: fetch status every 1 min until stopped."""
    while not _stop_event.is_set():
        try:
            with _client._lock:  # noqa: SLF001
                _client._ensure()  # noqa: SLF001
                macs = list(_client._state["devices"].keys())  # noqa: SLF001
            for mac in macs:
                r = _telemetry_fetch(mac)
                if r and "error" not in r:
                    _save_reading(r)
            _client._persist(None, None)  # noqa: SLF001
        except Exception as e:
            err_path = _DATA_DIR / "errors.jsonl"
            with _telemetry_lock, err_path.open("a", encoding="utf-8") as f:
                f.write(
                    dumps(
                        {
                            "_error": str(e),
                            "deviceTime": datetime.now(_local_tz()).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        },
                        default=str,
                    )
                    + "\n"
                )
        _stop_event.wait(60)


def _query_readings(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100000,
    mac: str | None = None,
) -> list[dict]:
    """Query telemetry readings by date range. Returns sorted list oldest-first (chronological)."""
    results = []
    if mac:
        files = sorted(
            (_device_dir(mac) / "telemetry").glob("*.jsonl"),
            key=lambda p: p.name,
            reverse=True,
        )
    else:
        files = sorted(
            _DATA_DIR.glob("*/telemetry/*.jsonl"), key=lambda p: p.name, reverse=True
        )
    for fpath in files:
        if len(results) >= limit:
            break
        with fpath.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    rec = loads(line)
                except JSONDecodeError:
                    continue
                dt = rec.get("deviceTime", "")
                if start and dt < start.strftime("%Y-%m-%d %H:%M:%S"):
                    continue
                if end and dt > end.strftime("%Y-%m-%d %H:%M:%S"):
                    continue
                results.append(rec)
                if len(results) >= limit:
                    break
    results.sort(key=lambda r: r.get("deviceTime", ""))
    return results


def _dedup_unchanged(readings: list[dict]) -> list[dict]:
    """
    Collapse runs of consecutive readings identical except for the timestamp.

    Keeps the FIRST and LAST reading of each run (a single point only once) so
    flat segments stay anchored at both ends — the smoothing curve then draws a
    true horizontal line instead of bowing through a lone midpoint. Transition
    timestamps remain accurate.

    Assumes `readings` contains only sensor readings (no action/event records);
    splitting those out is the caller's responsibility.
    """
    deduped: list[dict] = []
    run_sig: tuple | None = None
    run_last: dict | None = None  # pending tail of the current run, not yet emitted

    def flush() -> None:
        nonlocal run_last
        if run_last is not None:
            deduped.append(run_last)
            run_last = None

    for r in readings:
        sig = tuple(sorted((k, v) for k, v in r.items() if k != "deviceTime"))
        if sig != run_sig:
            flush()
            deduped.append(r)
            run_sig = sig
        else:
            run_last = r  # extend run; remember tail to emit when it ends
    flush()
    return deduped


# Max points to render/return. Data is collected every 1 min, so 1w = 10080
# raw points; anything past ~1000 is invisible noise on a chart.
_GRAPH_MAX_POINTS = 1000
_SERIES_MAX_POINTS = 200


def _downsample(readings: list[dict], max_points: int) -> list[dict]:
    """
    Uniformly thin readings to at most `max_points`, keeping the last sample.

    Index-stride is exact for our regular 1/min cadence. Sparse data
    (fewer than `max_points`) is returned untouched (step=1).
    """
    if not readings or len(readings) <= max_points:
        return readings
    step = -(-len(readings) // max_points)  # ceil division
    thinned = readings[::step]
    if thinned[-1] is not readings[-1]:
        thinned.append(readings[-1])
    return thinned


def _summarize_readings(readings: list[dict]) -> dict[str, Any]:
    room_temps = [
        v
        for r in readings
        if (
            v := (
                r.get("currentTemperature")
                if r.get("currentTemperature") is not None
                else r.get("roomTemperature")
            )
        )
        is not None
    ]
    target_temps = [
        r["targetTemperature"] for r in readings if r.get("targetTemperature")
    ]
    power_vals = [r.get("power") for r in readings]
    power_on_count = sum(1 for p in power_vals if p in (True, "on", "true", "1", 1))
    transitions = sum(
        1 for i in range(1, len(power_vals)) if power_vals[i] != power_vals[i - 1]
    )
    # Stats above use the raw uniform samples (time-correct averages/percentages);
    # the charted series is deduped + downsampled so flat runs draw clean.
    series = []
    for r in _downsample(_dedup_unchanged(readings), _SERIES_MAX_POINTS):
        rv = (
            r.get("currentTemperature")
            if r.get("currentTemperature") is not None
            else r.get("roomTemperature")
        )
        series.append(
            {
                "time": r.get("deviceTime"),
                "room": rv,
                "target": r.get("targetTemperature"),
                "power": r.get("power"),
            }
        )
    return {
        "data_points": len(readings),
        "room_temperature": room_temps[-1] if room_temps else None,
        "room_temp_min": min(room_temps) if room_temps else None,
        "room_temp_max": max(room_temps) if room_temps else None,
        "room_temp_avg": (
            round(sum(room_temps) / len(room_temps), 1) if room_temps else None
        ),
        "target_temperature": target_temps[-1] if target_temps else None,
        "power_on_pct": (
            round(power_on_count / len(power_vals) * 100, 1) if power_vals else None
        ),
        "power_transitions": transitions,
        "series": series,
    }


def _generate_graph(
    readings: list[dict],
    title: str = "Temperature Evolution",
    start: datetime | None = None,
    end: datetime | None = None,
    events: list[dict] | None = None,
    mac: str = "unknown",
) -> str:
    """Generate a temperature evolution PNG with power-state overlays. Returns file path."""
    plt.rcParams.update(
        {
            "figure.facecolor": "#000000",
            "figure.edgecolor": "#000000",
            "axes.facecolor": "#000000",
            "savefig.facecolor": "#000000",
            "savefig.edgecolor": "#000000",
            "text.color": "#eaeaea",
            "axes.labelcolor": "#eaeaea",
            "axes.titlecolor": "#eaeaea",
            "xtick.color": "#666666",
            "ytick.color": "#666666",
            "grid.color": "#222222",
        }
    )

    sampled = _downsample(_dedup_unchanged(readings), _GRAPH_MAX_POINTS)
    ts, rt, at, ps = [], [], [], []
    for r in sampled:
        dt_s = r.get("deviceTime")
        if not dt_s:
            continue
        try:
            ts.append(datetime.strptime(dt_s, "%Y-%m-%d %H:%M:%S"))  # noqa: DTZ007
        except (ValueError, TypeError):
            continue
        rv = r.get("currentTemperature")
        if rv is None:
            rv = r.get("roomTemperature")
        rt.append(float(rv) if rv is not None else None)
        av = r.get("targetTemperature")
        at.append(float(av) if av is not None else None)
        pv = r.get("power")
        ps.append(pv in (True, "on", "true", "1") if not isinstance(pv, bool) else pv)

    if not ts:
        raise ValueError("No valid readings to graph.")

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("#000000")
    ax.set_facecolor("#000000")

    if ps:
        _on_start: datetime | None = None
        for i, p in enumerate(ps):
            if p and _on_start is None:
                _on_start = ts[i]
            elif not p and _on_start is not None:
                ax.axvspan(_on_start, ts[i], color="#1a237e", alpha=0.07, zorder=0)
                _on_start = None
        if _on_start is not None:
            ax.axvspan(_on_start, ts[-1], color="#1a237e", alpha=0.07, zorder=0)

    rt_n, short_w, long_w = 0, 0, 0
    valid_rt = [(t, v) for t, v in zip(ts, rt) if v is not None]
    if valid_rt:
        rt_ts, rt_vals = zip(*valid_rt)
        rt_n = len(rt_vals)
        short_w = max(3, min(15, rt_n // 20))
        long_w = max(10, min(50, rt_n // 7))
        ax.plot(
            date2num(rt_ts),
            rt_vals,
            color="#00bcd4",
            linewidth=2,
            alpha=0.9,
            label="Room Temperature",
        )

        def _sma(vals: list[float], w: int) -> list[float]:
            if len(vals) < w:
                return list(vals)
            return [sum(vals[i : i + w]) / w for i in range(len(vals) - w + 1)]

        if rt_n > short_w:
            short_ma = _sma(list(rt_vals), short_w)
            ax.plot(
                date2num(rt_ts[short_w - 1 :]),
                short_ma,
                color="#80deea",
                linewidth=1.5,
                alpha=0.7,
                linestyle="--",
                label=f"Room MA-{short_w}",
            )
        if rt_n > long_w > short_w:
            long_ma = _sma(list(rt_vals), long_w)
            ax.plot(
                date2num(rt_ts[long_w - 1 :]),
                long_ma,
                color="#ffeb3b",
                linewidth=1.5,
                alpha=0.6,
                linestyle=":",
                label=f"Room MA-{long_w}",
            )

    valid_at = [(t, v, p, r) for t, v, p, r in zip(ts, at, ps, rt) if v is not None]
    at_vals: tuple = ()
    if valid_at:
        at_ts, at_vals, at_ps, at_rt = zip(*valid_at)
        segs, cols = [], []
        for i in range(len(at_ts) - 1):
            x1, y1 = date2num(at_ts[i]), at_vals[i]
            x2, y2 = date2num(at_ts[i + 1]), at_vals[i + 1]
            segs.append([(x1, y1), (x2, y2)])
            p, r, a = at_ps[i], at_rt[i], at_vals[i]
            if not p:
                cols.append("#ff1744")  # AC off
            elif r is not None and a is not None and abs(r - a) < 1:
                cols.append("#00e676")  # on target
            else:
                cols.append("#ff9100")  # actively changing
        lc = LineCollection(segs, colors=cols, linewidth=2, alpha=0.9)
        ax.add_collection(lc)

    if events and ts:
        ev_x, ev_y = [], []
        _rt_idx = sorted(range(len(ts)), key=lambda i: ts[i])
        _rt_ts = [ts[i] for i in _rt_idx]
        for ev in events:
            ev_ts = ev.get("deviceTime")
            if not ev_ts:
                continue
            try:
                ev_dt = datetime.strptime(ev_ts, "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
            except (ValueError, TypeError):
                continue
            s, e = start, end
            if s and s.tzinfo:
                s = s.replace(tzinfo=None)
            if e and e.tzinfo:
                e = e.replace(tzinfo=None)
            if (s is None or s <= ev_dt) and (e is None or ev_dt <= e):
                j = bisect_left(_rt_ts, ev_dt)
                j = min(j, len(_rt_ts) - 1)
                if j and abs((_rt_ts[j] - ev_dt).total_seconds()) > abs(
                    (_rt_ts[j - 1] - ev_dt).total_seconds()
                ):
                    j -= 1
                y = at[_rt_idx[j]]
                if y is not None:
                    ev_x.append(ev_dt)
                    ev_y.append(y)
        if ev_x:
            ax.scatter(
                date2num(ev_x), ev_y, color="#ffffff", s=12, zorder=6, marker="o"
            )

    ax.set_xlabel("Time", fontsize=11)
    ax.set_ylabel("Temperature (°C)", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    _handles = [
        Line2D([0], [0], color="#00bcd4", linewidth=2, label="Room Temperature")
    ]
    if valid_rt and short_w and rt_n > short_w:
        _handles.append(
            Line2D(
                [0],
                [0],
                color="#80deea",
                linewidth=1.5,
                linestyle="--",
                alpha=0.7,
                label=f"Room MA-{short_w}",
            )
        )
    if valid_rt and long_w and long_w > short_w and rt_n > long_w:
        _handles.append(
            Line2D(
                [0],
                [0],
                color="#ffeb3b",
                linewidth=1.5,
                linestyle=":",
                alpha=0.6,
                label=f"Room MA-{long_w}",
            )
        )
    if valid_at:
        _handles.extend(
            [
                Line2D(
                    [0], [0], color="#00e676", linewidth=2, label="Target (on target)"
                ),
                Line2D(
                    [0],
                    [0],
                    color="#ff9100",
                    linewidth=2,
                    label="Target (heating/cooling)",
                ),
                Line2D([0], [0], color="#ff1744", linewidth=2, label="Target (AC off)"),
            ]
        )
    ax.legend(handles=_handles, loc="lower left", fontsize=9, framealpha=0.8, ncol=2)
    ax.grid(True, linestyle="--", alpha=0.15)  # noqa: FBT003

    pad = (ts[-1] - ts[0]) * 0.02 if len(ts) > 1 else timedelta(hours=1)
    ax.set_xlim(ts[0] - pad, ts[-1] + pad)

    _y_vals = [v for v in rt if v is not None] + [v for v in at if v is not None]
    if _y_vals:
        y_min, y_max = min(_y_vals), max(_y_vals)
        y_pad = max(0.5, (y_max - y_min) * 0.1)
        ax.set_ylim(y_min - y_pad, y_max + y_pad)

    span = ts[-1] - ts[0]
    if span <= timedelta(days=2):
        ax.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    elif span <= timedelta(days=14):
        ax.xaxis.set_major_formatter(DateFormatter("%b %d\n%H:%M"))
    else:
        ax.xaxis.set_major_formatter(DateFormatter("%b %d"))
        ax.xaxis.set_major_locator(DayLocator())
    fig.autofmt_xdate()

    if valid_rt:
        rv = [v for _, v in valid_rt]
        current_room = f"Room: {rv[-1]:.1f}°C" if rv else ""
        current_target = f"Target: {at_vals[-1]:.0f}°C" if valid_at else ""
        range_info = f"Range: {min(rv):.1f}-{max(rv):.1f}°C" if rv else ""
        avg_info = f"Avg: {sum(rv) / len(rv):.1f}°C" if rv else ""
        info = "  |  ".join(
            s for s in [current_room, current_target, range_info, avg_info] if s
        )
        ax.text(
            0.02,
            0.98,
            info,
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=10,
            color="#eaeaea",
            bbox={
                "boxstyle": "round,pad=0.3",
                "facecolor": "#111111",
                "edgecolor": "#333333",
            },
        )

    plt.tight_layout()
    gdir = _device_dir(mac) / "graphs"
    out = str(
        gdir / f"ac_graph_{datetime.now(_local_tz()).strftime('%Y%m%d_%H%M%S')}.png"
    )
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    with suppress(PermissionError):
        Path(out).chmod(0o666)
    return out


# ============================================================
# AUTO-START
# ============================================================

_stop_event.clear()

# Sync AC clock(s) to local server time on startup.
with suppress(Exception):
    _client._ensure()  # noqa: SLF001
    for mac, d in _client._state["devices"].items():  # noqa: SLF001
        r = _client._bind_dev(d, refresh=True)  # noqa: SLF001
        if not isinstance(r, str):
            _client._sync_device_time(mac, r[1])  # noqa: SLF001
    _client._persist(None, None)  # noqa: SLF001

_collector_thread = Thread(target=_collect, daemon=True)
_collector_thread.start()


def _stop_collector() -> None:
    _stop_event.set()
    if _collector_thread:
        _collector_thread.join(timeout=5)


register(_stop_collector)
with suppress(ValueError, OSError):  # ponytail: only works in main thread
    signal(SIGTERM, lambda *_: _stop_collector())

# ============================================================
# MCP TOOLS — only convenience tools are exposed to the agent.
# All individual setters are subsumed by set_home_ac.
# ============================================================

_mac_desc = "Device MAC address (12 hex digits). Omit if only one device."
_name_desc = "Device name. Omit if only one device."


def _list_devices() -> dict[str, Any]:
    """List all GREE AC units with live status."""
    with _client._lock:  # noqa: SLF001
        _client._ensure()  # noqa: SLF001
        devices = []
        for mac, d in _client._state["devices"].items():  # noqa: SLF001
            r = _client._bind_dev(d, refresh=True)  # noqa: SLF001
            if isinstance(r, str):
                devices.append({"mac": mac, "name": d["name"], "error": r})
            else:
                devices.append(_client.decode(d, r[1], r[1].get("status", {})))
        _client._persist(None, None)  # noqa: SLF001
    return {"devices": devices}


def _generate_temp_graph(  # noqa: PLR0911
    range: str | None = None,  # noqa: A002
    mac: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Generate a temperature evolution graph (PNG) + structured data summary."""
    now = datetime.now(_local_tz())
    period = (range or "1w").lower()

    m = match(r"^(\d+)([hdw])$", period)
    if m:
        val, unit = int(m[1]), m[2]
        unit_map = {"h": 1, "d": 24, "w": 168}
        hours = val * unit_map[unit]
        if hours < 1 or hours > 336:
            return {"error": "Range must be between 1h and 2w (336h)."}
        start, end = now - timedelta(hours=hours), now
        title = f"Temperature - Last {val}{unit}"
    elif "to" in period:
        parts = period.split("to")
        try:
            s, e = (x.strip() for x in (parts[0], parts[1] if len(parts) > 1 else ""))
            start = (
                datetime.fromisoformat(s)
                if "T" in s
                else datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=_local_tz())
            )
            end = (
                datetime.fromisoformat(e)
                if "T" in e
                else (
                    datetime.strptime(e, "%Y-%m-%d").replace(tzinfo=_local_tz())
                    if e
                    else now
                )
            )
            title = f"Temperature - {s} to {e or 'now'}"
        except (ValueError, IndexError):
            return {
                "error": f"Invalid date range '{period}'. Use format 'YYYY-MM-DD to YYYY-MM-DD'."
            }
    else:
        return {
            "error": f"Unknown range '{period}'. Use e.g. '6h', '3d', '2w', or 'YYYY-MM-DD to YYYY-MM-DD'."
        }

    try:
        dev, _ = _client._resolve_one(mac, name)  # noqa: SLF001
    except ValueError as e:
        return {"error": str(e)}
    dev_mac = _client._norm(dev["mac"])  # noqa: SLF001

    readings = _query_readings(start, end, mac=dev_mac)
    if not readings:
        return {"error": f"No readings found for period: {period}"}
    events_list = [r for r in readings if "action" in r]
    readings = [r for r in readings if "action" not in r]
    if not readings:
        return {"error": f"No telemetry readings found for period: {period}"}
    try:
        path = _generate_graph(
            readings, title=title, start=start, end=end, events=events_list, mac=dev_mac
        )
        summary = _summarize_readings(readings)
        summary["events"] = events_list
        return {
            "graph_path": path,
            "title": title,
            "period": period,
            "summary": summary,
        }
    except ValueError as e:
        return {"error": str(e)}


@tool
def list_home_ac() -> dict[str, Any]:
    """List all home AC units with live status. Use this first to discover available units."""
    return _list_devices()


@tool
def status_home_ac(
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Get full live status of a home AC unit, including any scheduled timers. Omit mac/name if only one unit."""
    return _client.status(mac, name)


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
            description="Target temperature in C (16-30). Omit to leave unchanged.",
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
            description="Louver swing on/off (controls both vertical and horizontal together). Omit to leave unchanged. Use swing_vertical/swing_horizontal for independent control.",
            default=None,
        ),
    ] = None,
    swing_vertical: Annotated[
        str | None,
        Field(
            description="Vertical (up-down) louver position. Controls swing independently from horizontal. Values: default (off), full (full swing), fixed-top, fixed-upper-middle, fixed-middle, fixed-lower-middle, fixed-bottom, swing-bottom, swing-lower-middle, swing-middle, swing-upper-middle, swing-top. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    swing_horizontal: Annotated[
        str | None,
        Field(
            description="Horizontal (left-right) louver position. Controls swing independently from vertical. Values: default (off), full (full swing), fixed-left, fixed-center-left, fixed-center, fixed-center-right, fixed-right. Omit to leave unchanged.",
            default=None,
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
    fresh_air: Annotated[
        bool | None,
        Field(
            description="Fresh air intake on/off. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    health: Annotated[
        bool | None,
        Field(
            description="Health (ionizer/UV purifier) on/off. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    sleep: Annotated[
        bool | None,
        Field(
            description="Sleep timer on/off. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    sleep_mode: Annotated[
        bool | None,
        Field(
            description="Sleep mode on/off. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    no_frost: Annotated[
        bool | None,
        Field(
            description="No-frost / anti-freeze heating on/off. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    energy_saving: Annotated[
        bool | None,
        Field(
            description="Energy saving mode on/off. Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    heat_cool_type: Annotated[
        int | None,
        Field(
            description="Heat/cool type value (device-specific int). Omit to leave unchanged.",
            default=None,
        ),
    ] = None,
    schedule: Annotated[
        ScheduleConfig | None,
        Field(
            description="Create or update a scheduled timer. Provide as an object with hour, minute, power_on, weekdays, schedule_id.",
            default=None,
        ),
    ] = None,
    delete_schedule_id: Annotated[
        int | None,
        Field(
            description="Delete a schedule by its ID (0-15). Takes precedence over schedule creation.",
            default=None,
        ),
    ] = None,
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Set one or more AC settings at once. Only provided parameters are applied. Can also create, update, or delete scheduled timers via the schedule and delete_schedule_id params."""
    return _client.set_multiple(
        power=power,
        mode=mode,
        temperature=temperature,
        fan_speed=fan_speed,
        oscillation=oscillation,
        swing_vertical=swing_vertical,
        swing_horizontal=swing_horizontal,
        xfan=xfan,
        light=light,
        quiet=quiet,
        turbo=turbo,
        fresh_air=fresh_air,
        health=health,
        sleep=sleep,
        sleep_mode=sleep_mode,
        no_frost=no_frost,
        energy_saving=energy_saving,
        heat_cool_type=heat_cool_type,
        schedule=schedule,
        delete_schedule_id=delete_schedule_id,
        mac=mac,
        name=name,
    )


@tool
def graph_home_ac(
    range: Annotated[  # noqa: A002
        str | None,
        Field(
            description="Time range: number + unit (h/d/w), e.g. '6h', '3d', '2w'. Or 'YYYY-MM-DD to YYYY-MM-DD'. Default: '1w'.",
            default=None,
        ),
    ] = None,
    mac: Annotated[str | None, Field(description=_mac_desc, default=None)] = None,
    name: Annotated[str | None, Field(description=_name_desc, default=None)] = None,
) -> dict[str, Any]:
    """Generate a temperature evolution graph (PNG) + structured data summary. Graph: blue line=room temp, green/red/orange line=AC target temp (green=room≈target, orange=heating/cooling, red=AC off). Summary includes current temps, power stats, and user action events. Returns {graph_path, title, period, summary}."""
    return _generate_temp_graph(range=range, mac=mac, name=name)


@tool
def restart_ac_data_collection() -> dict[str, Any]:
    """Restart the background data collection thread (auto-started on MCP init, polls every 1min)."""
    global _collector_thread  # noqa: PLW0603
    _stop_event.set()
    if _collector_thread:
        _collector_thread.join(timeout=5)
    if _collector_thread is not None and _collector_thread.is_alive():
        return {"error": "Old collector thread did not stop within 5s. Try again."}
    _stop_event.clear()
    _collector_thread = Thread(target=_collect, daemon=True)
    _collector_thread.start()
    return {"message": "Data collection restarted."}


@tool
def ac_data_collection_status() -> dict[str, Any]:
    """Check if data collection is running and how much data exists."""
    running = _collector_thread is not None and _collector_thread.is_alive()
    return {
        "running": running,
        "data_dir": str(_DATA_DIR),
        "total_files": len(list(_DATA_DIR.glob("*/telemetry/*.jsonl"))),
    }


if __name__ == "__main__":
    print("=== status ===")
    r = _client.status()
    print(dumps(r, indent=2, default=str))
