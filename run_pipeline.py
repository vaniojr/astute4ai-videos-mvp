#!/usr/bin/env python3
"""
Pipeline runner para Astute4AI Videos.
Uso:
    python3 run_pipeline.py          # etapas 1-4 (para se approval_required=true)
    python3 run_pipeline.py --finish # etapas 5-7 (continua após aprovação)
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
OUTPUTS  = BASE_DIR / "outputs"
CONFIGS  = BASE_DIR / "configs"
SQUAD    = BASE_DIR / "squad"

load_dotenv(BASE_DIR / ".env")
OUTPUTS.mkdir(exist_ok=True)


# ── logging helpers ────────────────────────────────────────────────────────────

def log(msg: str = ""):
    print(msg, flush=True)

def step_start(n: int, name: str):
    print(f"[STEP:{n}] {name}", flush=True)

def step_done(n: int):
    print(f"[DONE:{n}]", flush=True)

def step_error(n: int, msg: str):
    print(f"[ERROR:{n}] {msg}", flush=True)


# ── Stage 1: News Collector (pure Python RSS) ──────────────────────────────────

def collect_news():
    step_start(1, "Coletando notícias das fontes RSS...")
    sources_cfg = json.loads((CONFIGS / "sources.json").read_text(encoding="utf-8"))
    sources     = [s for s in sources_cfg.get("sources", []) if s.get("enabled", True)]

    items:  list[dict] = []
    errors: list[dict] = []

    for src in sources:
        feed_url = src.get("feed_url", "")
        if not feed_url:
            continue
        try:
            r = requests.get(
                feed_url, timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AstutePipeline/1.0)"},
            )
            r.raise_for_status()

            # detecta encoding via Content-Type; ISO-8859-1 não tem declaração XML
            ct = r.headers.get("content-type", "")
            enc_match = re.search(r"charset=([\w-]+)", ct)
            enc = enc_match.group(1) if enc_match else "utf-8"
            xml_text = r.content.decode(enc, errors="replace")
            # garante declaração de encoding compatível com o parser
            if not xml_text.lstrip().startswith("<?xml"):
                xml_text = f'<?xml version="1.0" encoding="utf-8"?>\n' + xml_text
            root    = ET.fromstring(xml_text.encode("utf-8"))
            channel = root.find(".//channel") or root
            found   = channel.findall("item") or root.findall(
                ".//{http://www.w3.org/2005/Atom}entry"
            )

            count = 0
            for item in found[:15]:
                title = (
                    item.findtext("title") or
                    item.findtext("{http://www.w3.org/2005/Atom}title") or ""
                ).strip()
                link = (
                    item.findtext("link") or
                    item.findtext("{http://www.w3.org/2005/Atom}link") or ""
                ).strip()
                desc = (
                    item.findtext("description") or
                    item.findtext("{http://www.w3.org/2005/Atom}summary") or ""
                ).strip()
                desc = re.sub(r"<[^>]+>", "", desc)[:400]
                pub  = (
                    item.findtext("pubDate") or
                    item.findtext("{http://www.w3.org/2005/Atom}updated") or ""
                )
                if title:
                    items.append({
                        "title":   title,
                        "source":  src["name"],
                        "url":     link,
                        "date":    pub,
                        "summary": desc,
                    })
                    count += 1
            log(f"  ✓ {src['name']}: {count} itens")
        except Exception as exc:
            errors.append({"source": src["name"], "error": str(exc)})
            log(f"  ✗ {src['name']}: {exc}")

    output = {
        "items":        items,
        "errors":       errors,
        "collected_at": datetime.datetime.now().isoformat(),
        "total":        len(items),
    }
    (OUTPUTS / "collected_news.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log(f"  → {len(items)} notícias de {len(sources) - len(errors)} fontes ativas")
    step_done(1)


# ── OpenAI helper ──────────────────────────────────────────────────────────────

def ai_call(system: str, user: str, step_num: int) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        step_error(
            step_num,
            "OPENAI_API_KEY não configurada. "
            "Acesse Configurações → API Keys na interface.",
        )
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    log("  → chamando OpenAI gpt-4o-mini...")

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.4,
        max_tokens=4096,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$",           "", text, flags=re.MULTILINE)
    return text.strip()


def run_ai_stage(
    step_num: int,
    step_name: str,
    agent_file: str,
    input_files: list[str],
    output_file: str,
    extra: str = "",
) -> dict:
    step_start(step_num, step_name)

    system = (SQUAD / agent_file).read_text(encoding="utf-8")

    inputs: dict[str, object] = {}
    for fname in input_files:
        p = (BASE_DIR / fname) if fname.startswith("configs/") else (OUTPUTS / fname)
        if p.exists():
            inputs[fname] = json.loads(p.read_text(encoding="utf-8"))

    user = (
        "Processe os inputs abaixo seguindo as instruções do sistema.\n"
        "Retorne APENAS JSON válido — sem markdown, sem explicações, sem blocos de código.\n\n"
        f"INPUTS:\n{json.dumps(inputs, indent=2, ensure_ascii=False)}\n\n"
        f"{extra}"
    )

    raw = ai_call(system, user, step_num)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        step_error(step_num, f"JSON inválido: {exc} | resposta: {raw[:300]}")
        sys.exit(1)

    (OUTPUTS / output_file).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log(f"  → salvo em outputs/{output_file}")
    step_done(step_num)
    return data


# ── Stage 6: Video Payload Builder (pure Python) ──────────────────────────────

def build_video_payload():
    step_start(6, "Video Payload Builder")
    script    = json.loads((OUTPUTS / "script_validated.json").read_text(encoding="utf-8"))
    presenter = json.loads((CONFIGS / "presenter.json").read_text(encoding="utf-8"))

    full_text = " ".join(s.get("text", "") for s in script.get("segments", []))

    payload = {
        "provider":    presenter.get("avatar", {}).get("provider", "images_tts"),
        "avatar_id":   presenter.get("avatar", {}).get("avatar_id", ""),
        "voice_id":    presenter.get("avatar", {}).get("voice_id", ""),
        "script_text": full_text,
        "segments":    script.get("segments", []),
        "settings": {"width": 1280, "height": 720, "fps": 24, "avatar_style": "normal"},
        "presenter": {
            "name":         presenter.get("name", ""),
            "intro_phrase": presenter.get("intro_phrase", ""),
        },
    }
    (OUTPUTS / "video_payload.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log("  → salvo em outputs/video_payload.json")
    step_done(6)


# ── Stage 7: Publisher Payload Builder (pure Python) ──────────────────────────

def build_publish_payload():
    step_start(7, "Publisher Payload Builder")
    pkg = json.loads((OUTPUTS / "content_package.json").read_text(encoding="utf-8"))

    desc     = pkg.get("description", "")
    chapters = pkg.get("chapters", [])
    if chapters:
        desc += "\n\n" + "\n".join(
            f"{c.get('time','00:00')} {c.get('title','')}" for c in chapters
        )

    payload = {
        "platform":       "youtube",
        "title":          pkg.get("title", ""),
        "description":    desc,
        "tags":           pkg.get("hashtags", [])[:15],
        "visibility":     "private",
        "category_id":    25,
        "made_for_kids":  False,
        "thumbnail_text": pkg.get("thumbnail_text", ""),
        "video_file_ref": "outputs/video_images.mp4",
        "generated_at":   datetime.datetime.now().isoformat(),
    }
    (OUTPUTS / "publish_payload.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log("  → salvo em outputs/publish_payload.json")
    step_done(7)


# ── Pipeline halves ────────────────────────────────────────────────────────────

def run_first_half():
    """Etapas 1-4. Para em [APPROVAL_REQUIRED] se necessário."""
    config = json.loads((CONFIGS / "default_video_request.json").read_text(encoding="utf-8"))

    log("=" * 52)
    log("  Astute4AI Videos — Pipeline (etapas 1–4)")
    log("=" * 52)
    log()

    collect_news()
    log()

    run_ai_stage(
        2, "News Curator", "02_news_curator.md",
        ["collected_news.json"],
        "curated_news.json",
        "Retorne JSON com chave 'items' (array de 3-5 notícias curadas), cada uma com: "
        "title, source, url, date, summary, relevance_reason.",
    )
    log()

    presenter = json.loads((CONFIGS / "presenter.json").read_text(encoding="utf-8"))
    run_ai_stage(
        3, "Script Writer", "03_script_writer.md",
        ["curated_news.json"],
        "script.json",
        f"Config: {json.dumps(config)}\nPresenter: {json.dumps(presenter)}\n"
        "REQUISITOS OBRIGATÓRIOS DE DURAÇÃO:\n"
        "- Vídeo com MÍNIMO 6 minutos (nunca abaixo disso)\n"
        "- Cada news_block: mínimo 180 palavras (aprofunde contexto, causas, impacto, desdobramentos)\n"
        "- Total do roteiro: mínimo 800 palavras\n"
        "- Velocidade de leitura: ~130 palavras/minuto\n\n"
        "Retorne JSON com:\n"
        "  segments: array de objetos com campos:\n"
        "    - type: 'intro' | 'news_block' | 'transition' | 'outro'\n"
        "    - text: string (mínimo 180 palavras para news_block)\n"
        "    - news_ref: string 1-N (somente em news_block)\n"
        "    - image_query: string com 3-5 palavras em INGLÊS descrevendo "
        "a cena visual ideal para este segmento — seja específico e descritivo "
        "(ex: 'brazil congress vote politicians chamber', 'flood rescue victims rio grande', "
        "'supreme court judge brazil gavel', 'inflation market prices supermarket brazil')\n"
        "  estimated_duration_min: número\n"
        "  word_count: número total de palavras no roteiro\n"
        "  sources: array de strings\n",
    )
    log()

    run_ai_stage(
        4, "Editorial Validator", "04_editorial_validator.md",
        ["script.json", "curated_news.json"],
        "script_validated.json",
        "Retorne o mesmo JSON do script.json com campo adicional 'validation': "
        "{'passed': bool, 'checks': {sources_cited, no_literal_copy, duration_ok, "
        "tone_ok, factual_ok, sources_used_only}, 'notes': ''}.",
    )
    log()

    if config.get("approval_required", False):
        log("⏸  Roteiro aguardando aprovação na Etapa 8.")
        print("[APPROVAL_REQUIRED]", flush=True)
    else:
        run_second_half()


def run_second_half():
    """Etapas 5-7. Executar após aprovação do roteiro."""
    log("=" * 52)
    log("  Astute4AI Videos — Pipeline (etapas 5–7)")
    log("=" * 52)
    log()

    run_ai_stage(
        5, "Content Packager", "05_content_packager.md",
        ["script_validated.json"],
        "content_package.json",
        "Retorne JSON com: title (string), description (string ≤500 chars), "
        "hashtags (array ≤15 strings), chapters (array de {time, title}), "
        "thumbnail_text (string curta para capa).",
    )
    log()

    build_video_payload()
    log()

    build_publish_payload()
    log()

    log("✅ Pipeline completo! Acesse a Etapa 9 para gerar o vídeo.")
    print("[PIPELINE_DONE]", flush=True)


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--finish":
        run_second_half()
    else:
        run_first_half()
