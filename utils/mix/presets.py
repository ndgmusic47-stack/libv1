ROLE_PRESETS = {
    "lead": {
        "eq": [
            {"freq": 120, "gain": -3, "q": 1.1},
            {"freq": 3000, "gain": 2, "q": 1.0}
        ],
        "compressor": {"threshold": -18, "ratio": 4, "attack": 5, "release": 50},
        "saturation": 0.2,
        "gain": 0
    },

    "double": {
        "eq": [
            {"freq": 150, "gain": -2, "q": 1.1},
            {"freq": 5000, "gain": 1, "q": 1.0}
        ],
        "compressor": {"threshold": -20, "ratio": 3, "attack": 8, "release": 80},
        "saturation": 0.15,
        "gain": -3
    },

    "harmony": {
        "eq": [
            {"freq": 200, "gain": -3, "q": 1.0},
            {"freq": 4500, "gain": 2, "q": 1.0}
        ],
        "compressor": {"threshold": -16, "ratio": 2.5, "attack": 10, "release": 80},
        "saturation": 0.1,
        "gain": -2
    },

    "adlib": {
        "eq": [
            {"freq": 250, "gain": -4, "q": 1.2},
            {"freq": 6000, "gain": 3, "q": 1.0}
        ],
        "compressor": {"threshold": -12, "ratio": 4, "attack": 5, "release": 50},
        "saturation": 0.3,
        "gain": 1
    },

    "instrumental": {
        "eq": [],
        "compressor": {},
        "saturation": 0.0,
        "gain": 0
    },

    "unknown": {
        "eq": [],
        "compressor": {},
        "saturation": 0.0,
        "gain": 0
    }
}

