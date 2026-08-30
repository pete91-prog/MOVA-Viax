"""LAN (miIO) transport so the mower can be commanded without the cloud.

Dreame/MOVA mowers speak the same JSON-RPC methods the cloud relays
(``get_properties``, ``set_properties``, ``action``) on UDP port 54321 when
the robot is on the same Wi-Fi as Home Assistant. This module is the fallback
used when internet to the Dreame/MOVA cloud is cut.
"""

from __future__ import annotations

import logging
import socket
from typing import Any

_LOGGER = logging.getLogger(__name__)

MIIO_PORT = 54321
_HELLO = bytes.fromhex(
    "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)

try:
    from miio import Device
    from miio.exceptions import DeviceError, DeviceException

    _HAS_MIIO = True
except ImportError:  # pragma: no cover - python-miio is a declared requirement
    Device = None  # type: ignore[misc, assignment]
    DeviceError = OSError  # type: ignore[misc, assignment]
    DeviceException = OSError  # type: ignore[misc, assignment]
    _HAS_MIIO = False


def _normalize_mac(mac: str | None) -> str:
    return (mac or "").replace(":", "").replace("-", "").lower()


def _normalize_token(token: str | None) -> str:
    cleaned = (token or "").strip()
    if len(cleaned) == 32:
        return cleaned
    return "0" * 32


def discover_miio_hosts(timeout: float = 3.0) -> list[str]:
    """Return IPv4 addresses that answer a miIO hello on the LAN."""
    hosts: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.sendto(_HELLO, ("255.255.255.255", MIIO_PORT))
        while True:
            try:
                _data, addr = sock.recvfrom(1024)
            except TimeoutError:
                break
            except OSError:
                break
            host = addr[0]
            if host not in hosts:
                hosts.append(host)
    except OSError as ex:
        _LOGGER.debug("miIO discovery broadcast failed: %s", ex)
    finally:
        sock.close()
    return hosts


class LocalMowerProtocol:
    """Talk to a mower on the LAN using the miIO protocol."""

    def __init__(
        self,
        host: str,
        token: str | None = None,
        device_id: str | None = None,
    ) -> None:
        self.host = host
        self.token = _normalize_token(token)
        self.device_id = str(device_id) if device_id is not None else None
        self._connected = False
        self._device = None
        if _HAS_MIIO and host:
            self._device = Device(host, self.token)

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Handshake with the robot. Returns True when it answers locally."""
        if self._device is None:
            _LOGGER.debug("Local miIO client unavailable (missing python-miio or host)")
            self._connected = False
            return False
        try:
            info = self._device.info()
            self._connected = True
            _LOGGER.info(
                "Local mower connection to %s succeeded (model=%s)",
                self.host,
                getattr(info, "model", "unknown"),
            )
            return True
        except (DeviceException, DeviceError, OSError, TimeoutError) as ex:
            _LOGGER.warning("Local mower connection to %s failed: %s", self.host, ex)
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False

    def send(self, method: str, parameters: Any, retry_count: int = 2) -> Any:
        """Send one JSON-RPC method to the robot on the LAN."""
        if self._device is None:
            raise ConnectionError("Local miIO client is not available")
        last_error: Exception | None = None
        attempts = max(retry_count, 0) + 1
        for _ in range(attempts):
            try:
                result = self._device.send(method, parameters)
                self._connected = True
                return result
            except (DeviceException, DeviceError, OSError, TimeoutError) as ex:
                last_error = ex
                _LOGGER.debug("Local send %s failed: %s", method, ex)
        self._connected = False
        raise ConnectionError(f"Local send {method} failed: {last_error}") from last_error

    def get_properties(self, parameters: Any = None, retry_count: int = 1) -> Any:
        return self.send("get_properties", parameters=parameters, retry_count=retry_count)

    def action(self, siid: int, aiid: int, parameters: list | None = None, retry_count: int = 2) -> Any:
        if parameters is None:
            parameters = []
        payload: dict[str, Any] = {
            "siid": siid,
            "aiid": aiid,
            "in": parameters,
        }
        if self.device_id is not None:
            payload["did"] = str(self.device_id)
        return self.send("action", payload, retry_count=retry_count)

    def info_mac(self) -> str | None:
        """Return the MAC advertised by the robot, if a handshake works."""
        if self._device is None:
            return None
        try:
            info = self._device.info()
            return getattr(info, "mac_address", None) or getattr(info, "mac", None)
        except (DeviceException, DeviceError, OSError, TimeoutError):
            return None


def find_host_for_mac(mac: str, token: str | None = None, timeout: float = 3.0) -> str | None:
    """Scan the LAN for a miIO device whose MAC matches ``mac``."""
    wanted = _normalize_mac(mac)
    if not wanted:
        return None
    for host in discover_miio_hosts(timeout=timeout):
        proto = LocalMowerProtocol(host, token)
        found = proto.info_mac()
        if found and _normalize_mac(found) == wanted:
            return host
    return None
