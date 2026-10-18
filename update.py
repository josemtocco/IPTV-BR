#!/usr/bin/env python3
"""
Atualizador inteligente de lista M3U Brasil para SS IPTV.
Fonte: iptv-org (mesma base do brazil-stream-finder.lovable.app)

Regras:
- Atualiza a cada 6h via GitHub Actions
- Nunca remove canal que ainda funciona
- Só remove se falhar em 3 atualizações consecutivas
- Mantém histórico de canais que já funcionaram (mesmo que saiam da fonte)
- Gera M3U otimizado para SS IPTV (UTF-8, logos, group-title em PT, tvg-id)
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== CONFIGURAÇÃO =====================
SOURCE_M3U = "https://iptv-org.github.io/iptv/countries/br.m3u"
STATE_FILE = Path("state.json")
OUTPUT_M3U = Path("playlist.m3u")
MAX_FAILS = 3                    # remove só após 3 falhas seguidas
TIMEOUT = 8                      # segundos por teste de stream
WORKERS = 40                     # testes paralelos
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# Mapeamento de categorias EN -> PT (para SS IPTV ficar legível)
CATEGORY_MAP = {
    "general": "Geral",
    "entertainment": "Entretenimento",
    "news": "Notícias",
    "sports": "Esportes",
    "movies": "Filmes",
    "series": "Séries",
    "kids": "Infantil",
    "music": "Música",
    "documentary": "Documentários",
    "culture": "Cultura",
    "education": "Educação",
    "religious": "Religioso",
    "outdoor": "Agro / Campo",
    "shop": "Compras",
    "business": "Negócios",
    "comedy": "Comédia",
    "cooking": "Culinária",
    "lifestyle": "Lifestyle",
    "animation": "Animação",
    "legislative": "Legislativo",
    "weather": "Clima",
    "auto": "Automóveis",
    "classic": "Clássicos",
    "undefined": "Outros",
    "family": "Família",
    "public": "Público",
}

# ===================== HTTP SESSION =====================
def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(total=1, backoff_factor=0.3, status_forcelist=[502, 503, 504])
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({"User-Agent": USER_AGENT})
    return s

SESSION = make_session()

# ===================== PARSE M3U =====================
def parse_m3u(text: str) -> List[Dict]:
    """Retorna lista de dicts: {extinf, url, name, tvg_id, logo, groups}"""
    channels = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            url = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not next_line.startswith("#"):
                    url = next_line
                    i += 1
            if url.startswith("http"):
                name = line.split(",", 1)[-1].strip() if "," in line else "Canal"
                tvg_id = re.search(r'tvg-id="([^"]*)"', line)
                logo = re.search(r'tvg-logo="([^"]*)"', line)
                groups = re.search(r'group-title="([^"]*)"', line)
                channels.append({
                    "extinf": line,
                    "url": url,
                    "name": name,
                    "tvg_id": tvg_id.group(1) if tvg_id else "",
                    "logo": logo.group(1) if logo else "",
                    "groups": groups.group(1) if groups else "Outros",
                })
        i += 1
    return channels

def translate_groups(groups: str) -> str:
    """Converte group-title EN para PT (primeiro grupo principal)."""
    if not groups:
        return "Outros"
    parts = [p.strip().lower() for p in groups.split(";")]
    translated = []
    for p in parts:
        translated.append(CATEGORY_MAP.get(p, p.capitalize()))
    # Prioriza um grupo principal legível
    priority = ["Notícias", "Esportes", "Filmes", "Séries", "Infantil", "Geral", "Entretenimento"]
    for p in priority:
        if p in translated:
            return p
    return translated[0] if translated else "Outros"

def build_extinf(ch: Dict) -> str:
    """Monta linha #EXTINF otimizada para SS IPTV."""
    groups_pt = translate_groups(ch.get("groups", ""))
    tvg_id = ch.get("tvg_id") or ""
    logo = ch.get("logo") or ""
    name = ch.get("name") or "Canal"
    # Limpa sufixos feios
    name = re.sub(r"\s*\[Not 24/7\]", "", name).strip()
    name = re.sub(r"\s*\(\d+p\)", "", name).strip()  # qualidade fica no nome se quiser, mas limpo
    attrs = []
    if tvg_id:
        attrs.append(f'tvg-id="{tvg_id}"')
    if logo:
        attrs.append(f'tvg-logo="{logo}"')
    attrs.append(f'group-title="{groups_pt}"')
    return f'#EXTINF:-1 {" ".join(attrs)},{name}'

# ===================== TESTE DE STREAM =====================
def test_stream(url: str) -> bool:
    """Verifica se o stream responde (HEAD ou GET parcial)."""
    try:
        # Alguns servidores não gostam de HEAD
        r = SESSION.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
        if r.status_code >= 400:
            return False
        # Lê poucos bytes para confirmar que não é página de erro
        chunk = next(r.iter_content(512), b"")
        r.close()
        if not chunk:
            return False
        # Rejeita HTML de erro óbvio
        text_start = chunk[:200].lower()
        if b"<html" in text_start or b"<!doctype" in text_start:
            return False
        return True
    except Exception:
        return False

# ===================== ESTADO =====================
def load_state() -> Dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"channels": {}, "last_update": None}

def save_state(state: Dict):
    state["last_update"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ===================== LÓGICA PRINCIPAL =====================
def main():
    print("=" * 60)
    print("IPTV Brasil → SS IPTV | Atualização inteligente")
    print("=" * 60)

    # 1. Baixa fonte atual
    print(f"\n[1/5] Baixando fonte: {SOURCE_M3U}")
    try:
        r = SESSION.get(SOURCE_M3U, timeout=30)
        r.raise_for_status()
        source_channels = parse_m3u(r.text)
        print(f"      → {len(source_channels)} canais na fonte")
    except Exception as e:
        print(f"ERRO ao baixar fonte: {e}")
        sys.exit(1)

    # 2. Carrega estado anterior
    state = load_state()
    old = state.get("channels", {})
    print(f"[2/5] Estado anterior: {len(old)} canais conhecidos")

    # 3. Monta lista de candidatos (fonte + histórico)
    #    Prioridade: URL é a chave única
    candidates: Dict[str, Dict] = {}

    # Histórico primeiro (para preservar info)
    for url, info in old.items():
        candidates[url] = {
            "url": url,
            "extinf_raw": info.get("extinf_raw", ""),
            "name": info.get("name", "Canal"),
            "tvg_id": info.get("tvg_id", ""),
            "logo": info.get("logo", ""),
            "groups": info.get("groups", "Outros"),
            "fail_count": info.get("fail_count", 0),
            "from_source": False,
        }

    # Fonte atual sobrescreve/atualiza metadados
    for ch in source_channels:
        url = ch["url"]
        prev = candidates.get(url, {})
        candidates[url] = {
            "url": url,
            "extinf_raw": ch["extinf"],
            "name": ch["name"],
            "tvg_id": ch["tvg_id"],
            "logo": ch["logo"],
            "groups": ch["groups"],
            "fail_count": prev.get("fail_count", 0),
            "from_source": True,
        }

    print(f"[3/5] Total candidatos a testar: {len(candidates)}")

    # 4. Testa todos em paralelo
    print(f"[4/5] Testando streams (timeout={TIMEOUT}s, workers={WORKERS})...")
    results: Dict[str, bool] = {}
    urls = list(candidates.keys())

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        future_to_url = {executor.submit(test_stream, url): url for url in urls}
        done = 0
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = False
            done += 1
            if done % 50 == 0 or done == len(urls):
                print(f"      → {done}/{len(urls)} testados")

    # 5. Atualiza fail_count e decide quem fica
    kept = []
    new_state_channels = {}
    ok_count = 0
    removed = 0
    recovered = 0

    for url, data in candidates.items():
        works = results.get(url, False)
        fail_count = data["fail_count"]

        if works:
            if fail_count > 0:
                recovered += 1
            fail_count = 0
            ok_count += 1
        else:
            fail_count += 1

        entry = {
            "name": data["name"],
            "tvg_id": data["tvg_id"],
            "logo": data["logo"],
            "groups": data["groups"],
            "extinf_raw": data["extinf_raw"],
            "fail_count": fail_count,
            "last_ok": datetime.now(timezone.utc).isoformat() if works else None,
            "from_source": data["from_source"],
        }
        # Mantém last_ok antigo se não funcionou agora
        if not works and url in old and old[url].get("last_ok"):
            entry["last_ok"] = old[url]["last_ok"]

        if fail_count < MAX_FAILS:
            new_state_channels[url] = entry
            kept.append({
                "url": url,
                "name": data["name"],
                "tvg_id": data["tvg_id"],
                "logo": data["logo"],
                "groups": data["groups"],
            })
        else:
            removed += 1

    # Ordena: grupos prioritários + nome
    group_order = ["Notícias", "Esportes", "Geral", "Entretenimento", "Filmes", "Séries",
                   "Infantil", "Documentários", "Cultura", "Educação", "Religioso",
                   "Agro / Campo", "Música", "Outros"]
    def sort_key(ch):
        g = translate_groups(ch["groups"])
        try:
            gi = group_order.index(g)
        except ValueError:
            gi = 99
        return (gi, ch["name"].lower())

    kept.sort(key=sort_key)

    # 6. Gera M3U otimizado
    print(f"[5/5] Gerando {OUTPUT_M3U}...")
    lines = [
        "#EXTM3U",
        f'#EXTM3U url-tvg="https://iptv-org.github.io/epg/guides/br.xml" x-tvg-url="https://iptv-org.github.io/epg/guides/br.xml"',
        f"# Gerado em {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"# Fonte: iptv-org + histórico | Canais ativos: {len(kept)}",
        f"# Política: remove apenas após {MAX_FAILS} falhas consecutivas",
        "",
    ]

    for ch in kept:
        lines.append(build_extinf(ch))
        lines.append(ch["url"])

    OUTPUT_M3U.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Salva estado
    state["channels"] = new_state_channels
    save_state(state)

    # Relatório
    print("\n" + "=" * 60)
    print(f"✅ Concluído!")
    print(f"   Funcionando agora : {ok_count}")
    print(f"   Mantidos na lista : {len(kept)}")
    print(f"   Removidos (3 fails): {removed}")
    print(f"   Recuperados       : {recovered}")
    print(f"   Arquivo           : {OUTPUT_M3U.resolve()}")
    print("=" * 60)

if __name__ == "__main__":
    main()
