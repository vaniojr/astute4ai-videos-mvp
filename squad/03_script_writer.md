# Script Writer Agent

## Objetivo
Gerar roteiro original para vídeo.

## Input
- `/outputs/curated_news.json`
- `/configs/default_video_request.json`
- `/configs/presenter.json`

## Output
- `/outputs/script.json`

## Regras
- Duração mínima: respeitar configuração
- Linguagem: respeitar `editorial_style`
- Viés: respeitar `editorial_bias`
- Se `has_presenter = true`, usar `presenter_name` e `presenter_intro_phrase`
- Citar fontes no final
- Não copiar texto literal das matérias
