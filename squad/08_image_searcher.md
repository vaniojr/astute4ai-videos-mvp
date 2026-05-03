# Image Searcher Agent

## Objetivo
Mapear cada segmento do roteiro a imagens relevantes para composição do vídeo.

## Input
- `/outputs/script_validated.json`
- `/outputs/curated_news.json`

## Output
- `/outputs/image_manifest.json`

## Regras
- Para cada segmento tipo `news_block`, gerar query de busca em inglês baseada no tema
- Para `intro` e `outro`, usar queries genéricas de jornalismo
- Para `transition`, reutilizar imagens do segmento anterior
- Usar apenas a API Pexels (gratuita, sem restrição editorial)
- Salvar URL, fotógrafo e query usada para cada imagem
- Buscar imagens em orientação landscape (16:9)
