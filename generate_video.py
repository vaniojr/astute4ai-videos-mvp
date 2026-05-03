#!/usr/bin/env python3
"""
Submete o video_payload.json para a API do HeyGen e aguarda a renderização.
Uso: python generate_video.py
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── caminhos ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
PAYLOAD_FILE = BASE_DIR / "outputs" / "video_payload.json"
RESULT_FILE = BASE_DIR / "outputs" / "video_result.json"
ENV_FILE = BASE_DIR / ".env"

# ── constantes ─────────────────────────────────────────────────────────────
HEYGEN_API_BASE = "https://api.heygen.com"
POLL_INTERVAL_SEC = 30
MAX_WAIT_MIN = 30
# HeyGen aceita até ~1500 chars por segmento de voz; dividimos automaticamente
MAX_CHARS_PER_SEGMENT = 1400


def load_api_key() -> str:
    load_dotenv(ENV_FILE)
    key = os.getenv("HEYGEN_API_KEY")
    if not key:
        sys.exit("Erro: HEYGEN_API_KEY não encontrada em .env")
    return key


def load_payload() -> dict:
    if not PAYLOAD_FILE.exists():
        sys.exit(f"Erro: {PAYLOAD_FILE} não encontrado. Execute o pipeline primeiro.")
    with open(PAYLOAD_FILE, encoding="utf-8") as f:
        return json.load(f)


def split_script(text: str, max_chars: int) -> list[str]:
    """Divide o roteiro em blocos respeitando pontuação final de frases."""
    if len(text) <= max_chars:
        return [text]

    segments, current = [], ""
    for sentence in text.replace("\n\n", " <PARA> ").split(". "):
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = (current + ". " + sentence).strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                segments.append(current if current.endswith(".") else current + ".")
            current = sentence

    if current:
        segments.append(current if current.endswith(".") else current + ".")

    return [s.replace("<PARA>", "\n\n") for s in segments]


def build_heygen_request(payload: dict) -> dict:
    avatar_id = payload["avatar_id"]
    voice_id = payload["voice_id"]
    script_text = payload["script_text"]
    settings = payload.get("presenter_settings", {})

    segments = split_script(script_text, MAX_CHARS_PER_SEGMENT)
    total = len(segments)
    if total > 1:
        print(f"Roteiro dividido em {total} segmentos (limite de {MAX_CHARS_PER_SEGMENT} chars/segmento).")

    video_inputs = [
        {
            "character": {
                "type": "avatar",
                "avatar_id": avatar_id,
                "avatar_style": "normal",
            },
            "voice": {
                "type": "text",
                "voice_id": voice_id,
                "input_text": seg,
            },
            "background": {
                "type": "color",
                "value": "#f5f5f0",
            },
        }
        for seg in segments
    ]

    width, height = (1920, 1080) if settings.get("aspect_ratio") == "16:9" else (1920, 1080)

    return {
        "video_inputs": video_inputs,
        "dimension": {"width": width, "height": height},
        "test": False,
    }


def submit_video(api_key: str, request_body: dict) -> str:
    print("Submetendo para HeyGen...")
    resp = requests.post(
        f"{HEYGEN_API_BASE}/v2/video/generate",
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json=request_body,
        timeout=30,
    )

    if not resp.ok:
        print(f"Erro HTTP {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    data = resp.json()
    video_id = data.get("data", {}).get("video_id")
    if not video_id:
        sys.exit(f"Resposta inesperada da API:\n{json.dumps(data, indent=2)}")

    return video_id


def poll_status(api_key: str, video_id: str) -> dict:
    max_polls = (MAX_WAIT_MIN * 60) // POLL_INTERVAL_SEC
    print(f"\nvideo_id : {video_id}")
    print(f"Aguardando renderização (a cada {POLL_INTERVAL_SEC}s, máximo {MAX_WAIT_MIN}min)...\n")

    for attempt in range(1, max_polls + 1):
        resp = requests.get(
            f"{HEYGEN_API_BASE}/v1/video_status.get",
            headers={"X-Api-Key": api_key},
            params={"video_id": video_id},
            timeout=30,
        )

        if not resp.ok:
            print(f"  Aviso: erro HTTP {resp.status_code} ao checar status. Tentando novamente...")
            time.sleep(POLL_INTERVAL_SEC)
            continue

        data = resp.json().get("data", {})
        status = data.get("status", "unknown")
        elapsed_min = (attempt * POLL_INTERVAL_SEC) // 60
        print(f"  [{attempt:02d}] {elapsed_min}min — status: {status}")

        if status == "completed":
            return data
        if status == "failed":
            error = data.get("error") or data.get("msg") or "sem detalhes"
            sys.exit(f"\nRenderização falhou: {error}")

        time.sleep(POLL_INTERVAL_SEC)

    sys.exit(f"\nTimeout: vídeo não ficou pronto em {MAX_WAIT_MIN} minutos.")


def save_result(video_id: str, result: dict) -> None:
    output = {
        "video_id": video_id,
        "status": result.get("status"),
        "video_url": result.get("video_url"),
        "thumbnail_url": result.get("thumbnail_url"),
        "duration_seconds": result.get("duration"),
    }
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def main():
    api_key = load_api_key()
    payload = load_payload()

    print(f"Payload carregado: {len(payload['script_text'])} chars de roteiro")
    print(f"Avatar : {payload['avatar_id']}")
    print(f"Voz    : {payload['voice_id']}\n")

    request_body = build_heygen_request(payload)
    video_id = submit_video(api_key, request_body)
    result = poll_status(api_key, video_id)

    print("\n" + "=" * 52)
    print("  VÍDEO PRONTO")
    print("=" * 52)
    print(f"  URL       : {result.get('video_url')}")
    print(f"  Thumbnail : {result.get('thumbnail_url')}")
    duration = result.get("duration")
    if duration:
        print(f"  Duração   : {int(duration // 60)}min {int(duration % 60)}s")
    print("=" * 52)

    save_result(video_id, result)
    print(f"\nResultado salvo em: {RESULT_FILE}")


if __name__ == "__main__":
    main()
