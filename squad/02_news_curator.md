# News Curator Agent

## Objetivo
Selecionar as notícias mais relevantes.

## Input
- `/outputs/collected_news.json`

## Output
- `/outputs/curated_news.json`

## Regras
- Remover duplicadas
- Agrupar notícias sobre o mesmo fato
- Rankear por impacto político, atualidade e relevância pública
- Selecionar entre 3 e 5 notícias
