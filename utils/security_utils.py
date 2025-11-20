"""
Security utilities for file upload validation and sanitization
"""
import re
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, UploadFile


# Security constants
ALLOWED_MIME_TYPES = [
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mpeg3",
    "audio/x-mpeg-3",
    "audio/aiff",
    "audio/x-aiff",
]

ALLOWED_EXTENSIONS = [".wav", ".mp3", ".aiff", ".wave"]

# 50MB in bytes
MAX_FILE_SIZE = 50 * 1024 * 1024


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    
    Removes:
    - Directory separators (/ and \)
    - Path traversal sequences (..)
    - Null bytes (\x00)
    - Any other potentially dangerous characters
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for use in file paths
    """
    if not filename:
        raise ValueError("Filename cannot be empty")
    
    # Remove null bytes
    filename = filename.replace("\x00", "")
    
    # Remove directory separators
    filename = filename.replace("/", "").replace("\\", "")
    
    # Remove path traversal sequences
    while ".." in filename:
        filename = filename.replace("..", "")
    
    # Remove any remaining dangerous characters (keep alphanumeric, dots, hyphens, underscores)
    # This regex keeps: letters, numbers, dots, hyphens, underscores, and spaces
    filename = re.sub(r'[^a-zA-Z0-9._\-\s]', '', filename)
    
    # Remove leading/trailing dots and spaces (Windows doesn't allow these)
    filename = filename.strip('. ')
    
    # Ensure filename is not empty after sanitization
    if not filename:
        raise ValueError("Filename is invalid after sanitization")
    
    # Limit filename length (Windows has 255 char limit, but we'll be more conservative)
    if len(filename) > 200:
        # Keep extension if present
        ext = Path(filename).suffix
        name_without_ext = Path(filename).stem[:200 - len(ext)]
        filename = name_without_ext + ext
    
    return filename


def get_file_extension(filename: str) -> str:
    """
    Extract file extension from filename (lowercase).
    
    Args:
        filename: Filename
        
    Returns:
        File extension with leading dot (e.g., ".wav") or empty string
    """
    return Path(filename).suffix.lower()


def validate_file_extension(filename: str) -> None:
    """
    Validate that file extension is in the whitelist.
    
    Args:
        filename: Filename to validate
        
    Raises:
        HTTPException: If extension is not allowed
    """
    ext = get_file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' is not allowed. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}"
        )


def detect_mime_type_from_content(content: bytes) -> Optional[str]:
    """
    Detect MIME type from file content using magic bytes.
    
    This is a fallback method that checks file signatures.
    For more accurate detection, python-magic should be used if available.
    
    Args:
        content: File content bytes
        
    Returns:
        Detected MIME type or None if unknown
    """
    if not content:
        return None
    
    # Check file signatures (magic bytes)
    # WAV: RIFF...WAVE
    if content[:4] == b'RIFF' and len(content) > 8 and content[8:12] == b'WAVE':
        return "audio/wav"
    
    # MP3: ID3 tag or MPEG frame sync
    if content[:3] == b'ID3' or (len(content) > 2 and content[:2] == b'\xff\xfb'):
        return "audio/mpeg"
    
    # AIFF: FORM...AIFF
    if content[:4] == b'FORM' and len(content) > 8 and content[8:12] == b'AIFF':
        return "audio/aiff"
    
    # Try python-magic if available
    try:
        import magic
        mime = magic.from_buffer(content, mime=True)
        if mime and mime.startswith('audio/'):
            return mime
    except ImportError:
        pass
    
    return None


def validate_file_content(content: bytes, filename: str) -> None:
    """
    Validate file content (MIME type and size).
    
    Args:
        content: File content bytes
        filename: Original filename for error messages
        
    Raises:
        HTTPException: If validation fails
    """
    # Check file size
    if len(content) > MAX_FILE_SIZE:
        size_mb = len(content) / (1024 * 1024)
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File size ({size_mb:.2f}MB) exceeds maximum allowed size ({max_mb}MB)"
        )
    
    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="File is empty"
        )
    
    # Detect MIME type from content
    detected_mime = detect_mime_type_from_content(content)
    
    if detected_mime:
        # Validate detected MIME type
        if detected_mime not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File MIME type '{detected_mime}' is not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
            )
    else:
        # If we can't detect MIME type, at least validate extension
        # This is a fallback - ideally we should always detect MIME type
        ext = get_file_extension(filename)
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Could not verify file type. File extension '{ext}' may not be valid."
            )


async def validate_uploaded_file(file: UploadFile) -> tuple[str, bytes]:
    """
    Comprehensive validation of uploaded file.
    
    This function:
    1. Sanitizes the filename
    2. Validates file extension
    3. Reads and validates file content (size and MIME type)
    
    Args:
        file: FastAPI UploadFile object
        
    Returns:
        Tuple of (sanitized_filename, file_content)
        
    Raises:
        HTTPException: If any validation fails
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    # Sanitize filename
    try:
        sanitized_filename = sanitize_filename(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Validate file extension
    validate_file_extension(sanitized_filename)
    
    # Read file content
    content = await file.read()
    
    # Validate file content (size and MIME type)
    validate_file_content(content, sanitized_filename)
    
    # Reset file pointer for potential reuse
    await file.seek(0)
    
    return sanitized_filename, content


def validate_password_strength(password: str) -> None:
    """
    Validate password strength according to security requirements.
    
    Enforces:
    - Minimum length: 12 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)
    - At least one special character (!@#$%^&*(),.?":{}|<>])
    
    Args:
        password: Password string to validate
        
    Raises:
        ValueError: If password does not meet strength requirements
    """
    if not password:
        raise ValueError("Password cannot be empty")
    
    # Check minimum length
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long")
    
    # Check for uppercase letter
    if not re.search(r'[A-Z]', password):
        raise ValueError("Password must contain at least one uppercase letter (A-Z)")
    
    # Check for lowercase letter
    if not re.search(r'[a-z]', password):
        raise ValueError("Password must contain at least one lowercase letter (a-z)")
    
    # Check for digit
    if not re.search(r'[0-9]', password):
        raise ValueError("Password must contain at least one digit (0-9)")
    
    # Check for special character
    if not re.search(r'[!@#$%&*(),.?":{}|<>\[\]^]', password):
        raise ValueError("Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>[])")