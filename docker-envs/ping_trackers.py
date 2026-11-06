#!/usr/bin/env python3
"""Ping trackers and remove dead ones from the additional section.

A tracker is considered dead only if its hostname does not exist (permanent
DNS failure: NXDOMAIN/NODATA), the URL is malformed, or its scheme is
unsupported by Transmission (http, https and udp only; an unsupported scheme
makes Transmission silently discard the whole default-trackers list).
Timeouts, connection refusals and *transient* resolver failures (EAI_AGAIN /
EAI_FAIL, e.g. a flaky local resolver) are kept because they are caused by
the local network environment rather than the tracker being down. Default
trackers are reported but left untouched.

Run: python3 ping_trackers.py
"""

from __future__ import annotations

import concurrent.futures
import random
import socket
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

FILE = Path(__file__).with_name("transmission.trackers.txt")

DEFAULT_PORTS = {"http": 80, "https": 443}


def parse_sections(text: str) -> list[dict]:
    """Split the tracker file into sections (header comments + trackers)."""
    sections: list[dict] = []
    header: list[str] = []
    trackers: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if trackers:
                sections.append({"header": header, "trackers": trackers})
                header = []
                trackers = []
            header.append(line)
        elif line.strip():
            trackers.append(line.strip())
        else:
            if trackers:
                sections.append({"header": header, "trackers": trackers})
                header = []
                trackers = []
    if header or trackers:
        sections.append({"header": header, "trackers": trackers})
    return sections


def build_file(sections: list[dict]) -> str:
    lines: list[str] = []
    for i, sec in enumerate(sections):
        lines.extend(sec["header"])
        lines.extend(sorted(sec["trackers"], key=str.lower))
        if i < len(sections) - 1:
            lines.append("")
    return "\n".join(lines) + "\n"


def _dns_error_kind(exc: Exception) -> str | None:
    """Classify a resolver failure as "dead", "inconclusive" or None (not DNS).

    `gaierror` covers both "this name does not exist" (EAI_NONAME/EAI_NODATA, a
    real answer) and "the resolver could not tell you right now"
    (EAI_AGAIN/EAI_FAIL). Only the former says anything about the tracker, so a
    transient failure must not count as dead -- otherwise one resolver blip
    silently strips live trackers from the list.
    """
    if isinstance(exc, socket.gaierror):
        return "dead" if exc.errno in (-2, -5) else "inconclusive"
    reason = getattr(exc, "reason", None)
    if isinstance(reason, Exception):
        return _dns_error_kind(reason)
    if isinstance(exc, OSError):
        if exc.errno in (-2, -5):
            return "dead"
        msg = str(exc).lower()
        if "name or service not known" in msg or "no address associated" in msg:
            return "dead"
        if "temporary failure in name resolution" in msg:
            return "inconclusive"
    return None


def _dns_verdict(exc: Exception) -> tuple[bool | None, str] | None:
    """Turn a resolver failure into a check verdict, or None if it is not DNS."""
    kind = _dns_error_kind(exc)
    if kind == "dead":
        return False, f"DNS error: {exc}"
    if kind == "inconclusive":
        return None, f"DNS inconclusive: {exc}"
    return None


def check_http(url: str) -> tuple[bool | None, str]:
    try:
        req = urllib.request.Request(url, method="HEAD")  # noqa: S310 - http(s) URLs validated before call
        req.add_header("User-Agent", "Transmission/4.0")
        with urllib.request.urlopen(req, timeout=10):  # noqa: S310 - URLs are validated as http(s) before reaching here
            return True, "HEAD ok"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code}"
    except Exception as exc:
        if verdict := _dns_verdict(exc):
            return verdict
        # GET fallback before giving up on ambiguous errors
        try:
            req = urllib.request.Request(url, method="GET")  # noqa: S310
            req.add_header("User-Agent", "Transmission/4.0")
            with urllib.request.urlopen(req, timeout=10):  # noqa: S310
                return True, "GET ok"
        except urllib.error.HTTPError as exc2:
            return True, f"GET HTTP {exc2.code}"
        except Exception as exc2:
            if verdict := _dns_verdict(exc2):
                return verdict
            return None, f"network: {exc2}"


def check_udp(host: str, port: int) -> tuple[bool | None, str]:
    for _ in range(3):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(10)
        try:
            transaction_id = random.randint(0, 0xFFFFFFFF)
            packet = struct.pack(">QII", 0x41727101980, 0, transaction_id)
            sock.sendto(packet, (host, port))
            data, _addr = sock.recvfrom(16)
            if len(data) >= 16:
                action, tid, _conn_id = struct.unpack(">IIQ", data[:16])
                if tid == transaction_id and action == 0:
                    return True, "UDP connect ok"
            return None, "bad response"
        except TimeoutError:
            pass
        except OSError as exc:
            if verdict := _dns_verdict(exc):
                return verdict
            return None, f"network: {exc}"
        except Exception as exc:
            return None, f"error: {exc}"
        finally:
            sock.close()
        time.sleep(0.5)
    return None, "timeout"


def check_tracker(tracker: str) -> tuple[bool | None, str]:
    parsed = urlparse(tracker)
    scheme = parsed.scheme
    if not scheme:
        return False, "invalid url: no scheme"
    host = parsed.hostname
    port = parsed.port or DEFAULT_PORTS.get(scheme)
    if not host:
        return False, "invalid url: no host"
    if not port:
        return False, f"invalid url: no port for {scheme}"

    if scheme in ("http", "https"):
        return check_http(tracker)
    if scheme == "udp":
        return check_udp(host, port)
    return False, f"unsupported scheme: {scheme}"


def main() -> None:
    text = FILE.read_text()
    sections = parse_sections(text)
    if not sections:
        raise SystemExit("No sections found in tracker file.")

    trackers_to_check: list[tuple[int, str]] = [
        (idx, t) for idx, sec in enumerate(sections) for t in sec["trackers"]
    ]

    results: dict[str, tuple[bool | None, str]] = {}
    print(f"Checking {len(trackers_to_check)} trackers...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(check_tracker, t): (idx, t) for idx, t in trackers_to_check
        }
        for future in concurrent.futures.as_completed(futures):
            idx, tracker = futures[future]
            try:
                status, reason = future.result()
            except Exception as exc:
                status, reason = None, f"exception: {exc}"
            results[tracker] = (status, reason)
            label = (
                "LIVE" if status is True else ("DEAD" if status is False else "UNREACH")
            )
            print(f"{label}: {tracker} ({reason})")

    dead_by_section: dict[int, list[tuple[str, str]]] = {
        i: [] for i in range(len(sections))
    }
    for idx, sec in enumerate(sections):
        kept = []
        for t in sec["trackers"]:
            status, reason = results[t]
            if status is False:
                dead_by_section[idx].append((t, reason))
                if idx != 0:
                    continue
            kept.append(t)
        sec["trackers"] = kept

    FILE.write_text(build_file(sections))

    print("\n=== Summary ===")
    for idx, sec in enumerate(sections):
        header = " / ".join(sec["header"])
        dead = dead_by_section[idx]
        print(f"{header}: removed {len(dead)} dead trackers")
        for t, reason in dead:
            print(f"  - {t} ({reason})")


if __name__ == "__main__":
    main()
