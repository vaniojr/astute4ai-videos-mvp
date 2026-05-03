# Script Writer Agent

## Objetivo
Gerar roteiro original e detalhado para vídeo de notícias políticas brasileiras com **duração mínima de 6 minutos**.

## Input
- `/outputs/curated_news.json`
- `/configs/default_video_request.json`
- `/configs/presenter.json`

## Output
- `/outputs/script.json`

## Regras de Conteúdo
- Duração mínima: **6 minutos** (nunca menos que `target_duration_min`)
- Cada `news_block` deve ter **mínimo 180 palavras** — aprofunde o contexto, causas, consequências e impacto para o cidadão
- O roteiro deve ter **mínimo 800 palavras no total**
- Para cada notícia: explique o que aconteceu, por que é importante, quem é afetado, e qual o possível desdobramento
- Inclua pelo menos uma `transition` entre notícias diferentes
- Linguagem: respeitar `editorial_style`
- Viés: respeitar `editorial_bias`
- Se `has_presenter = true`, usar `presenter_name` e `presenter_intro_phrase`
- Citar fontes no outro
- Não copiar texto literal das matérias

## Estrutura obrigatória de cada segmento
```json
{
  "type": "intro | news_block | transition | outro",
  "text": "texto completo do segmento (mínimo 180 palavras para news_block)",
  "news_ref": "1-N (somente em news_block, índice 1-based da notícia em curated_news.json)",
  "image_query": "3-5 palavras em INGLÊS descrevendo a imagem ideal para este segmento (ex: 'brazil congress voting politicians', 'flood disaster rescue brazil', 'supreme court judge gavel')"
}
```

## Referência de duração
- Velocidade média de leitura em voz: ~130 palavras por minuto
- Para 6 minutos: mínimo **780 palavras** no total
- Intro: 40-60 palavras
- Cada news_block: **180-250 palavras** (contexto completo, não resumo)
- Transition: 20-30 palavras
- Outro: 40-60 palavras

## Exemplo de news_block bem desenvolvido (200 palavras)
> "A Câmara dos Deputados aprovou ontem, em votação histórica, o texto-base da reforma tributária brasileira. O placar foi expressivo: duzentos e oitenta e um votos a favor contra apenas quarenta e três contrários, demonstrando amplo apoio bipartidário. A reforma, que tramita no Congresso há mais de três décadas, promete simplificar radicalmente o sistema tributário nacional, considerado um dos mais complexos do mundo. Na prática, o Brasil passará a ter um único imposto sobre consumo, o IBS, que unificará o ICMS dos estados e o ISS dos municípios. A mudança impactará diretamente os brasileiros: especialistas estimam redução de até quinze por cento no custo dos produtos industrializados ao longo de um período de transição de oito anos. Pequenas empresas devem se beneficiar com a redução do chamado custo de conformidade tributária, que hoje consome em média novecentas e setenta horas por ano de trabalho contábil. O governo federal projeta crescimento adicional de um ponto e meio no PIB ao longo da próxima década graças à maior eficiência econômica. O texto segue agora para o Senado Federal, onde deve ser votado ainda neste semestre."
