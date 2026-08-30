"""Device-layer tests for cloud-to-LAN command fallback."""

from __future__ import annotations

from unittest.mock import Mock, patch

from custom_components.mova_viax.dreame.const import ACTION_PAUSE, ACTION_START_MOWING
from custom_components.mova_viax.dreame.device import DreameMowerDevice


def _device(
    host: str | None = "192.168.1.50",
    prefer_local: bool = False,
    token: str | None = "0" * 32,
) -> DreameMowerDevice:
    with patch(
        "custom_components.mova_viax.dreame.device.DreameMowerCloudDevice"
    ) as cloud_cls:
        cloud = Mock()
        cloud.connected = False
        cloud.device_reachable = False
        cloud.send = Mock(side_effect=ConnectionError("no internet"))
        cloud_cls.return_value = cloud
        device = DreameMowerDevice(
            device_id="did-1",
            username="u",
            password="p",
            account_type="mova",
            country="eu",
            hass_config_dir="/tmp",
            host=host,
            token=token,
            prefer_local=prefer_local,
            mac="aa:bb:cc:dd:ee:ff",
        )
        device._raw_cloud_device = cloud
        return device


def test_send_uses_lan_when_cloud_is_down():
    device = _device()
    device._local = Mock()
    device._local.host = "192.168.1.50"
    device._local.connected = True
    device._local.send.return_value = "local-ok"

    result = device._send_command("action", {"siid": 5, "aiid": 1})

    assert result == "local-ok"
    device._local.send.assert_called_once()
    device._raw_cloud_device.send.assert_not_called()


def test_send_falls_back_to_lan_after_cloud_timeout():
    device = _device(prefer_local=False)
    device._raw_cloud_device.connected = True
    device._raw_cloud_device.send.side_effect = TimeoutError("cloud timeout")
    device._local = Mock()
    device._local.host = "192.168.1.50"
    device._local.send.return_value = "local-ok"

    result = device._send_command("get_properties", [{"siid": 3, "piid": 1}])

    assert result == "local-ok"
    device._local.send.assert_called_once()


def test_connected_stays_true_on_lan_after_cloud_drop():
    device = _device()
    device._raw_cloud_device.connected = False
    device._local = Mock()
    device._local.connected = True

    assert device.local_connected is True
    assert device.connected is True
    assert device.online is True
    device._handle_disconnected()
    assert device.connected is True


def test_start_and_pause_use_lan_when_cloud_is_down():
    """Lawn-mower actions must not bind to the raw cloud client's send()."""
    device = _device()
    device._local = Mock()
    device._local.host = "192.168.1.50"
    device._local.connected = True
    device._local.send.return_value = {"ok": 1}

    assert device._cloud_device.execute_action(ACTION_START_MOWING) is True
    assert device._cloud_device.execute_action(ACTION_PAUSE) is True

    methods = [call.args[0] for call in device._local.send.call_args_list]
    assert methods == ["action", "action"]
    device._raw_cloud_device.send.assert_not_called()


def test_get_properties_on_wrapper_uses_lan():
    device = _device()
    device._local = Mock()
    device._local.host = "192.168.1.50"
    device._local.send.return_value = [{"siid": 3, "piid": 1, "value": 80, "code": 0}]

    result = device._cloud_device.get_properties([{"siid": 3, "piid": 1}])

    assert result[0]["value"] == 80
    device._local.send.assert_called_once()
    device._raw_cloud_device.send.assert_not_called()


def test_device_info_fills_missing_lan_address():
    device = _device(host=None, token=None)
    assert device.lan_credentials == (None, None)
    device._update_device_state_from_info({
        "localip": "192.168.1.77",
        "token": "aabbccddeeff00112233445566778899",
        "battery": 40,
        "latestStatus": 1,
    })
    host, token = device.lan_credentials
    assert host == "192.168.1.77"
    assert token == "aabbccddeeff00112233445566778899"
    assert device._local is not None
    assert device._local.host == "192.168.1.77"


def test_configured_host_is_not_overwritten_by_cloud():
    device = _device(host="192.168.1.50")
    device._update_device_state_from_info({"localip": "10.0.0.9", "token": "b" * 32})
    assert device.lan_credentials[0] == "192.168.1.50"
