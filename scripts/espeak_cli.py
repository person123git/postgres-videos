"""Small project-local CLI for the bundled eSpeak NG library and data."""

from __future__ import annotations

import argparse
from pathlib import Path

from phonemizer import phonemize
from phonemizer.backend.espeak.wrapper import EspeakWrapper

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(prog="espeak-ng")
    parser.add_argument("--version", action="version", version="eSpeak NG 1.52.0 (project-local library)")
    parser.add_argument("--language", default="en-us")
    parser.add_argument("text", nargs="+")
    args = parser.parse_args()
    EspeakWrapper.set_library(str(ROOT / ".runtime/lib/libespeak-ng.dylib"))
    EspeakWrapper.set_data_path(str(ROOT / ".runtime/share/espeak-ng-data"))
    print(phonemize(" ".join(args.text), language=args.language, backend="espeak", strip=True))


if __name__ == "__main__":
    main()
