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
import shutil
import sys
from pathlib import Path

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
MANIFEST_FILE = BASE_DIR / "outputs" / "image_manifest.json"
CONFIG_FILE   = BASE_DIR / "configs" / "video_generation.json"
OUTPUT_VIDEO  = BASE_DIR / "outputs" / "video_images.mp4"
TEMP_DIR      = BASE_DIR / "outputs" / "_tmp_video"
ENV_FILE      = BASE_DIR / ".env"

PEXELS_URL = "https://api.pexels.com/v1/search"

# ── queries por bloco de notícia (news_ref) ────────────────────────────────
_NEWS_QUERIES = {
    1: "brazil congress parliament vote politics",
    2: "flood rain storm city street",
    3: "hospital surgery medical doctor",
    4: "economy finance money debt brazil",
    5: "supreme court judge justice law",
}


# ── config & env ───────────────────────────────────────────────────────────

def load_config() -> dict:
    defaults = {
        "tts_provider": "gtts",
        "tts_voice_openai": "onyx",
        "video_width": 1280,
        "video_height": 720,
        "fps": 24,
        "images_per_segment": 2,
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

def get_query(seg: dict) -> str | None:
    seg_type = seg["type"]
    if seg_type == "intro":
        return "news television studio anchor broadcast"
    if seg_type == "outro":
        return "microphone journalism broadcast television"
    if seg_type == "transition":
        return None
    if seg_type == "news_block":
        return _NEWS_QUERIES.get(seg.get("news_ref"), "brazil politics news")
    return "brazil news politics"


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

    segments = script.get("segments", [])

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

    all_clips    = []
    manifest     = []
    last_images  = []  # fallback para transitions

    for idx, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text:
            continue

        seg_type = seg["type"]
        print(f"[{idx+1:02d}/{len(segments)}] {seg_type}")

        # áudio
        audio_path = TEMP_DIR / f"seg_{idx:02d}.mp3"
        generate_audio(text, audio_path, provider, cfg, env)

        # imagens
        query = get_query(seg)
        image_paths = []
        image_meta  = []

        if query:
            print(f"  busca: \"{query}\"")
            photos = fetch_images(query, pexels_key, cfg["images_per_segment"])
            for pi, photo in enumerate(photos):
                dest = TEMP_DIR / f"seg_{idx:02d}_{pi}.jpg"
                if not dest.exists():
                    download_file(photo["url"], dest)
                if dest.exists():
                    image_paths.append(dest)
                    image_meta.append(photo)
        else:
            image_paths = last_images  # transition: reutiliza imagens anteriores

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
            "search_query": query,
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
