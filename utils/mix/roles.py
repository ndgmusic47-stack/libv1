import os


def detect_role(filename: str):
    name = os.path.basename(filename).lower()

    if "lead" in name:
        return "lead"
    if "main" in name:
        return "lead"

    if "double" in name or "dbl" in name:
        return "double"

    if "harm" in name or "harmony" in name:
        return "harmony"

    if "adlib" in name or "ad" in name:
        return "adlib"

    if "beat" in name or "instr" in name:
        return "instrumental"

    return "unknown"

