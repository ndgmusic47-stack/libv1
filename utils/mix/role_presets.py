from models.mix_config import TrackConfig, EQBand, CompressorSettings, SaturationSettings


ROLE_PRESETS = {
    "lead_vocal": TrackConfig(
        role="lead_vocal",
        gain=-3.0,
        hp_filter=120,
        eq=[
            EQBand(freq=200, gain=-2, q=1.2),
            EQBand(freq=3500, gain=3, q=1.5),
        ],
        compressor=CompressorSettings(
            threshold=-12,
            ratio=3.5,
            attack=5,
            release=60,
            makeup=3,
        ),
        saturation=SaturationSettings(drive=0.2, mix=0.7),
        width=1.1,
    ),
    "adlib": TrackConfig(
        role="adlib",
        gain=-6.0,
        hp_filter=150,
        eq=[
            EQBand(freq=5000, gain=4, q=1.2),
        ],
        compressor=CompressorSettings(
            threshold=-15,
            ratio=2.5,
            attack=10,
            release=50,
            makeup=2,
        ),
        width=1.3,
    ),
    "beat": TrackConfig(
        role="beat",
        gain=-5.0,
        eq=[],
        width=1.0,
    ),
    "bass": TrackConfig(
        role="bass",
        gain=-4.0,
        hp_filter=None,
        eq=[
            EQBand(freq=60, gain=2, q=1.0),
            EQBand(freq=200, gain=-3, q=1.1),
        ],
        compressor=CompressorSettings(
            threshold=-18,
            ratio=4,
            attack=20,
            release=80,
            makeup=4,
        ),
    ),
}

