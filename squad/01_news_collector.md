# News Collector Agent

## Objetivo
Coletar notícias com base nas fontes configuradas.

## Input
- `/configs/default_video_request.json`
- `/configs/sources.json`

## Output
- `/outputs/collected_news.json`

## Regras
- Usar apenas fontes configuradas
- Retornar título, fonte, URL, data, resumo curto
- Não gerar roteiro
- Não opinar
- Se uma fonte falhar, registrar erro
