#!/usr/bin/env python3
"""Check paired documentation sources, examples, headings, and local links (stdlib only)."""
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'references/zh-CN/translation-sources.json'
FENCES = re.compile(r'^```[^\n]*\n.*?^```', re.M | re.S)
LINKS = re.compile(r'!?\[[^\]\n]*\]\(([^\s)]+)\)')
errors = []


def slug(heading):
    # GitHub retains letters, numbers, marks, underscores and hyphens.
    plain = heading.lower().replace('`', '')
    return ''.join(c for c in plain if c in '_- ' or unicodedata.category(c)[0] in 'LNM').replace(' ', '-')


def anchors(text):
    text = FENCES.sub('', text)
    result = set(re.findall(r'<a\s+id="([^"]+)"', text))
    counts = {}
    for heading in re.findall(r'^#{1,6} (.+)$', text, re.M):
        key = slug(heading)
        count = counts.get(key, 0)
        result.add(key if count == 0 else f'{key}-{count}')
        counts[key] = count + 1
    return result


manifest = json.loads(MANIFEST.read_text())
for entry in manifest['files']:
    source, target = ROOT / entry['source'], ROOT / entry['translation']
    if not source.is_file() or not target.is_file():
        errors.append(f'Missing pair: {source} -> {target}')
        continue
    if hashlib.sha256(source.read_bytes()).hexdigest() != entry['source_sha256']:
        errors.append(f'English source changed; review translation: {entry["source"]}')
    en, zh = source.read_text(), target.read_text()
    if source.suffix == '.md':
        if FENCES.findall(en) != FENCES.findall(zh):
            errors.append(f'Code blocks differ: {entry["translation"]}')
        en_headings = re.findall(r'^#{2,6} (.+)$', FENCES.sub('', en), re.M)
        zh_headings = re.findall(r'^#{2,6} (.+)$', FENCES.sub('', zh), re.M)
        if len(en_headings) != len(zh_headings):
            errors.append(f'Section count differs: {entry["translation"]}')
        missing = {slug(h) for h in en_headings} - anchors(zh)
        if missing:
            errors.append(f'Missing stable anchors in {entry["translation"]}: {sorted(missing)}')
    elif source.suffix == '.svg':
        try:
            a, b = ET.fromstring(en), ET.fromstring(zh)
            ns = {'svg': 'http://www.w3.org/2000/svg'}
            if len(a.findall('.//svg:text', ns)) != len(b.findall('.//svg:text', ns)):
                errors.append(f'SVG label count differs: {entry["translation"]}')
            if b.get('{http://www.w3.org/XML/1998/namespace}lang') != 'zh-CN':
                errors.append(f'SVG language missing: {entry["translation"]}')
        except ET.ParseError as exc:
            errors.append(f'Invalid SVG: {entry["translation"]}: {exc}')

for path in [ROOT / 'README.md', ROOT / 'README.zh-CN.md', ROOT / 'SKILL.md', *sorted((ROOT / 'references').rglob('*.md'))]:
    text = FENCES.sub('', path.read_text())
    for link in LINKS.findall(text):
        parts = urlsplit(link)
        if parts.scheme or parts.netloc:
            continue
        target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
        if not target.exists():
            errors.append(f'Broken link in {path.relative_to(ROOT)}: {link}')
        elif parts.fragment and target.suffix == '.md' and unquote(parts.fragment) not in anchors(target.read_text()):
            errors.append(f'Broken anchor in {path.relative_to(ROOT)}: {link}')

if errors:
    print('\n'.join(errors), file=sys.stderr)
    sys.exit(1)
print(f'OK: {len(manifest["files"])} translation pairs; source hashes, code blocks, sections, SVG labels and local links.')
