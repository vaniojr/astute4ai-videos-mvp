# PRD — Astute4AI Videos MVP

## Objetivo

Construir um pipeline de agentes de IA capaz de gerar, de forma autônoma, vídeos de resumo de notícias políticas brasileiras, prontos para publicação no YouTube.

## Problema

Produzir vídeos informativos diários é caro, lento e dependente de equipe humana. O MVP automatiza o ciclo completo — da coleta de notícias à publicação — mantendo supervisão humana apenas no ponto de aprovação do roteiro.

## Solução

Uma squad de 8 agentes especializados, coordenados por um orchestrator, que:

1. Coleta notícias de fontes RSS brasileiras confiáveis
2. Seleciona e curada as mais relevantes
3. Gera roteiro original, sem cópia literal, com viés editorial neutro
4. Valida o roteiro contra critérios editoriais e factuais
5. Empacota o conteúdo para YouTube (título, descrição, hashtags, capítulos)
6. Busca imagens relevantes por segmento do roteiro (Pexels — gratuito)
7. Gera vídeo com narração TTS + slideshow de imagens (`generate_video_images.py` — custo $0)
8. Prepara payload de publicação no YouTube

> **Geração de vídeo com avatar (HeyGen)**
> Implementado e funcional via `generate_video.py`. Custo: ~$5.95 por vídeo de 6 min.
> Substituído pela abordagem de imagens + TTS por custo zero. Manter como opção premium
> quando o canal demandar apresentador em câmera.

## Requisitos Funcionais

### RF-01: Coleta de Notícias
- Coletar de todas as fontes configuradas em `sources.json`
- Janela de coleta configurável (padrão: 12h)
- Registrar erros de fontes sem interromper o pipeline

### RF-02: Curadoria
- Remover duplicatas e agrupar notícias sobre o mesmo fato
- Selecionar entre 3 e 5 notícias por rankeamento de relevância
- Critérios: impacto político, atualidade, relevância pública

### RF-03: Roteiro
- Gerado em português brasileiro
- Duração alvo: 5–8 minutos
- Tom: neutro explicativo
- Apresentador: Rafael (configurável)
- Fontes citadas ao final
- Proibido: cópia literal de matérias

### RF-04: Validação Editorial
- Checar uso exclusivo de fontes coletadas
- Checar citação de fontes
- Checar ausência de cópia literal excessiva
- Checar estimativa de duração adequada

### RF-05: Aprovação Humana
- Quando `approval_required = true`, o pipeline para após a validação do roteiro
- O usuário revisa e aprova antes de continuar

### RF-06: Empacotamento YouTube
- Título ≤ 100 caracteres
- Descrição com capítulos e hashtags
- Máximo de 15 hashtags
- Texto para thumbnail ≤ 60 caracteres

### RF-07: Geração de Vídeo — Imagens + TTS (padrão)
- Buscar imagens no Pexels por segmento do roteiro (orientação landscape)
- Gerar narração via gTTS (gratuito) ou OpenAI TTS (~$0.07/vídeo)
- Montar vídeo 1280x720 com MoviePy + ffmpeg
- Script: `generate_video_images.py`
- Custo: $0.00 com gTTS

### RF-07b: Geração de Vídeo — Avatar HeyGen (opcional/premium)
- Avatar e voice ID configuráveis em `presenter.json`
- Script: `generate_video.py`
- Custo: ~$5.95 por vídeo de 6 min via API
- Usar quando qualidade de apresentador em câmera for necessária

### RF-08: Payload de Publicação
- `made_for_kids = false`
- Visibilidade inicial: `private` (para revisão)

## Requisitos Não-Funcionais

- Todos os outputs devem ser arquivos JSON válidos
- Cada agente deve validar o input antes de processar
- Nenhum agente deve inventar informações não presentes no input
- O pipeline deve ser idempotente (re-executável sem efeitos colaterais)

## Métricas de Sucesso MVP

- Pipeline executa do início ao roteiro sem erros manuais
- Roteiro gerado é aprovado na primeira revisão humana
- Vídeo gerado localmente (imagens + TTS) com custo zero
- Payload de publicação válido para a API do YouTube

## Fora do Escopo (MVP)

- Upload automático ao YouTube
- Agendamento automático de publicação
- Multi-idioma
- Múltiplos apresentadores simultâneos
