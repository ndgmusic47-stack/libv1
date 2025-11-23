from models.mix_config import MixConfig, MasterConfig, EQBand, CompressorSettings


MIX_RECIPES = {
    "default": MixConfig(
        master=MasterConfig(
            eq=[EQBand(freq=20000, gain=0, q=1)],
            compressor=CompressorSettings(
                threshold=-10,
                ratio=2.5,
                attack=30,
                release=120,
                makeup=2,
            ),
            limiter_threshold=-1.0,
            output_gain=0.0,
        )
    ),
    "modern_clean": MixConfig(
        master=MasterConfig(
            eq=[
                EQBand(freq=60, gain=1, q=1),
                EQBand(freq=8000, gain=1, q=0.7),
            ],
            compressor=CompressorSettings(
                threshold=-12,
                ratio=3,
                attack=20,
                release=80,
                makeup=2,
            ),
            limiter_threshold=-0.8,
            output_gain=0.5,
        )
    ),
}

