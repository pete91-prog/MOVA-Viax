"""Test device registration for Dreame Mower integration."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mova_viax.const import DOMAIN
from custom_components.mova_viax.coordinator import DreameMowerCoordinator
from custom_components.mova_viax.entity import DreameMowerEntity
from custom_components.mova_viax.config_flow import (
    CONF_MAC, 
    CONF_MODEL, 
    CONF_SERIAL,
    CONF_ACCOUNT_TYPE,
    CONF_COUNTRY,
    CONF_DID,
)
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture
def test_config_entry():
    """Create a test config entry for testing."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Mower Device",
        data={
            CONF_NAME: "Test Mower Device",
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "password123",
            CONF_COUNTRY: "US",
            CONF_ACCOUNT_TYPE: "dreame",
            CONF_MAC: "11:22:33:44:55:66",
            CONF_MODEL: "dreame.mower.test123",
            CONF_SERIAL: "TEST123456",
            CONF_DID: "test_device_456",
        },
        entry_id="test_device_entry",
    )


async def test_device_info_with_valid_data(hass: HomeAssistant, test_config_entry):
    """Test that device_info is properly created with valid coordinator data."""
    coordinator = DreameMowerCoordinator(hass, entry=test_config_entry)
    
    # Mock device properties for testing
    with patch.object(DreameMowerCoordinator, 'device_mac', new_callable=PropertyMock) as mock_mac, \
         patch.object(DreameMowerCoordinator, 'device_model', new_callable=PropertyMock) as mock_model, \
         patch.object(DreameMowerCoordinator, 'device_name', new_callable=PropertyMock) as mock_name:
        
        mock_mac.return_value = "11:22:33:44:55:66"
        mock_model.return_value = "dreame.mower.test123"
        mock_name.return_value = "Test Mower Device"
        
        # Create a test entity
        entity = DreameMowerEntity(coordinator, "test_entity")
        
        device_info = entity.device_info
        
        assert device_info is not None
        assert device_info["name"] == "Test Mower Device"
        assert device_info["manufacturer"] == "Dreametech™"
        assert device_info["model"] == "dreame.mower.test123"
        assert (DOMAIN, "11:22:33:44:55:66") in device_info["identifiers"]


async def test_device_info_with_complete_config_data(hass: HomeAssistant):
    """Test that device_info uses real config entry data."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Mower Complete",
        data={
            CONF_NAME: "Test Mower Complete",
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "password123",
            CONF_COUNTRY: "US",
            CONF_ACCOUNT_TYPE: "dreame",
            CONF_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_MODEL: "dreame.mower.p2009",
            CONF_SERIAL: "12345ABCDE",
            CONF_DID: "test_device_789",
        },
        entry_id="test_complete_entry",
    )
    
    coordinator = DreameMowerCoordinator(hass, entry=config_entry)
    entity = DreameMowerEntity(coordinator, "test_entity")
    
    # Should return proper device_info with config entry data
    device_info = entity.device_info
    assert device_info is not None
    assert device_info["name"] == "Test Mower Complete"
    assert device_info["manufacturer"] == "Dreametech™"
    assert device_info["model"] == "dreame.mower.p2009"
    assert (DOMAIN, "AA:BB:CC:DD:EE:FF") in device_info["identifiers"]


async def test_device_info_with_mova_model(hass: HomeAssistant, test_config_entry):
    """Test that device_info shows Dreametech as manufacturer for Mova models."""
    coordinator = DreameMowerCoordinator(hass, entry=test_config_entry)
    
    # Mock device properties for testing
    with patch.object(DreameMowerCoordinator, 'device_mac', new_callable=PropertyMock) as mock_mac, \
         patch.object(DreameMowerCoordinator, 'device_model', new_callable=PropertyMock) as mock_model, \
         patch.object(DreameMowerCoordinator, 'device_name', new_callable=PropertyMock) as mock_name:
        
        mock_mac.return_value = "11:22:33:44:55:66"
        mock_model.return_value = "mova.mower.test456"
        mock_name.return_value = "Test Mowa Device"
        
        entity = DreameMowerEntity(coordinator, "test_entity")
        device_info = entity.device_info
        
        assert device_info is not None
        assert device_info["manufacturer"] == "Dreametech™"
    assert device_info["model"] == "mova.mower.test456"


async def test_device_info_with_mova_model_from_config(hass: HomeAssistant):
    """Test that device_info correctly uses Mova model from config entry."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Mowa Device",
        data={
            CONF_NAME: "Test Mowa Device",
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "password123",
            CONF_COUNTRY: "US",
            CONF_ACCOUNT_TYPE: "dreame",
            CONF_MAC: "FF:EE:DD:CC:BB:AA",
            CONF_MODEL: "mova.mower.p2045",
            CONF_SERIAL: "MOVA98765",
            CONF_DID: "mova_device_456",
        },
        entry_id="test_mova_entry",
    )
    
    coordinator = DreameMowerCoordinator(hass, entry=config_entry)
    entity = DreameMowerEntity(coordinator, "test_entity")
    
    # Should return proper device_info with Mova model from config
    device_info = entity.device_info
    assert device_info is not None
    assert device_info["name"] == "Test Mowa Device"
    assert device_info["manufacturer"] == "Dreametech™"
    assert device_info["model"] == "mova.mower.p2045"
    assert (DOMAIN, "FF:EE:DD:CC:BB:AA") in device_info["identifiers"]


async def test_single_device_creation_across_entity_types(hass: HomeAssistant, test_config_entry):
    """Test that entity creates device_info when MAC is provided."""
    coordinator = DreameMowerCoordinator(hass, entry=test_config_entry)
    
    # Mock device properties for testing
    with patch.object(DreameMowerCoordinator, 'device_mac', new_callable=PropertyMock) as mock_mac, \
         patch.object(DreameMowerCoordinator, 'device_model', new_callable=PropertyMock) as mock_model, \
         patch.object(DreameMowerCoordinator, 'device_name', new_callable=PropertyMock) as mock_name:
        
        mock_mac.return_value = "11:22:33:44:55:66"
        mock_model.return_value = "dreame.mower.test123"
        mock_name.return_value = "Test Device"
        
        # Create entity
        base_entity = DreameMowerEntity(coordinator, "test_entity")
        
        # Should return device_info when MAC is available
        base_device_info = base_entity.device_info
        
        assert base_device_info is not None
        assert base_device_info["name"] == "Test Device"
        assert (DOMAIN, "11:22:33:44:55:66") in base_device_info["identifiers"]