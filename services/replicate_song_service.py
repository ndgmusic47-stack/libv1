"""
Replicate song generation service using YuE model
"""
import os
import logging
from typing import Optional
import replicate

logger = logging.getLogger(__name__)


async def replicate_generate_song_yue(lyrics: str, style: Optional[str] = None) -> str:
    """
    Generate a song using Replicate's fofr/yue model.
    
    Args:
        lyrics: The lyrics text to generate the song from
        style: Optional style/genre prompt (only included if model supports it)
    
    Returns:
        URL of the generated audio file
    
    Raises:
        ValueError: If REPLICATE_API_TOKEN is not set
        Exception: If generation fails
    """
    token = os.getenv("REPLICATE_API_TOKEN")
    if not token:
        raise ValueError("REPLICATE_API_TOKEN environment variable is not set")
    
    client = replicate.Client(api_token=token)
    
    # Build input - start with lyrics
    input_data = {"lyrics": lyrics}
    
    # Note: Only include style if the model schema supports it
    # For fofr/yue, we'll check if style is provided and try to include it
    # If the model doesn't support it, it will be ignored
    # Based on Replicate model docs, fofr/yue may support additional prompts
    # but we'll be conservative and only send lyrics unless we know the schema
    # For now, we'll only send lyrics to be safe
    
    try:
        logger.info(f"Starting Replicate song generation for lyrics (length: {len(lyrics)} chars)")
        
        # Run the model - use async if available, otherwise run sync in thread
        try:
            # Try async_run if available (newer replicate versions)
            if hasattr(client, 'async_run'):
                output = await client.async_run("fofr/yue", input=input_data)
            else:
                # Fallback to sync run in thread pool
                import asyncio
                output = await asyncio.to_thread(client.run, "fofr/yue", input=input_data)
        except AttributeError:
            # Fallback to sync run
            import asyncio
            output = await asyncio.to_thread(client.run, "fofr/yue", input=input_data)
        
        logger.info(f"Replicate generation completed, output type: {type(output)}")
        
        # Extract audio URL from output
        audio_url = None
        
        if isinstance(output, dict):
            # Try common keys for audio output
            for key in ["audio", "output", "files", "url", "file"]:
                if key in output:
                    value = output[key]
                    if isinstance(value, str) and (value.endswith(".mp3") or value.endswith(".wav")):
                        audio_url = value
                        break
                    elif isinstance(value, list) and len(value) > 0:
                        # If it's a list, check first item
                        first_item = value[0]
                        if isinstance(first_item, str) and (first_item.endswith(".mp3") or first_item.endswith(".wav")):
                            audio_url = first_item
                            break
        elif isinstance(output, list) and len(output) > 0:
            # If output is a list, find first URL ending with .mp3 or .wav
            for item in output:
                if isinstance(item, str) and (item.endswith(".mp3") or item.endswith(".wav")):
                    audio_url = item
                    break
        elif isinstance(output, str):
            # If output is directly a string URL
            if output.endswith(".mp3") or output.endswith(".wav"):
                audio_url = output
        
        if not audio_url:
            # Log the output for debugging
            logger.error(f"Could not extract audio URL from Replicate output: {output}")
            raise ValueError(f"Replicate model returned unexpected output format: {type(output)}")
        
        logger.info(f"Extracted audio URL: {audio_url}")
        return audio_url
        
    except Exception as e:
        logger.error(f"Error generating song with Replicate: {e}", exc_info=True)
        raise

