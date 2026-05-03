#!/usr/bin/env python3
from __future__ import annotations
"""
Gera vídeo de notícias com imagens (Pexels) + narração TTS.
Custo estimado: $0 com gTTS · ~$0.07 com OpenAI TTS.
Pré-requisito: brew install ffmpeg

Uso: python3 generate_video_images.py
"""

import hashlib
import json
import os
import re
import shutil
import sys
import warnings
from pathlib import Path

# Suppress LibreSSL/urllib3 warning on macOS
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

import requests
from dotenv import load_dotenv

# ── compatibilidade Pillow >= 10 com moviepy 1.x ──────────────────────────
try:
    from PIL import Image as _PILImage
    if not hasattr(_PILImage, "ANTIALIAS"):
        _PILImage.ANTIALIAS = _PILImage.LANCZOS
except ImportError:
    pass

# ── paths ──────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
SCRIPT_FILE   = BASE_DIR / "outputs" / "script_validated.json"
CURATED_FILE  = BASE_DIR / "outputs" / "curated_news.json"
MANIFEST_FILE = BASE_DIR / "outputs" / "image_manifest.json"
CONFIG_FILE   = BASE_DIR / "configs" / "video_generation.json"
OUTPUT_VIDEO  = BASE_DIR / "outputs" / "video_images.mp4"
TEMP_DIR      = BASE_DIR / "outputs" / "_tmp_video"
ENV_FILE      = BASE_DIR / ".env"

PEXELS_URL = "https://api.pexels.com/v1/search"

# ── tradução de termos PT-BR → EN para Pexels ─────────────────────────────
_PT_EN: dict[str, str] = {
    # política/governo
    "presidente": "president",
    "presidência": "presidency",
    "governo": "government",
    "ministro": "minister",
    "ministério": "ministry",
    "senado": "senate",
    "senador": "senator",
    "câmara": "congress",
    "deputado": "congressman",
    "congresso": "congress",
    "eleição": "election",
    "eleições": "election",
    "partido": "political party",
    "voto": "vote",
    "votação": "voting",
    "reforma": "reform",
    "projeto de lei": "bill law",
    "constituição": "constitution",
    "golpe": "coup",
    "manifestação": "protest demonstration",
    "protesto": "protest",
    "policia": "police",
    "segurança": "security",
    "crime": "crime",
    "corrupção": "corruption",
    # economia
    "economia": "economy",
    "inflação": "inflation",
    "pib": "gdp economy",
    "dólar": "dollar currency",
    "real": "currency money",
    "banco": "bank",
    "juros": "interest rate",
    "desemprego": "unemployment",
    "emprego": "jobs employment",
    "impostos": "taxes",
    "orçamento": "budget",
    "dívida": "debt",
    "petróleo": "oil petroleum",
    "petrobras": "oil company",
    "agronegócio": "agribusiness",
    "indústria": "industry factory",
    # saúde/social
    "saúde": "healthcare",
    "hospital": "hospital",
    "vacina": "vaccine",
    "pandemia": "pandemic",
    "sus": "healthcare hospital",
    "educação": "education",
    "escola": "school",
    "universidade": "university",
    "ciência": "science",
    # ambiente/desastres
    "clima": "climate",
    "enchente": "flood",
    "seca": "drought",
    "incêndio": "fire",
    "desastre": "disaster",
    "amazônia": "amazon forest",
    "ambiental": "environment",
    # judiciário
    "stf": "supreme court justice",
    "supremo": "supreme court",
    "juiz": "judge court",
    "justiça": "justice court",
    "investigação": "investigation",
    "operação": "police operation",
    # internacional
    "estados unidos": "united states",
    "eua": "usa flag",
    "china": "china",
    "guerra": "war",
    "ucrânia": "ukraine war",
    "diplomacia": "diplomacy",
    "acordo": "agreement signing",
    # misc
    "brasil": "brazil",
    "brasília": "brasilia brazil government",
    "rio de janeiro": "rio de janeiro brazil",
    "são paulo": "sao paulo brazil city",
    "nordeste": "northeast brazil",
}

# Stopwords PT-BR para remover antes de extrair keywords
_STOPWORDS = {
    "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
    "para", "por", "com", "sem", "sob", "sobre", "até", "após",
    "que", "se", "é", "e", "ou", "mas", "um", "uma", "uns", "umas",
    "o", "a", "os", "as", "ao", "aos", "à", "às",
    "este", "esta", "esse", "essa", "isso", "isto",
    "seu", "sua", "seus", "suas", "meu", "minha",
    "como", "mais", "muito", "também", "já", "ainda", "mesmo",
    "só", "não", "foi", "ser", "ter", "tem", "vai", "entre",
    "segundo", "após", "contra", "durante", "ante", "desde",
    "afirmou", "disse", "declarou", "anunciou", "informou",
    "novo", "nova", "novos", "novas", "grande", "grandes",
}


# ── config & env ───────────────────────────────────────────────────────────

def load_config() -> dict:
    defaults = {
        "tts_provider": "gtts",
        "tts_voice_openai": "onyx",
        "video_width": 1280,
        "video_height": 720,
        "fps": 24,
        "images_per_segment": 3,
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            defaults.update(json.load(f))
    return defaults


def load_env() -> dict:
    load_dotenv(ENV_FILE)
    return {
        "pexels_key": os.getenv("PEXELS_API_KEY", ""),
        "openai_key": os.getenv("OPENAI_API_KEY", ""),
        "tts_provider": os.getenv("TTS_PROVIDER", ""),
    }


def check_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("\nErro: ffmpeg não encontrado.\nInstale com: brew install ffmpeg\n")


def load_curated_news() -> dict[str, dict]:
    """Retorna mapa news_ref → {title, summary} a partir do curated_news.json."""
    if not CURATED_FILE.exists():
        return {}
    try:
        data  = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
        items = data.get("items", [])
        # news_ref no roteiro é 1-based index
        return {str(i + 1): item for i, item in enumerate(items)}
    except Exception:
        return {}


# ── construção de query Pexels ────────────────────────────────────────────

def _extract_keywords(text: str, max_words: int = 6) -> list[str]:
    """Extrai palavras-chave relevantes de texto PT-BR."""
    text = text.lower()
    # remove pontuação e números isolados
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()
    # filtra stopwords e palavras muito curtas
    keywords = [w for w in words if len(w) > 3 and w not in _STOPWORDS]
    # conta frequência
    freq: dict[str, int] = {}
    for w in keywords:
        freq[w] = freq.get(w, 0) + 1
    # ordena por frequência
    ranked = sorted(freq, key=lambda w: freq[w], reverse=True)
    return ranked[:max_words]


def _translate_to_en(pt_words: list[str]) -> list[str]:
    """Traduz palavras PT-BR para EN usando dicionário, mantendo as não mapeadas.
    Usa prefix matching para cobrir plurais e variações (enchente→enchentes, etc.)."""
    en_terms: list[str] = []
    seen: set[str] = set()

    # ordena chaves por tamanho desc para priorizar matches mais longos
    dict_keys = sorted(_PT_EN.keys(), key=len, reverse=True)

    for w in pt_words:
        matched = False
        for key in dict_keys:
            # match exato ou prefixo (cobre plural: enchente/enchentes, eleição/eleições)
            if w == key or (len(key) >= 5 and w.startswith(key[:max(4, len(key)-2)])):
                for t in _PT_EN[key].split():
                    if t not in seen:
                        en_terms.append(t)
                        seen.add(t)
                matched = True
                break
        # se não traduziu mas parece nome próprio (maiúsculo no texto original),
        # ignora — Pexels não reconhece nomes próprios brasileiros bem
        _ = matched  # usado implicitamente via loop

    return en_terms


def _multi_word_lookup(text: str) -> str | None:
    """Verifica expressões multi-palavra no dicionário PT→EN."""
    text_lower = text.lower()
    for pt_expr, en_expr in _PT_EN.items():
        if " " in pt_expr and pt_expr in text_lower:
            return en_expr
    return None


def _ai_image_query(text: str, openai_key: str, cache: dict[str, str]) -> str | None:
    """Usa OpenAI gpt-4o-mini para gerar uma query Pexels em inglês a partir do texto PT."""
    if not openai_key:
        return None
    key = hashlib.md5(text[:200].encode()).hexdigest()
    if key in cache:
        return cache[key]
    try:
        from openai import OpenAI
        resp = OpenAI(api_key=openai_key).chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    "You are a photo editor. Given this Brazilian Portuguese news text, "
                    "write 3-5 English keywords to search for a relevant stock photo on Pexels. "
                    "Be specific and visual. Output ONLY the search query, nothing else.\n\n"
                    f"Text: {text[:400]}"
                ),
            }],
            temperature=0.3,
            max_tokens=20,
        )
        query = resp.choices[0].message.content.strip().strip('"').strip("'")
        cache[key] = query
        return query
    except Exception:
        return None


def build_search_query(
    seg: dict, news_map: dict[str, dict],
    openai_key: str = "", ai_cache: dict[str, str] | None = None,
) -> str | None:
    """
    Prioridade da query Pexels:
    1. image_query gerada pelo script writer (campo no JSON do roteiro)
    2. OpenAI gpt-4o-mini, se OPENAI_API_KEY configurada
    3. Keyword extraction PT→EN a partir do título/resumo da notícia + texto do segmento
    """
    seg_type = seg.get("type", "")

    if seg_type == "intro":
        return "news television studio anchor broadcast"
    if seg_type == "outro":
        return "microphone journalism broadcast television"
    if seg_type == "transition":
        return None

    # 1. usa image_query do script writer quando disponível
    script_query = seg.get("image_query", "").strip()
    if script_query:
        return script_query

    seg_text     = seg.get("text", "")
    news_ref     = str(seg.get("news_ref", ""))
    news_item    = news_map.get(news_ref, {})
    news_title   = news_item.get("title", "")
    news_summary = news_item.get("summary", "")
    source_text  = f"{news_title} {news_summary} {seg_text}"

    # 2. OpenAI query generation (fast, specific, in English)
    if openai_key and ai_cache is not None:
        ai_q = _ai_image_query(source_text, openai_key, ai_cache)
        if ai_q:
            return ai_q

    # 3. keyword extraction + PT→EN translation (offline fallback)
    multi    = _multi_word_lookup(source_text)
    pt_words = _extract_keywords(source_text, max_words=8)
    en_words = _translate_to_en(pt_words)

    if multi:
        en_words = multi.split() + en_words

    if not en_words and news_title:
        en_words = [w for w in news_title.split() if len(w) > 3][:4]

    seen: set[str] = set()
    unique: list[str] = []
    for w in en_words:
        if w not in seen:
            unique.append(w)
            seen.add(w)

    query_words = unique[:5]

    if "brazil" not in query_words and "war" not in query_words and "ukraine" not in query_words:
        query_words.append("brazil")

    return " ".join(query_words) if query_words else "brazil politics news"


# ── pexels ─────────────────────────────────────────────────────────────────

def fetch_images(query: str, api_key: str, count: int) -> list[dict]:
    try:
        r = requests.get(
            PEXELS_URL,
            headers={"Authorization": api_key},
            params={"query": query, "per_page": count, "orientation": "landscape"},
            timeout=15,
        )
        if not r.ok:
            print(f"  Pexels {r.status_code}: {r.text[:80]}")
            return []
        return [
            {"url": p["src"]["large2x"], "photographer": p["photographer"]}
            for p in r.json().get("photos", [])
        ]
    except Exception as e:
        print(f"  Pexels erro: {e}")
        return []


def fetch_images_with_fallback(
    primary_query: str, fallback_query: str, api_key: str, count: int
) -> tuple[list[dict], str]:
    """Tenta primary_query; se retornar < 2 fotos, usa fallback_query."""
    photos = fetch_images(primary_query, api_key, count)
    if len(photos) >= 2:
        return photos, primary_query
    print(f"  poucos resultados para \"{primary_query}\" — tentando fallback...")
    fb = fetch_images(fallback_query, api_key, count)
    if fb:
        return fb, fallback_query
    return photos, primary_query


def download_file(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  Download falhou: {e}")
        return False


# ── TTS ────────────────────────────────────────────────────────────────────

def generate_audio(text: str, out: Path, provider: str, cfg: dict, env: dict) -> None:
    if out.exists():
        print(f"  áudio: cache ({out.name})")
        return
    print(f"  áudio: gerando com {provider}...")
    if provider == "openai":
        from openai import OpenAI
        resp = OpenAI(api_key=env["openai_key"]).audio.speech.create(
            model="tts-1",
            voice=cfg.get("tts_voice_openai", "onyx"),
            input=text,
            response_format="mp3",
        )
        resp.stream_to_file(str(out))
    else:
        from gtts import gTTS
        gTTS(text=text, lang="pt", slow=False).save(str(out))


# ── video ──────────────────────────────────────────────────────────────────

def prepare_frame(path: Path, w: int, h: int):
    """Carrega imagem, redimensiona e recorta para exatamente (w, h)."""
    import numpy as np
    from PIL import Image

    img = Image.open(path).convert("RGB")
    ratio = img.width / img.height
    target = w / h
    if ratio > target:
        new_h, new_w = h, int(h * ratio)
    else:
        new_w, new_h = w, int(w / ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    x = (new_w - w) // 2
    y = (new_h - h) // 2
    return np.array(img.crop((x, y, x + w, y + h)))


def build_segment_clip(image_paths: list[Path], audio_path: Path, cfg: dict):
    from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips

    audio = AudioFileClip(str(audio_path))
    w, h  = cfg["video_width"], cfg["video_height"]
    n     = len(image_paths)
    dur_each = audio.duration / n

    clips = [
        ImageClip(prepare_frame(p, w, h)).set_duration(dur_each)
        for p in image_paths
    ]
    video = concatenate_videoclips(clips, method="compose")
    return video.set_audio(audio).set_duration(audio.duration)


def build_fallback_clip(audio_path: Path, cfg: dict):
    from moviepy.editor import AudioFileClip, ColorClip
    audio = AudioFileClip(str(audio_path))
    clip  = ColorClip(
        size=(cfg["video_width"], cfg["video_height"]),
        color=[20, 20, 30],
        duration=audio.duration,
    )
    return clip.set_audio(audio)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    check_ffmpeg()

    cfg = load_config()
    env = load_env()

    provider   = env["tts_provider"] or cfg["tts_provider"]
    pexels_key = env["pexels_key"]

    if not pexels_key:
        sys.exit(
            "Erro: PEXELS_API_KEY não configurada em .env\n"
            "Chave gratuita em: https://www.pexels.com/api/\n"
        )
    if provider == "openai" and not env["openai_key"]:
        sys.exit("Erro: OPENAI_API_KEY não configurada em .env")

    if not SCRIPT_FILE.exists():
        sys.exit(f"Erro: {SCRIPT_FILE} não encontrado. Execute o pipeline primeiro.")

    with open(SCRIPT_FILE, encoding="utf-8") as f:
        script = json.load(f)

    segments  = script.get("segments", [])
    news_map  = load_curated_news()

    if news_map:
        print(f"Notícias carregadas: {len(news_map)} itens para enriquecer queries\n")

    # invalida cache se o roteiro mudou desde a última execução
    script_hash = hashlib.md5(json.dumps(segments, ensure_ascii=False).encode()).hexdigest()
    hash_file   = TEMP_DIR / ".script_hash"
    if TEMP_DIR.exists():
        cached_hash = hash_file.read_text().strip() if hash_file.exists() else ""
        if cached_hash != script_hash:
            print("Roteiro alterado — limpando cache de áudio anterior...\n")
            shutil.rmtree(TEMP_DIR)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(script_hash)

    print(f"TTS provider : {provider}")
    print(f"Segmentos    : {len(segments)}")
    print(f"Resolução    : {cfg['video_width']}x{cfg['video_height']}\n")

    openai_key = env.get("OPENAI_API_KEY", "")
    ai_query_cache: dict[str, str] = {}

    all_clips    = []
    manifest     = []
    last_images: list[Path] = []  # fallback para transitions

    for idx, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text:
            continue

        seg_type = seg["type"]
        print(f"[{idx+1:02d}/{len(segments)}] {seg_type}")

        # áudio
        audio_path = TEMP_DIR / f"seg_{idx:02d}.mp3"
        generate_audio(text, audio_path, provider, cfg, env)

        # query de imagens
        query      = build_search_query(seg, news_map, openai_key, ai_query_cache)
        image_paths: list[Path] = []
        image_meta:  list[dict] = []
        used_query   = query

        if query:
            fallback_q = "brazil politics news government"
            photos, used_query = fetch_images_with_fallback(
                query, fallback_q, pexels_key, cfg["images_per_segment"]
            )
            print(f"  busca: \"{used_query}\" → {len(photos)} foto(s)")
            for pi, photo in enumerate(photos):
                dest = TEMP_DIR / f"seg_{idx:02d}_{pi}.jpg"
                if not dest.exists():
                    download_file(photo["url"], dest)
                if dest.exists():
                    image_paths.append(dest)
                    image_meta.append(photo)
        else:
            image_paths = last_images  # transition: reutiliza imagens anteriores
            print(f"  imagens: reutilizando {len(image_paths)} do segmento anterior")

        # clip
        if image_paths:
            clip = build_segment_clip(image_paths, audio_path, cfg)
            last_images = image_paths
        else:
            print("  imagens: fallback (frame escuro)")
            clip = build_fallback_clip(audio_path, cfg)

        all_clips.append(clip)
        manifest.append({
            "segment_index": idx,
            "type": seg_type,
            "search_query": used_query,
            "images": image_meta,
            "audio_file": str(audio_path.name),
        })

    # salva manifesto
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump({"generated_at": script.get("generated_at"), "segments": manifest},
                  f, indent=2, ensure_ascii=False)
    print(f"\nManifesto: {MANIFEST_FILE}")

    # monta vídeo
    print(f"\nMontando {len(all_clips)} clipes → {OUTPUT_VIDEO.name} ...")
    from moviepy.editor import concatenate_videoclips
    final = concatenate_videoclips(all_clips, method="compose")
    tmp_output = OUTPUT_VIDEO.with_suffix(".tmp.mp4")
    final.write_videofile(
        str(tmp_output),
        fps=cfg["fps"],
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=str(TEMP_DIR / "_tmp_audio.m4a"),
        remove_temp=True,
    )

    # move moov atom to the front so the browser can stream without downloading the full file
    print("  faststart: movendo moov para o início...")
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp_output),
         "-movflags", "+faststart", "-c", "copy", str(OUTPUT_VIDEO)],
        check=True, capture_output=True,
    )
    tmp_output.unlink(missing_ok=True)

    duration_min = final.duration / 60
    print(f"\n{'='*52}")
    print(f"  VÍDEO PRONTO: {duration_min:.1f} min")
    print(f"  Arquivo: {OUTPUT_VIDEO}")
    print(f"{'='*52}")


if __name__ == "__main__":
    main()
