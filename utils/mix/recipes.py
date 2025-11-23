MIX_RECIPES = {
    "np22_modern_clean": {
        "master": {
            "eq": [
                {"freq": 80, "gain": -2, "q": 1.0},
                {"freq": 12000, "gain": 1, "q": 1.0}
            ],
            "threshold": -14,
            "ratio": 2.0,
            "attack": 10,
            "release": 40,
            "ceiling": -1.0
        }
    },

    "np22_bright_vocal": {
        "master": {
            "eq": [
                {"freq": 10000, "gain": 2, "q": 0.9},
            ],
            "threshold": -16,
            "ratio": 2.5,
            "attack": 8,
            "release": 60,
            "ceiling": -1.0
        }
    },

    "default": {
        "master": {
            "eq": [],
            "threshold": -14,
            "ratio": 2.0,
            "attack": 10,
            "release": 50,
            "ceiling": -1.0
        }
    }
}

