from models.mix_config import MixConfig, TrackConfig
from utils.mix.role_presets import ROLE_PRESETS
from utils.mix.mix_recipes import MIX_RECIPES


def apply_recipe(recipe_name: str, track_roles: dict):
    recipe = MIX_RECIPES.get(recipe_name, MIX_RECIPES["default"])

    final_tracks = {}

    for track_id, role in track_roles.items():
        preset = ROLE_PRESETS.get(role)
        if preset:
            final_tracks[track_id] = preset
        else:
            final_tracks[track_id] = TrackConfig(role=role)

    return MixConfig(
        tracks=final_tracks,
        master=recipe.master,
    )

