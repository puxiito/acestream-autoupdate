#!/usr/bin/env python3
"""
update_m3u.py
Busca enlaces (p.ej. acestream://) en páginas web y actualiza una lista M3U.

Configúralo en channels.yaml. Se puede ejecutar localmente o en GitHub Actions.
"""
from __future__ import annotations
import re
import sys
import time
import random
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
import yaml

# --- Ajustes de rutas ---
REPO_ROOT = Path(__file__).resolve().parents[1]
M3U_PATH = REPO_ROOT / "lista-horus-ace.m3u8"
CONFIG_PATH = REPO_ROOT / "channels.yaml"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

ACESTREAM_REGEX = re.compile(r"acestream://[0-9a-fA-F]{40}")
HEX40_REGEX = re.compile(r"[0-9a-fA-F]{40}$")

@dataclass
class Channel:
    name: str
    source_url: Optional[str] = None
    fixed_url: Optional[str] = None
    regex: Optional[str] = None
    selector: Optional[str] = None
    attr: Optional[str] = None
    inner_regex: Optional[str] = None
    attrs: Optional[Dict[str, str]] = None  # atributos EXTINF (tvg-logo, group-title, etc.)

def load_config(path: Path) -> List[Channel]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    channels = []
    for item in data.get("channels", []):
        channels.append(Channel(
            name=item["name"],
            source_url=item.get("source_url"),
            fixed_url=item.get("fixed_url"),
            regex=item.get("regex"),
            selector=item.get("selector"),
            attr=item.get("attr"),
            inner_regex=item.get("inner_regex"),
            attrs=item.get("attrs"),
        ))
    return channels

def parse_m3u(path: Path) -> List[Tuple[str, str, Dict[str, str]]]:
    """
    Devuelve lista [(name, url, attrs_dict)]
    """
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    entries = []
    i = 0
    current_name = None
    current_attrs: Dict[str, str] = {}
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            # Formato: #EXTINF:-1 key="val" key2="val2", Nombre
            # Extrae atributos
            attr_part, _, name_part = line.partition(",")
            # atributos entre #EXTINF:-1 y la coma
            attrs = {}
            for m in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', attr_part):
                attrs[m.group(1)] = m.group(2)
            current_attrs = attrs
            current_name = name_part.strip()
            # siguiente línea debería ser URL
            if i + 1 < len(lines):
                url = lines[i + 1].strip()
                if url and not url.startswith("#"):
                    entries.append((current_name, url, current_attrs))
                    i += 1  # saltar URL
            current_name = None
            current_attrs = {}
        i += 1
    return entries

def build_extinf_line(name: str, attrs: Optional[Dict[str, str]] = None) -> str:
    attr_str = ""
    if attrs:
        # Asegurar orden estable (alfabético)
        parts = [f'{k}="{v}"' for k, v in sorted(attrs.items())]
        if parts:
            attr_str = " " + " ".join(parts)
    return f"#EXTINF:-1{attr_str}, {name}"

def fetch(url: str, timeout: int = 20, retries: int = 2, sleep_min=1.0, sleep_max=2.5) -> Optional[str]:
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.text
            logging.warning("GET %s -> %s", url, r.status_code)
        except Exception as e:
            logging.warning("GET %s error: %s", url, e)
        if attempt < retries:
            time.sleep(random.uniform(sleep_min, sleep_max))
    return None

def extract_url_from_html(html: str, ch: Channel) -> Optional[str]:
    # 1) regex directa si se indicó
    if ch.regex:
        m = re.search(ch.regex, html, flags=re.IGNORECASE)
        if m:
            candidate = m.group(0)
            return normalize_acestream(candidate)

    # 2) selector CSS
    if ch.selector:
        soup = BeautifulSoup(html, "lxml")
        els = soup.select(ch.selector)
        for el in els:
            if ch.attr:
                candidate = el.get(ch.attr, "") or ""
            else:
                candidate = el.get_text(strip=True)
            candidate = candidate.strip()
            if ch.inner_regex:
                m = re.search(ch.inner_regex, candidate, flags=re.IGNORECASE)
                if m:
                    candidate = m.group(0)
                else:
                    continue
            url = normalize_acestream(candidate)
            if url:
                return url

    # 3) fallback: intenta buscar cualquier acestream en la página
    m = ACESTREAM_REGEX.search(html)
    if m:
        return normalize_acestream(m.group(0))

    return None

def normalize_acestream(candidate: str) -> Optional[str]:
    c = candidate.strip()
    if c.startswith("acestream://"):
        # normalizar a minúsculas la parte del hash
        parts = c.split("acestream://", 1)[1]
        if HEX40_REGEX.match(parts):
            return "acestream://" + parts.lower()
        return c
    if HEX40_REGEX.fullmatch(c):
        return "acestream://" + c.lower()
    # podría ser m3u8 u otro: devolver tal cual si parece URL
    if c.startswith(("http://", "https://")):
        return c
    return None

def main(dry_run: bool = False) -> int:
    channels = load_config(CONFIG_PATH)
    old_entries = parse_m3u(M3U_PATH)
    old_map = {name: (url, attrs) for name, url, attrs in old_entries}

    new_entries: List[Tuple[str, str, Dict[str, str]]] = []
    changes: List[str] = []

    for ch in channels:
        logging.info("Procesando: %s", ch.name)
        url: Optional[str] = None

        if ch.fixed_url:
            url = ch.fixed_url
            logging.info("  fixed_url usado")
        else:
            if not ch.source_url:
                logging.warning("  Sin source_url ni fixed_url: se omite")
            else:
                html = fetch(ch.source_url)
                if html:
                    found = extract_url_from_html(html, ch)
                    if found:
                        url = found
                        logging.info("  encontrado -> %s", url)
                if not url:
                    logging.warning("  No se pudo extraer. Intentando mantener el anterior.")
                    if ch.name in old_map:
                        url = old_map[ch.name][0]
                        logging.info("  se mantiene anterior -> %s", url)

        if url:
            prev = old_map.get(ch.name)
            if (not prev) or (prev[0] != url):
                changes.append(f"{ch.name}: {prev[0] if prev else '∅'}  ->  {url}")
            new_entries.append((ch.name, url, ch.attrs or {}))
        else:
            logging.error("  No hay URL para '%s'; quedará fuera del M3U.", ch.name)

    # Construir contenido M3U
    m3u_lines = ["#EXTM3U"]
    for name, url, attrs in new_entries:
        m3u_lines.append(build_extinf_line(name, attrs))
        m3u_lines.append(url)

    new_content = "\n".join(m3u_lines) + "\n"
    old_content = M3U_PATH.read_text(encoding="utf-8") if M3U_PATH.exists() else ""

    if new_content != old_content:
        if dry_run:
            logging.info("Cambios detectados (dry-run):\n%s", "\n".join(changes) or "—")
        else:
            M3U_PATH.write_text(new_content, encoding="utf-8")
            logging.info("M3U actualizado con %d entradas.", len(new_entries))
            if changes:
                logging.info("Resumen de cambios:\n%s", "\n".join(changes))
    else:
        logging.info("Sin cambios en la lista.")

    return 0

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    raise SystemExit(main(dry_run=dry))
