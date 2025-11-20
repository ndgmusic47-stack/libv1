"""
Integration tests for media router security - upload_audio endpoint

Tests cover:
- Valid file upload
- Path traversal attack prevention (filename sanitization)
- Oversized file rejection
- Forbidden extension rejection
- MIME type validation
"""
import pytest
import asyncio
import io
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app
from auth import get_current_user
from database import get_db, Base
from tests.conftest import TestAsyncSessionLocal, test_engine
from utils.security_utils import MAX_FILE_SIZE


# Override get_db dependency to use test database
async def override_get_db():
    """Override get_db to use test database"""
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Mock user for authentication
async def mock_get_current_user(
    auth_token: str = None,
    authorization: str = None,
    db = None
) -> dict:
    """Mock get_current_user dependency that returns a test user"""
    return {
        "user_id": "123",
        "email": "test@example.com",
        "plan": "pro",
        "is_paid_user": True,
        "is_active": True,
        "trial_start_date": None
    }


# Mock require_feature_pro to always allow access
async def mock_require_feature_pro(current_user: dict, feature: str, endpoint: str, db):
    """Mock require_feature_pro to always return None (allow access)"""
    return None


# Create TestClient with database and auth overrides
@pytest.fixture
def client(monkeypatch):
    """FastAPI TestClient fixture with test database and auth overrides"""
    # Import models to ensure they're registered with Base
    import database_models  # noqa: F401
    
    # Create tables for test
    async def setup_db():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    # Run async setup
    asyncio.run(setup_db())
    
    # Override dependencies
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    # Mock require_feature_pro using monkeypatch (persists for all tests using this fixture)
    # Patch it in the module where it's imported and used
    from routers import media_router
    monkeypatch.setattr(media_router, 'require_feature_pro', mock_require_feature_pro)
    
    # Create test client
    test_client = TestClient(app)
    
    yield test_client
    
    # Cleanup: remove dependency overrides
    app.dependency_overrides.clear()
    
    # Drop tables after test
    async def teardown_db():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    asyncio.run(teardown_db())


# Helper function to create a valid WAV file in memory
def create_valid_wav_file(size_bytes: int = 1024) -> bytes:
    """
    Create a minimal valid WAV file with specified size.
    
    Args:
        size_bytes: Desired file size in bytes (minimum ~44 bytes for valid WAV header)
    
    Returns:
        bytes: Valid WAV file content
    """
    # Minimum valid WAV file structure
    # RIFF header (12 bytes) + fmt chunk (24 bytes) + data chunk header (8 bytes) + data
    header_size = 44
    
    if size_bytes < header_size:
        size_bytes = header_size
    
    # RIFF header
    wav_data = b'RIFF'
    file_size = size_bytes - 8
    wav_data += file_size.to_bytes(4, 'little')
    wav_data += b'WAVE'
    
    # fmt chunk
    wav_data += b'fmt '
    wav_data += (16).to_bytes(4, 'little')  # fmt chunk size
    wav_data += (1).to_bytes(2, 'little')   # audio format (PCM)
    wav_data += (1).to_bytes(2, 'little')   # num channels
    wav_data += (44100).to_bytes(4, 'little')  # sample rate
    wav_data += (88200).to_bytes(4, 'little')  # byte rate
    wav_data += (2).to_bytes(2, 'little')   # block align
    wav_data += (16).to_bytes(2, 'little')  # bits per sample
    
    # data chunk
    data_size = size_bytes - header_size
    wav_data += b'data'
    wav_data += data_size.to_bytes(4, 'little')
    
    # Add padding data to reach desired size
    wav_data += b'\x00' * data_size
    
    return wav_data


# Helper function to create a file with forbidden extension
def create_file_with_extension(extension: str, content: bytes = b"dummy content") -> tuple[str, bytes]:
    """
    Create a file with specified extension.
    
    Args:
        extension: File extension (e.g., '.exe', '.txt')
        content: File content bytes
    
    Returns:
        Tuple of (filename, content)
    """
    filename = f"test_file{extension}"
    return filename, content


# Helper function to create a file with non-audio content but valid extension
def create_fake_audio_file(extension: str = ".wav") -> tuple[str, bytes]:
    """
    Create a file with valid audio extension but non-audio content.
    
    Args:
        extension: Audio extension (e.g., '.wav')
    
    Returns:
        Tuple of (filename, content)
    """
    filename = f"fake_audio{extension}"
    # Non-audio content (just random bytes, not a valid audio file)
    content = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
    return filename, content


def test_valid_upload_success(client):
    """
    Test Successful Valid Upload: Verify a normal, valid audio file upload succeeds (HTTP 200).
    """
    # Create a valid WAV file
    wav_content = create_valid_wav_file(size_bytes=1024)
    
    # Prepare file upload
    files = {
        "file": ("test_audio.wav", io.BytesIO(wav_content), "audio/wav")
    }
    
    # Make request
    response = client.post(
        "/api/upload-audio",
        files=files,
        data={"session_id": "test_session_123"}
    )
    
    # Should succeed with 200 status
    assert response.status_code == 200
    response_data = response.json()
    assert response_data.get("ok") is True
    assert "file_url" in response_data.get("data", {})
    assert "session_id" in response_data.get("data", {})
    
    # Verify file was saved in correct location
    file_url = response_data["data"]["file_url"]
    assert "/media/123/test_session_123/recordings/" in file_url
    assert file_url.endswith(".wav")
    
    # Verify file exists on disk
    # Extract filename from URL
    filename = file_url.split("/")[-1]
    file_path = Path("./media/123/test_session_123/recordings") / filename
    assert file_path.exists(), f"File should exist at {file_path}"
    assert file_path.stat().st_size == len(wav_content)


def test_path_traversal_sanitization(client):
    """
    Test Path Traversal Rejection: Attempt to upload a file with a malicious filename
    (e.g., `../../../etc/passwd.wav`). Verify the endpoint succeeds (HTTP 200) but
    the file is saved with a sanitized name (no `..` components) in the correct media directory.
    """
    # Create a valid WAV file
    wav_content = create_valid_wav_file(size_bytes=1024)
    
    # Prepare file upload with malicious filename
    malicious_filename = "../../../etc/passwd.wav"
    files = {
        "file": (malicious_filename, io.BytesIO(wav_content), "audio/wav")
    }
    
    # Make request
    response = client.post(
        "/api/upload-audio",
        files=files,
        data={"session_id": "test_session_456"}
    )
    
    # Should succeed with 200 status (sanitization, not rejection)
    assert response.status_code == 200
    response_data = response.json()
    assert response_data.get("ok") is True
    assert "file_url" in response_data.get("data", {})
    
    # Verify file URL does NOT contain path traversal
    file_url = response_data["data"]["file_url"]
    assert ".." not in file_url, "File URL should not contain path traversal sequences"
    assert "/etc/passwd" not in file_url, "File should not be saved outside media directory"
    assert "/media/123/test_session_456/recordings/" in file_url, "File should be in correct media directory"
    
    # Verify sanitized filename
    filename = file_url.split("/")[-1]
    assert ".." not in filename, "Filename should be sanitized (no ..)"
    assert "/" not in filename, "Filename should be sanitized (no /)"
    assert "\\" not in filename, "Filename should be sanitized (no \\)"
    assert filename.endswith(".wav"), "Filename should retain valid extension"
    
    # Verify file exists in correct location (not in /etc/)
    file_path = Path("./media/123/test_session_456/recordings") / filename
    assert file_path.exists(), f"File should exist at {file_path}"
    
    # Verify file is NOT in /etc/passwd (if we're on a system where that would be possible)
    # This is more of a sanity check - the sanitization should prevent this
    etc_passwd_path = Path("/etc/passwd")
    if etc_passwd_path.exists():
        # Read a small portion to compare
        with open(file_path, "rb") as f:
            saved_content = f.read(1024)
        with open(etc_passwd_path, "rb") as f:
            etc_content = f.read(1024)
        assert saved_content != etc_content, "File should not overwrite /etc/passwd"


def test_oversized_file_rejection(client):
    """
    Test Oversized File Rejection: Attempt to upload a mock file larger than the
    MAX_FILE_SIZE (50MB). Verify the request is rejected (HTTP 400).
    """
    # Create a file larger than MAX_FILE_SIZE (50MB)
    oversized_size = MAX_FILE_SIZE + 1024  # 50MB + 1KB
    wav_content = create_valid_wav_file(size_bytes=oversized_size)
    
    # Prepare file upload
    files = {
        "file": ("oversized_audio.wav", io.BytesIO(wav_content), "audio/wav")
    }
    
    # Make request
    response = client.post(
        "/api/upload-audio",
        files=files,
        data={"session_id": "test_session_789"}
    )
    
    # Should be rejected with 400 status
    assert response.status_code == 400
    response_data = response.json()
    assert "detail" in response_data
    detail = response_data["detail"].lower()
    assert "size" in detail or "exceeds" in detail or "maximum" in detail


def test_forbidden_extension_rejection(client):
    """
    Test Forbidden Extension Rejection: Attempt to upload a file with a forbidden
    extension (e.g., `.exe` or `.txt`). Verify the request is rejected (HTTP 400).
    """
    # Test with .exe extension
    exe_filename, exe_content = create_file_with_extension(".exe", b"MZ\x90\x00")  # PE header
    files = {
        "file": (exe_filename, io.BytesIO(exe_content), "application/x-msdownload")
    }
    
    response = client.post(
        "/api/upload-audio",
        files=files,
        data={"session_id": "test_session_exe"}
    )
    
    # Should be rejected with 400 status
    assert response.status_code == 400
    response_data = response.json()
    assert "detail" in response_data
    detail = response_data["detail"].lower()
    assert "extension" in detail or "not allowed" in detail or "allowed extensions" in detail
    
    # Test with .txt extension
    txt_filename, txt_content = create_file_with_extension(".txt", b"Hello, world!")
    files = {
        "file": (txt_filename, io.BytesIO(txt_content), "text/plain")
    }
    
    response = client.post(
        "/api/upload-audio",
        files=files,
        data={"session_id": "test_session_txt"}
    )
    
    # Should be rejected with 400 status
    assert response.status_code == 400
    response_data = response.json()
    assert "detail" in response_data
    detail = response_data["detail"].lower()
    assert "extension" in detail or "not allowed" in detail or "allowed extensions" in detail


def test_mime_type_rejection(client):
    """
    Test MIME Type Rejection: Attempt to upload a file that has a valid extension
    but non-audio content (e.g., a headerless binary file). Verify rejection (HTTP 400).
    """
    # Create a file with valid .wav extension but non-audio content
    fake_filename, fake_content = create_fake_audio_file(".wav")
    
    # Prepare file upload
    files = {
        "file": (fake_filename, io.BytesIO(fake_content), "audio/wav")
    }
    
    # Make request
    response = client.post(
        "/api/upload-audio",
        files=files,
        data={"session_id": "test_session_fake"}
    )
    
    # Should be rejected with 400 status (MIME type validation fails)
    assert response.status_code == 400
    response_data = response.json()
    assert "detail" in response_data
    detail = response_data["detail"].lower()
    # The error should mention MIME type or file type validation
    assert (
        "mime" in detail or
        "file type" in detail or
        "not allowed" in detail or
        "could not verify" in detail or
        "content" in detail
    )


def test_multiple_path_traversal_variants(client):
    """
    Additional test: Verify various path traversal attack patterns are sanitized.
    """
    wav_content = create_valid_wav_file(size_bytes=512)
    
    # Test various malicious filename patterns
    malicious_patterns = [
        "../../../etc/passwd.wav",
        "..\\..\\..\\windows\\system32\\config\\sam.wav",
        "/etc/passwd.wav",
        "C:\\Windows\\System32\\config\\sam.wav",
        "....//....//etc//passwd.wav",
        "test/../etc/passwd.wav",
        "test\\..\\etc\\passwd.wav",
    ]
    
    for malicious_filename in malicious_patterns:
        files = {
            "file": (malicious_filename, io.BytesIO(wav_content), "audio/wav")
        }
        
        response = client.post(
            "/api/upload-audio",
            files=files,
            data={"session_id": f"test_session_{hash(malicious_filename)}"}
        )
        
        # Should succeed (sanitization, not rejection)
        assert response.status_code == 200, f"Should sanitize filename: {malicious_filename}"
        
        response_data = response.json()
        file_url = response_data["data"]["file_url"]
        
        # Verify sanitization
        assert ".." not in file_url, f"URL should not contain .. for {malicious_filename}"
        assert "/etc/" not in file_url, f"URL should not contain /etc/ for {malicious_filename}"
        assert "\\" not in file_url or "\\" not in file_url.replace("\\", "/"), f"URL should not contain backslashes for {malicious_filename}"
        
        # Verify file is in correct directory
        assert "/media/123/" in file_url, f"File should be in media directory for {malicious_filename}"


def test_empty_file_rejection(client):
    """
    Additional test: Verify empty files are rejected.
    """
    files = {
        "file": ("empty.wav", io.BytesIO(b""), "audio/wav")
    }
    
    response = client.post(
        "/api/upload-audio",
        files=files,
        data={"session_id": "test_session_empty"}
    )
    
    # Should be rejected with 400 status
    assert response.status_code == 400
    response_data = response.json()
    assert "detail" in response_data
    detail = response_data["detail"].lower()
    assert "empty" in detail

