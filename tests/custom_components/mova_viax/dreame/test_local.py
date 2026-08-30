"""Tests for LAN fallback used when the cloud is unreachable."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.mova_viax.config_flow import DreameMowerConfigFlow
from custom_components.mova_viax.dreame.local import (
    LocalMowerProtocol,
    _normalize_mac,
    _normalize_token,
    discover_miio_hosts,
)


def test_normalize_token_defaults_to_zeros():
    assert _normalize_token(None) == "0" * 32
    assert _normalize_token("  ") == "0" * 32
    assert _normalize_token("aabbccddeeff00112233445566778899") == "aabbccddeeff00112233445566778899"


def test_normalize_mac_strips_separators():
    assert _normalize_mac("AA:BB:CC:DD:EE:FF") == "aabbccddeeff"
    assert _normalize_mac("aa-bb-cc-dd-ee-ff") == "aabbccddeeff"


def test_extract_info_keeps_lan_address_and_token():
    flow = object.__new__(DreameMowerConfigFlow)
    flow.host = None
    flow.token = None
    flow.device_id = None
    flow.mac = None
    flow.model = None
    flow.serial_number = None
    flow.name = None
    flow._extract_info({
        "did": "123",
        "mac": "aa:bb:cc:dd:ee:ff",
        "model": "mova.mower.g2420b",
        "sn": "SN1",
        "localip": "192.168.1.50",
        "token": "aabbccddeeff00112233445566778899",
        "customName": "Garden",
    })
    assert flow.host == "192.168.1.50"
    assert flow.token == "aabbccddeeff00112233445566778899"
    assert flow.name == "Garden"


def test_local_protocol_connect_without_miio_fails_closed(monkeypatch):
    monkeypatch.setattr("custom_components.mova_viax.dreame.local._HAS_MIIO", False)
    proto = LocalMowerProtocol("192.168.1.50", "0" * 32, "did")
    proto._device = None
    assert proto.connect() is False
    assert proto.connected is False


def test_local_protocol_send_marks_connected():
    proto = LocalMowerProtocol("192.168.1.50", "0" * 32, "did")
    proto._device = SimpleNamespace(send=Mock(return_value={"ok": 1}))
    assert proto.send("action", {"siid": 5, "aiid": 1}) == {"ok": 1}
    assert proto.connected is True
    proto._device.send.assert_called_once()


def test_discover_miio_hosts_collects_replies(monkeypatch):
    replies = [(b"hello", ("192.168.1.50", 54321)), TimeoutError()]

    class FakeSocket:
        def setsockopt(self, *args, **kwargs):
            return None

        def settimeout(self, value):
            return None

        def sendto(self, data, addr):
            return len(data)

        def recvfrom(self, size):
            item = replies.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        def close(self):
            return None

    monkeypatch.setattr("custom_components.mova_viax.dreame.local.socket.socket", lambda *a, **k: FakeSocket())
    assert discover_miio_hosts(timeout=0.1) == ["192.168.1.50"]
