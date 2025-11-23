import numpy as np
import wave
import struct


def load_wav(path, target_sr=44100):
    with wave.open(path, "rb") as wav:
        channels = wav.getnchannels()
        sr = wav.getframerate()
        frames = wav.getnframes()
        audio = wav.readframes(frames)
        samples = struct.unpack("<" + ("h" * frames * channels), audio)
        audio_np = np.array(samples, dtype=np.float32) / 32768.0

        if channels == 2:
            audio_np = audio_np.reshape(-1, 2)
        else:
            audio_np = np.stack([audio_np, audio_np], axis=1)

    # Resample if needed
    if sr != target_sr:
        ratio = target_sr / sr
        new_length = int(audio_np.shape[0] * ratio)
        indices = np.linspace(0, audio_np.shape[0]-1, new_length)
        audio_np = audio_np[indices.astype(np.int32)]

    return audio_np

