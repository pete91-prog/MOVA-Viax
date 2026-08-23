"""Tests for utils module."""

import os
import tempfile
from unittest.mock import Mock, patch
import pytest

from custom_components.mova_viax.dreame.utils import download_file


@patch('custom_components.mova_viax.dreame.utils.requests.get')
def test_download_file_binary_success(mock_get):
    """Test successful binary file download."""
    # Setup mock response
    mock_response = Mock()
    mock_response.content = b"binary_data_content"
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response
    
    # Mock URL getter
    def get_url(path):
        return f"https://example.com/{path}"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = download_file(
            file_path="path/to/file.bin",
            get_download_url=get_url,
            hass_config_dir=tmpdir,
            timeout=30
        )
        
        # Verify result
        assert result is not None
        assert result["path"] == "path/to/file.bin"
        expected_path = os.path.join(tmpdir, "www", "dreame", "path/to/file.bin")
        assert result["local_path"] == expected_path
        assert result["size_bytes"] == 19
        
        # Verify file exists and has correct content
        assert os.path.exists(result["local_path"])
        with open(result["local_path"], "rb") as f:
            assert f.read() == b"binary_data_content"


@patch('custom_components.mova_viax.dreame.utils.requests.get')
def test_download_file_text_success(mock_get):
    """Test successful text file download (saved as binary)."""
    # Setup mock response
    mock_response = Mock()
    mock_response.content = b"text content"
    mock_response.text = "text content"
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response
    
    # Mock URL getter
    def get_url(path):
        return f"https://example.com/{path}"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = download_file(
            file_path="path/to/file.txt",
            get_download_url=get_url,
            hass_config_dir=tmpdir,
            timeout=30
        )
        
        # Verify result
        assert result is not None
        assert result["path"] == "path/to/file.txt"
        expected_path = os.path.join(tmpdir, "www", "dreame", "path/to/file.txt")
        assert result["local_path"] == expected_path
        assert result["size_bytes"] == 12
        
        # Verify file exists and has correct content (can be read as text)
        assert os.path.exists(result["local_path"])
        with open(result["local_path"], "r", encoding="utf-8") as f:
            assert f.read() == "text content"


def test_download_file_empty_path():
    """Test download with empty file path."""
    def get_url(path):
        return f"https://example.com/{path}"
    
    result = download_file(
        file_path="",
        get_download_url=get_url,
        hass_config_dir="/tmp",
        timeout=30
    )
    
    assert result is None


def test_download_file_no_url():
    """Test download when URL getter returns None."""
    def get_url(path):
        return None
    
    result = download_file(
        file_path="path/to/file.bin",
        get_download_url=get_url,
        hass_config_dir="/tmp",
        timeout=30
    )
    
    assert result is None


@patch('custom_components.mova_viax.dreame.utils.requests.get')
def test_download_file_request_failure(mock_get):
    """Test download when HTTP request fails."""
    import requests
    mock_get.side_effect = requests.exceptions.RequestException("Network error")
    
    def get_url(path):
        return f"https://example.com/{path}"
    
    result = download_file(
        file_path="path/to/file.bin",
        get_download_url=get_url,
        hass_config_dir="/tmp",
        timeout=30
    )
    
    assert result is None


@patch('custom_components.mova_viax.dreame.utils.requests.get')
def test_download_file_mirrors_directory_structure(mock_get):
    """Test that download mirrors the cloud directory structure."""
    # Setup mock response
    mock_response = Mock()
    mock_response.content = b"data"
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response
    
    def get_url(path):
        return f"https://example.com/{path}"
    
    # Test with complex nested path
    file_path = "ali_dreame/2025/10/11/user123/device456/file.tbz2"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = download_file(
            file_path=file_path,
            get_download_url=get_url,
            hass_config_dir=tmpdir,
            timeout=30
        )
        
        # Verify the full path mirrors the cloud structure under www/dreame
        expected_path = os.path.join(tmpdir, "www", "dreame", file_path)
        assert result["local_path"] == expected_path
        assert os.path.exists(expected_path)
        
        # Verify all parent directories were created
        assert os.path.isdir(os.path.dirname(expected_path))


@patch('custom_components.mova_viax.dreame.utils.requests.get')
def test_download_file_custom_timeout(mock_get):
    """Test that custom timeout is passed to requests.get."""
    mock_response = Mock()
    mock_response.content = b"data"
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response
    
    def get_url(path):
        return f"https://example.com/{path}"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        download_file(
            file_path="file.bin",
            get_download_url=get_url,
            hass_config_dir=tmpdir,
            timeout=99
        )
        
        # Verify timeout was passed to requests.get
        mock_get.assert_called_once()
        assert mock_get.call_args[1]['timeout'] == 99
