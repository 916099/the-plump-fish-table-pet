"""Generate SHA-256-verified upload parts for the optional HD animation ZIP."""
import argparse
import hashlib
from pathlib import Path

PART_SIZE = 180 * 1024 * 1024

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Built HD animation ZIP")
    parser.add_argument("output", type=Path, help="Directory for the four GitHub upload parts")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with args.archive.open("rb") as source:
        index = 1
        while chunk := source.read(PART_SIZE):
            path = args.output / f"Dafeiyu-Pet-HD-Animations-v1.0.0.part{index:02d}"
            path.write_bytes(chunk)
            print(f"{path.name} {path.stat().st_size} {hashlib.sha256(chunk).hexdigest()}")
            index += 1
    print("parts", index - 1)

if __name__ == "__main__":
    main()
