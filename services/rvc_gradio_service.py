"""
RVC Gradio Service for voice conversion using Gradio client
"""
import os
import logging
import asyncio
import shutil
from pathlib import Path
from typing import Tuple, Optional
import httpx
import aiofiles
from gradio_client import Client

from config.settings import settings

logger = logging.getLogger(__name__)


class RvcGradioService:
    """Service for RVC voice conversion using Gradio client"""
    
    def __init__(self, gradio_url: Optional[str] = None):
        """
        Initialize RVC Gradio service
        
        Args:
            gradio_url: Gradio server URL (defaults to RVC_GRADIO_URL from settings)
        """
        self.gradio_url = gradio_url or settings.rvc_gradio_url
        if not self.gradio_url:
            raise RuntimeError("RVC_GRADIO_URL not set.")
        self.client = None
        self._client_initialized = False
        self._preflight_ok = False
        self._preflight_lock = asyncio.Lock()
    
    async def _ensure_client(self):
        """Initialize Gradio client if not already initialized"""
        async with self._preflight_lock:
            if not self._client_initialized:
                # Perform preflight check before creating Client
                if not self._preflight_ok:
                    await self._preflight_check()
                
                try:
                    # Initialize client in thread pool (gradio_client is sync)
                    self.client = await asyncio.to_thread(Client, self.gradio_url)
                    self._client_initialized = True
                    logger.info(f"Gradio client initialized for {self.gradio_url}")
                except Exception as e:
                    logger.error(f"Failed to initialize Gradio client: {e}", exc_info=True)
                    raise
    
    async def _preflight_check(self):
        """Check if Gradio endpoint is reachable by requesting /config"""
        config_url = f"{self.gradio_url.rstrip('/')}/config"
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                response = await client.get(config_url)
                
                if response.status_code != 200:
                    # Log error with details
                    response_text = response.text[:200] if response.text else "(empty response)"
                    logger.error(
                        f"RVC Gradio preflight check failed: "
                        f"base_url={self.gradio_url}, "
                        f"status_code={response.status_code}, "
                        f"response_text={response_text}"
                    )
                    raise RuntimeError(
                        f"RVC service misconfigured: Gradio endpoint not reachable at {self.gradio_url} (expected /config)."
                    )
                
                self._preflight_ok = True
                logger.info(f"RVC Gradio preflight check passed for {self.gradio_url}")
        except httpx.TimeoutException:
            logger.error(
                f"RVC Gradio preflight check timeout: base_url={self.gradio_url}"
            )
            raise RuntimeError(
                f"RVC service misconfigured: Gradio endpoint timeout at {self.gradio_url} (expected /config)."
            )
        except httpx.RequestError as e:
            logger.error(
                f"RVC Gradio preflight check request error: base_url={self.gradio_url}, error={e}"
            )
            raise RuntimeError(
                f"RVC service misconfigured: Gradio endpoint not reachable at {self.gradio_url} (expected /config)."
            )
        except RuntimeError:
            # Re-raise our custom RuntimeError
            raise
    
    async def upload_audio(self, local_path: Path) -> str:
        """
        Upload audio file to Gradio server and get server-side path string
        
        Args:
            local_path: Local file path to upload
            
        Returns:
            Server-side path string suitable for textbox input
        """
        await self._ensure_client()
        
        if not local_path.exists():
            raise FileNotFoundError(f"Audio file not found: {local_path}")
        
        try:
            # Upload file using gradio_client
            # The upload_file method returns a server-side file path string or FileData object
            # Wrap in timeout (300s as specified)
            upload_result = await asyncio.wait_for(
                asyncio.to_thread(self.client.upload_file, str(local_path)),
                timeout=300.0
            )
            
            # Handle both string and FileData object responses
            if hasattr(upload_result, 'path'):
                server_path = upload_result.path
            elif isinstance(upload_result, str):
                server_path = upload_result
            else:
                # Try to get path attribute or convert to string
                server_path = str(upload_result)
            
            if not server_path:
                raise ValueError("Gradio upload returned empty path")
            
            logger.info(f"Audio uploaded to Gradio: {server_path}")
            return server_path
            
        except Exception as e:
            logger.error(f"Failed to upload audio to Gradio: {e}", exc_info=True)
            raise
    
    async def convert(
        self,
        server_audio_path: str,
        speaker_id: int = 0,
        transpose: float = 0.0,
        f0_curve_file: Optional[str] = None,
        pitch_algo: str = "pm",
        index_path: str = "",
        index_dropdown: str = "",
        search_ratio: float = 0.75,
        median_filter: int = 3,
        resample_sr: int = 0,
        volume_scale: float = 0.25,
        protect_ratio: float = 0.33,
    ) -> Tuple[str, str]:
        """
        Convert audio using RVC with specified parameters
        
        Args:
            server_audio_path: Server-side audio path string (from upload_audio)
            speaker_id: Speaker ID (default 0)
            transpose: Pitch transpose in semitones (default 0)
            f0_curve_file: F0 curve file path (default None)
            pitch_algo: Pitch algorithm (default "pm")
            index_path: Index file path (default "")
            index_dropdown: Index dropdown selection (default "")
            search_ratio: Search ratio (default 0.75)
            median_filter: Median filter size (default 3)
            resample_sr: Resample sample rate (default 0)
            volume_scale: Volume scale (default 0.25)
            protect_ratio: Protect ratio (default 0.33)
            
        Returns:
            Tuple of (info_text, output_audio_path_or_url)
        """
        await self._ensure_client()
        
        try:
            # Call predict by fn_index=2 with exact parameter order
            # fn_index=2 is the main convert function
            # api_name=None means we call by fn_index
            # Wrap in timeout (300s as specified)
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.predict,
                    speaker_id,              # param 0
                    server_audio_path,       # param 1 (textbox - server path string)
                    transpose,               # param 2
                    f0_curve_file,           # param 3
                    pitch_algo,              # param 4
                    index_path,              # param 5
                    index_dropdown,          # param 6
                    search_ratio,            # param 7
                    median_filter,           # param 8
                    resample_sr,             # param 9
                    volume_scale,            # param 10
                    protect_ratio,           # param 11
                    fn_index=2,
                    api_name=None
                ),
                timeout=300.0
            )
            
            # Result is typically a tuple/list with [info_text, output_audio_path]
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                info_text = result[0] if result[0] else ""
                output_audio = result[1] if result[1] else ""
            elif isinstance(result, (list, tuple)) and len(result) == 1:
                # Sometimes only one output
                output_audio = result[0] if result[0] else ""
                info_text = ""
            else:
                # Single value
                output_audio = result if result else ""
                info_text = ""
            
            logger.info(f"RVC conversion completed. Info: {info_text}, Output: {output_audio}")
            return info_text, output_audio
            
        except Exception as e:
            logger.error(f"RVC conversion failed: {e}", exc_info=True)
            raise
    
    async def download_output(self, output_ref: str, dest_path: Path) -> Path:
        """
        Download output audio from Gradio to local destination
        
        Args:
            output_ref: Output reference from convert() (can be URL or local temp path)
            dest_path: Local destination path
            
        Returns:
            Path to downloaded file
        """
        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if output_ref is a URL or local path
        if output_ref.startswith("http://") or output_ref.startswith("https://"):
            # Download from URL
            logger.info(f"Downloading output from URL: {output_ref}")
            async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
                response = await client.get(output_ref)
                response.raise_for_status()
                
                async with aiofiles.open(dest_path, "wb") as f:
                    await f.write(response.content)
            
            logger.info(f"Downloaded output to: {dest_path}")
        else:
            # Assume it's a file path reference from Gradio server
            # Gradio serves files via /file= endpoint
            # Extract filename from path if it's a full path
            file_name = output_ref
            if "/" in output_ref:
                file_name = output_ref.split("/")[-1]
            
            # Construct Gradio file download URL
            # Format: {gradio_url}/file={filename}
            download_url = f"{self.gradio_url.rstrip('/')}/file={file_name}"
            
            try:
                logger.info(f"Downloading output from Gradio: {download_url}")
                async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
                    response = await client.get(download_url)
                    response.raise_for_status()
                    
                    async with aiofiles.open(dest_path, "wb") as f:
                        await f.write(response.content)
                
                logger.info(f"Downloaded output to: {dest_path}")
            except Exception as e:
                # Fallback: try using gradio_client's download method if available
                logger.warning(f"Direct download failed, trying gradio_client download: {e}")
                try:
                    await self._ensure_client()
                    if hasattr(self.client, 'download'):
                        downloaded_path = await asyncio.to_thread(
                            self.client.download,
                            output_ref,
                            dest_path
                        )
                        if downloaded_path and Path(downloaded_path).exists():
                            # If download returns a different path, copy it
                            if str(downloaded_path) != str(dest_path):
                                shutil.copy2(downloaded_path, dest_path)
                            logger.info(f"Downloaded via gradio_client to: {dest_path}")
                        else:
                            raise ValueError("gradio_client download returned invalid path")
                    else:
                        raise ValueError("gradio_client does not support download method")
                except Exception as e2:
                    logger.error(f"All download methods failed: {e2}", exc_info=True)
                    raise
        
        return dest_path

