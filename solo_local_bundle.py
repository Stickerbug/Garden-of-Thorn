# -*- coding: utf-8 -*-
"""Build the self-contained Python bundle used by the browser solo worker."""

from __future__ import annotations

import ast
import hashlib
import io
from pathlib import Path
import threading
import zipfile


ROOT = Path(__file__).resolve().parent
_CACHE = {'key': None, 'payload': None}
_CACHE_LOCK = threading.Lock()


def _python_dependencies():
    root_files = {path.name: path for path in ROOT.glob('*.py')}
    pending = ['solo_local_runner.py']
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen or name not in root_files:
            continue
        seen.add(name)
        source = root_files[name].read_text(encoding='utf-8')
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            imported = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module in imported:
                candidate = module.split('.', 1)[0] + '.py'
                if candidate in root_files and candidate not in seen:
                    pending.append(candidate)
    return sorted(seen)


def _cache_key(disabled_card_ids, disabled_mod_files):
    digest = hashlib.sha256()
    for name in [*_python_dependencies(), 'solo_local_bundle.py']:
        path = ROOT / name
        digest.update(name.encode('utf-8'))
        digest.update(path.read_bytes())
    for mod_path in sorted((ROOT / 'mods').glob('*')):
        if mod_path.suffix.lower() not in ('.json', '.gtnmod'):
            continue
        stat = mod_path.stat()
        digest.update(f'{mod_path.name}:{stat.st_mtime_ns}:{stat.st_size}'.encode('utf-8'))
    digest.update(repr(sorted(set(disabled_card_ids))).encode('utf-8'))
    digest.update(repr(sorted(set(disabled_mod_files))).encode('utf-8'))
    return digest.hexdigest()


def runtime_bundle(disabled_card_ids=(), disabled_mod_files=()):
    key = _cache_key(disabled_card_ids, disabled_mod_files)
    with _CACHE_LOCK:
        if _CACHE['key'] == key and _CACHE['payload'] is not None:
            return _CACHE['payload']
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in _python_dependencies():
                archive.write(ROOT / name, arcname=name)
            import json
            manifest = {
                'format': 1,
                'disabled_card_ids': sorted(set(disabled_card_ids)),
                'disabled_mod_files': sorted(set(disabled_mod_files)),
            }
            archive.writestr('solo_local_manifest.json', json.dumps(manifest, ensure_ascii=False, separators=(',', ':')))
            for mod_path in sorted((ROOT / 'mods').glob('*')):
                if mod_path.suffix.lower() in ('.json', '.gtnmod'):
                    archive.write(mod_path, arcname=f'mods/{mod_path.name}')
        payload = (buffer.getvalue(), key)
        _CACHE['key'] = key
        _CACHE['payload'] = payload
        return payload
