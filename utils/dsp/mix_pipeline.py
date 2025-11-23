from .eq import apply_eq
from .compressor import apply_compressor
from .saturator import apply_saturation
from .limiter import apply_limiter
from .gain import apply_gain
from utils.dsp.deesser import apply_deesser
from utils.dsp.air import add_air
from utils.dsp.stereo import stereo_widen
from utils.mix.roles import detect_role
from utils.mix.presets import ROLE_PRESETS
from utils.dsp.metering import compute_gain_reduction
from utils.dsp.scope import compute_scope
import numpy as np


def match_loudness(audio, target_rms=-20.0):
    rms = np.sqrt(np.mean(audio**2))
    if rms < 1e-9:
        return audio
    target_linear = 10 ** (target_rms / 20)
    return audio * (target_linear / rms)


def align_tracks(tracks):
    max_len = max([t.shape[0] for t in tracks])
    aligned = []
    for t in tracks:
        if t.shape[0] < max_len:
            pad = np.zeros((max_len - t.shape[0], t.shape[1]))
            aligned.append(np.concatenate([t, pad], axis=0))
        else:
            aligned.append(t[:max_len])
    return aligned


def process_track(audio_data, config):
    role = config.get("role", "unknown")
    preset = ROLE_PRESETS.get(role, ROLE_PRESETS["unknown"])

    # Merge preset with user-config (preset wins unless user overrides)
    merged = {
        "eq": config.get("eq", preset["eq"]),
        "compressor": config.get("compressor", preset["compressor"]),
        "saturation": config.get("saturation", preset["saturation"]),
        "gain": config.get("gain", preset["gain"])
    }

    config = merged

    eq_settings = config.get("eq", [])
    comp = config.get("compressor", {})
    sat_amount = config.get("saturation", 0.0)
    gain_db = config.get("gain", 0.0)

    processed = audio_data.copy()

    if eq_settings:
        processed = apply_eq(processed, eq_settings)

    if comp:
        audio_in = processed.copy()
        processed = apply_compressor(
            processed,
            threshold=comp.get("threshold", -18),
            ratio=comp.get("ratio", 4.0),
            attack=comp.get("attack", 5),
            release=comp.get("release", 50)
        )
        gr_curve = compute_gain_reduction(audio_in, processed)
    else:
        gr_curve = []

    processed = apply_saturation(processed, sat_amount)
    processed = apply_gain(processed, gain_db)

    # Apply de-esser for vocals only
    if role in ["lead", "double", "harmony", "adlib"]:
        processed = apply_deesser(processed)
        processed = add_air(processed)

    # Apply stereo widening to backing vocals
    if role in ["double", "harmony"]:
        processed = stereo_widen(processed)

    track_scope = compute_scope(processed)

    return processed, {
        "gr": gr_curve,
        "scope": track_scope
    }


def process_master_bus(mix, cfg):
    mix = apply_eq(mix, cfg.get("eq", []))
    mix = apply_compressor(
        mix,
        threshold=cfg.get("threshold", -14),
        ratio=cfg.get("ratio", 2.0),
        attack=cfg.get("attack", 10),
        release=cfg.get("release", 50)
    )
    audio_in = mix.copy()
    mix = apply_limiter(mix, ceiling=cfg.get("ceiling", -1.0))
    master_gr = compute_gain_reduction(audio_in, mix)
    return mix, {"gr": master_gr}


def blend_tracks(tracks):
    # Use aligned tracks
    tracks = align_tracks(tracks)
    mix = np.sum(tracks, axis=0)
    peak = np.max(np.abs(mix))
    if peak > 1.0:
        mix = mix / peak
    return mix

