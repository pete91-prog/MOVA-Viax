"""Tests for MOVA ViAX JSON saved-map rendering."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.mova_viax.viax_map import (
    _find_object_name,
    is_viax_json_map,
    parse_clean_record,
    refresh_device_map,
    render_map_png,
)

VIAX_MAP = {
    "map": [{"type": 0, "data": [[0, 0], [400, 0], [400, 300], [0, 300]]}],
    "obstacle": [{"data": [[80, 80], [140, 80], [140, 140], [80, 140]]}],
    "trajectory": [{"data": [[20, 20], [200, 150], [360, 40]]}],
    "dock": [20, 20],
    "start": 1_700_000_000,
    "end": 1_700_003_600,
    "areas": 25.5,
    "map_area": 120,
    "map_name": "Front lawn",
    "faults": ["none"],
}


def test_is_viax_json_map_detects_model():
    device = SimpleNamespace(info=SimpleNamespace(model="mova.mower.g2420b"), model=None)
    assert is_viax_json_map(device) is True
    assert is_viax_json_map(SimpleNamespace(), "mova.mower.g2420b") is True


def test_is_viax_json_map_rejects_unrelated_model_with_vector_map():
    device = SimpleNamespace(
        info=SimpleNamespace(model="dreame.mower.g2408"),
        model="dreame.mower.g2408",
        vector_map=object(),
    )
    assert is_viax_json_map(device) is False


def test_find_object_name_walks_nested_event_payload():
    events = [
        {
            "value": '{"file":"ali_dreame/mova.mower.g2420b/abc/map.json"}',
        }
    ]
    assert _find_object_name(events) == "ali_dreame/mova.mower.g2420b/abc/map.json"


def test_parse_clean_record_duration_and_faults():
    summary = parse_clean_record(VIAX_MAP)
    assert summary is not None
    assert summary["duration_min"] == 60.0
    assert summary["mowed_area"] == 25.5
    assert summary["fault_count"] == 1
    assert summary["map_name"] == "Front lawn"


def test_render_map_png_returns_png_bytes():
    png = render_map_png(VIAX_MAP)
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_refresh_device_map_caches_json(monkeypatch):
    cloud = SimpleNamespace()
    device = SimpleNamespace(cloud_device=cloud)

    def fake_fetch(_cloud):
        return VIAX_MAP

    monkeypatch.setattr("custom_components.mova_viax.viax_map.fetch_latest_map_json", fake_fetch)
    refresh_device_map(device, min_interval=0)
    assert device.viax_map_json == VIAX_MAP
    assert device.viax_last_mow["mowed_area"] == 25.5
