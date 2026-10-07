#!/usr/bin/env python3
"""将 SVG 图表的中性色转换为深色主题，保留彩色数据标记。

用法：python3 darken_figures.py --input assets/figures --output assets/dark
仅处理 SVG；不会覆盖原图。复杂渐变、嵌入图片与外部样式需人工检查。
"""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

PALETTE = {
    '#ffffff': '#111111', '#fff': '#111111', 'white': '#111111',
    '#000000': '#f0ece5', '#000': '#f0ece5', 'black': '#f0ece5',
    '#111111': '#f0ece5', '#222222': '#f0ece5', '#333333': '#f0ece5',
    '#444444': '#f0ece5', '#555555': '#b8b8b0', '#666666': '#b8b8b0',
    '#777777': '#b8b8b0', '#888888': '#b8b8b0',
    '#eeeeee': '#282826', '#eee': '#282826', '#f5f5f5': '#282826',
    '#f8f8f8': '#282826', '#fafafa': '#282826',
    '#dddddd': '#505048', '#ddd': '#505048', '#cccccc': '#505048', '#ccc': '#505048',
}
COLOR = re.compile(r'(?<![\w-])(#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|white\b|black\b)', re.I)


def recolor(value, palette=PALETTE):
    return COLOR.sub(lambda m: palette.get(m[0].lower(), m[0]), value)


def convert(source, dest):
    tree = ET.parse(source)
    root = tree.getroot()
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        raise ValueError(f'not an SVG: {source}')
    for node in root.iter():
        for attr in ('fill', 'stroke', 'color', 'stop-color', 'style'):
            if attr in node.attrib:
                node.set(attr, recolor(node.get(attr)))
        if node.tag.rsplit('}', 1)[-1] == 'style' and node.text:
            # Only replace paint declaration values; leave selectors and URLs intact.
            node.text = re.sub(r'((?:fill|stroke|color|stop-color)\s*:)\s*([^;}]+)',
                               lambda m: m[1] + recolor(m[2]), node.text)
    if 'fill' not in root.attrib:
        root.set('fill', '#f0ece5')  # SVG's implicit black fill must also become readable.
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_suffix(dest.suffix + '.tmp')
    tree.write(temporary, encoding='utf-8', xml_declaration=True)
    temporary.replace(dest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='输出目录')
    a = parser.parse_args()
    source, output = a.input.resolve(), a.output.resolve()
    if not source.exists():
        parser.error(f'input not found: {source}')
    if source == output or (source.is_dir() and source in output.parents):
        parser.error('output must be separate from the input directory')
    files = [source] if source.is_file() else sorted(source.rglob('*.svg'))
    if not files or any(p.suffix.lower() != '.svg' for p in files):
        parser.error('input must contain SVG files')
    for path in files:
        relative = path.name if source.is_file() else path.relative_to(source)
        dest = output / relative
        if dest.resolve() == path.resolve():
            parser.error('refusing to overwrite the source')
        convert(path, dest)
        print(f'{path} → {dest}')


if __name__ == '__main__':
    main()
