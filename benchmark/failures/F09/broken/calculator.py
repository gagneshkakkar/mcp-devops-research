import sys


def get_runtime_label() -> str:
    if sys.version_info >= (3, 12):
        raise RuntimeError("Simulated runtime incompatibility")

    return "compatible"