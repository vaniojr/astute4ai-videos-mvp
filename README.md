# Astute4AI Videos MVP

Pipeline automatizado de geração de vídeos de notícias políticas com avatar IA para YouTube.

## Visão Geral

Uma squad de agentes de IA que executa um pipeline completo:
coleta notícias → seleciona e curada → escreve roteiro → valida → empacota para YouTube → gera payload de vídeo com avatar → prepara publicação.

## Estrutura

```
astute4ai-videos-mvp/
├── README.md
├── PRD.md
├── squad/                        # Definições dos agentes
│   ├── orchestrator.md
│   ├── 01_news_collector.md
│   ├── 02_news_curator.md
│   ├── 03_script_writer.md
│   ├── 04_editorial_validator.md
│   ├── 05_content_packager.md
│   ├── 06_video_payload_builder.md
│   └── 07_publisher_payload_builder.md
├── schemas/                      # Contratos JSON de cada etapa
│   ├── video_request.schema.json
│   ├── news_items.schema.json
│   ├── curated_news.schema.json
│   ├── script_output.schema.json
│   ├── content_package.schema.json
│   └── video_payload.schema.json
├── configs/                      # Configurações do pipeline
│   ├── default_video_request.json
│   ├── sources.json
│   └── presenter.json
└── outputs/                      # Outputs gerados pelo pipeline
    ├── collected_news.json
    ├── curated_news.json
    ├── script.json
    ├── content_package.json
    ├── video_payload.json
    └── publish_payload.json
```

## Como Executar

Abra este projeto no VS Code com Claude Code e execute:

```
Leia o PRD.md e a pasta /squad. Execute o pipeline do MVP usando os arquivos
em /configs, gere os outputs em /outputs e pare após o roteiro, pois
approval_required=true.
```

## Pipeline

| Etapa | Agente | Input | Output |
|-------|--------|-------|--------|
| 1 | News Collector | configs/ | collected_news.json |
| 2 | News Curator | collected_news.json | curated_news.json |
| 3 | Script Writer | curated_news.json + configs/ | script.json |
| 4 | Editorial Validator | script.json | script_validated.json |
| ⏸ | **APROVAÇÃO HUMANA** | script_validated.json | — |
| 5 | Content Packager | script_validated.json | content_package.json |
| 6 | Video Payload Builder | script_validated.json + presenter.json | video_payload.json |
| 7 | Publisher Payload Builder | content_package.json + video_payload.json | publish_payload.json |

## Configuração

Antes de executar, revise:

- [configs/sources.json](configs/sources.json) — fontes de notícias
- [configs/presenter.json](configs/presenter.json) — avatar_id e voice_id do HeyGen
- [configs/default_video_request.json](configs/default_video_request.json) — parâmetros do vídeo
