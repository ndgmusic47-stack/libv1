from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class EQBand(BaseModel):
    freq: float
    gain: float
    q: float
    type: str = "bell"


class CompressorSettings(BaseModel):
    threshold: float
    ratio: float
    attack: float
    release: float
    makeup: float


class SaturationSettings(BaseModel):
    drive: float = 0.0
    mix: float = 1.0


class TrackConfig(BaseModel):
    role: Optional[str] = None
    gain: float = 0.0
    hp_filter: Optional[float] = None
    eq: List[EQBand] = []
    compressor: Optional[CompressorSettings] = None
    saturation: Optional[SaturationSettings] = None
    width: Optional[float] = None
    pan: Optional[float] = 0.0


class MasterConfig(BaseModel):
    eq: List[EQBand] = []
    compressor: Optional[CompressorSettings] = None
    limiter_threshold: float = -1.0
    output_gain: float = 0.0


class MixConfig(BaseModel):
    tracks: Dict[str, TrackConfig] = Field(default_factory=dict)
    master: MasterConfig = MasterConfig()

