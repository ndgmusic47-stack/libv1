import wave
import struct
import numpy as np


def save_wav(path, audio, sr=44100):
    # Ensure stereo
    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=1)

    # Normalize for int16 export
    peak = np.max(np.abs(audio))
    if peak > 1.0:
        audio = audio / peak

    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(path, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(audio_int16.tobytes())

    return path

