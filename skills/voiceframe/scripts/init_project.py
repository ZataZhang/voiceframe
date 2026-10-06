#!/usr/bin/env python3
"""Copy the bundled starter to a new directory without overwriting files."""
import argparse
from pathlib import Path
import shutil


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('destination', type=Path)
    p.add_argument('--adapter', choices=['hyperframes'], help='Optional application-specific starter')
    a = p.parse_args()
    source = Path(__file__).resolve().parents[1] / 'assets/project'
    if a.destination.exists():
        p.error('Destination exists; choose a new directory')
    shutil.copytree(source, a.destination)
    if a.adapter:
        adapter = source.parent / 'adapters' / a.adapter
        shutil.copytree(adapter, a.destination, dirs_exist_ok=True)
    print(a.destination.resolve())


if __name__ == '__main__':
    main()
