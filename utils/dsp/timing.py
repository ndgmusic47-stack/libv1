"""
Timing utilities for audio stem alignment
"""
import numpy as np


def detect_onset(audio, sample_rate=44100, threshold=0.1):
    """
    Detect the onset (start) of audio content.
    
    Args:
        audio: numpy array of audio samples (can be mono or stereo)
        sample_rate: Sample rate in Hz
        threshold: Energy threshold for onset detection (0.0 to 1.0)
        
    Returns:
        Sample index where onset is detected
    """
    # Convert to mono if stereo
    if audio.ndim == 2:
        mono = audio.mean(axis=1)
    else:
        mono = audio
    
    # Normalize
    max_val = np.max(np.abs(mono))
    if max_val == 0:
        return 0
    mono = mono / max_val
    
    # Use a sliding window to find where energy crosses threshold
    window_size = int(sample_rate * 0.01)  # 10ms window
    energy = np.convolve(mono ** 2, np.ones(window_size) / window_size, mode='same')
    
    # Find first point where energy exceeds threshold
    onset_idx = np.where(energy > threshold)[0]
    if len(onset_idx) > 0:
        return int(onset_idx[0])
    
    return 0


def align_stems(audio_data_dict: dict, sample_rate: int = 44100) -> dict:
    """
    Align stems by detecting onset differences and synchronizing vocal to beat.
    
    This function detects the onset difference between "beat" and "vocal" stems
    and shifts/pads the vocal stem to synchronize it with the beat.
    
    Args:
        audio_data_dict: Dictionary mapping stem names to audio arrays
            e.g., {"vocal": np.array(...), "beat": np.array(...)}
        sample_rate: Sample rate in Hz (default: 44100)
        
    Returns:
        Dictionary with aligned audio data (same structure as input)
    """
    if "vocal" not in audio_data_dict or "beat" not in audio_data_dict:
        # If we don't have both stems, return unchanged
        return audio_data_dict
    
    beat_audio = audio_data_dict["beat"]
    vocal_audio = audio_data_dict["vocal"]
    
    # Detect onsets
    beat_onset = detect_onset(beat_audio, sample_rate)
    vocal_onset = detect_onset(vocal_audio, sample_rate)
    
    # Calculate offset (how much to shift vocal)
    offset_samples = beat_onset - vocal_onset
    
    # If offset is positive, we need to pad the vocal at the beginning
    # If offset is negative, we need to trim the vocal at the beginning
    if offset_samples > 0:
        # Pad vocal at the beginning
        if vocal_audio.ndim == 2:
            # Stereo
            padding = np.zeros((offset_samples, 2), dtype=vocal_audio.dtype)
            aligned_vocal = np.vstack([padding, vocal_audio])
        else:
            # Mono
            padding = np.zeros(offset_samples, dtype=vocal_audio.dtype)
            aligned_vocal = np.concatenate([padding, vocal_audio])
    elif offset_samples < 0:
        # Trim vocal at the beginning
        trim_samples = abs(offset_samples)
        if vocal_audio.ndim == 2:
            aligned_vocal = vocal_audio[trim_samples:, :]
        else:
            aligned_vocal = vocal_audio[trim_samples:]
    else:
        # No alignment needed
        aligned_vocal = vocal_audio
    
    # Ensure both stems have the same length (pad shorter one with zeros)
    beat_length = beat_audio.shape[0]
    vocal_length = aligned_vocal.shape[0]
    
    if beat_length > vocal_length:
        # Pad vocal to match beat length
        pad_samples = beat_length - vocal_length
        if aligned_vocal.ndim == 2:
            padding = np.zeros((pad_samples, 2), dtype=aligned_vocal.dtype)
            aligned_vocal = np.vstack([aligned_vocal, padding])
        else:
            padding = np.zeros(pad_samples, dtype=aligned_vocal.dtype)
            aligned_vocal = np.concatenate([aligned_vocal, padding])
    elif vocal_length > beat_length:
        # Pad beat to match vocal length
        pad_samples = vocal_length - beat_length
        if beat_audio.ndim == 2:
            padding = np.zeros((pad_samples, 2), dtype=beat_audio.dtype)
            aligned_beat = np.vstack([beat_audio, padding])
        else:
            padding = np.zeros(pad_samples, dtype=beat_audio.dtype)
            aligned_beat = np.concatenate([beat_audio, padding])
        audio_data_dict["beat"] = aligned_beat
    
    # Update the vocal in the dictionary
    audio_data_dict["vocal"] = aligned_vocal
    
    return audio_data_dict

