"""Minimal canary module for packaging/installation tests."""

def greet(name: str = "world") -> str:
    return f"hello, {name}!"

if __name__ == "__main__":
    print(greet())
