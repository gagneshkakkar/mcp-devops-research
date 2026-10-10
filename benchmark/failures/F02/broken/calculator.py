def divide(a: float, b: float) -> float:
    """Return the division of two numbers."""
    if b == 0:
        raise ValueError("Cannot divide by zero")

    return a * b