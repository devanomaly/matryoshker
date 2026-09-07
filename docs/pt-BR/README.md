> Snapshot dos docs em português da v1.3. Os docs em inglês na raiz do repositório são canônicos e descrevem a v2 (entry points, build.py). Os comandos abaixo referem-se à CLI da v1.3 (`--urls`, `endpoints`, `ucs.json`), que a v2 não aceita mais — use os docs em inglês para a CLI atual.

# Matryoshker

Mapa navegável de código em níveis aninhados — como bonecas matryoshka — com overlays
semânticos que nenhuma ferramenta de mercado oferece: **use-cases** e **endpoints** projetados
sobre um grafo extraído deterministicamente do repositório.

Repo-agnóstico por construção: toda especificidade de repo (categorias, regras de
classificação, rotas) vive em `config/` e `data/`, nunca no código do viewer.

## Por que existe

Três varreduras de prior art (08/2026) mostraram que a combinação
*grafo extraído automaticamente × granularidade ajustável × overlays persistentes de
use-case e fluxo* não existe em ferramenta viva — os fragmentos existem separados
(Sourcetrail, CodeScene, AppMap, Understand-Anything), e o produto que mais se aproximou
(CodeSee) morreu em 2024. O padrão da categoria: produtos standalone morrem; **formatos e
primitivas abertas sobrevivem**. Matryoshker é uma camada fina de curadoria e visualização
sobre essas primitivas.

## O que o viewer oferece

| Cena | Nível C4 | O que mostra |
|---|---|---|
| **Contexto** | C1 | pacotes como caixas + arestas agregadas de import (espessura = nº de imports); lente de endpoint esmaece o não-alcançado (BFS prof. 2) |
| **Pacotes** | C2 | todos os arquivos em clusters por pacote, coloridos por categoria |
| **Símbolos** | C3–C4 | duplo-clique num arquivo: classes/funções como pills + chamadas internas e cross-file como arestas |
| **Fluxo** | — | só aparece com UC ou endpoint ativo: UC → cadeia vertical numerada dos hops; endpoint → árvore de chamadas top-down |

Mais:

- overlay de use-case no mapa (dim + badges numerados + setas na ordem dos hops);
- painel de endpoints na barra lateral (porta de entrada pela API) e migalha `rota: … ×`
  para limpar a lente;
- índice reverso **arquivo → use-cases**: clicar num arquivo lista os UCs que passam por
  ele (vínculo por arquivo, não por rota) e leva de volta a cada um;
- `dropdown` de status no painel do UC (rascunho local, ver abaixo);
- busca por arquivo/classe/método e alternador para mostrar as categorias `muted`
  (testes, por padrão ocultas);
- arrastar nós estilo Obsidian: Contexto e Símbolos sempre, Pacotes só com UC ativo. O
  arranjo é salvo em `localStorage` por commit — **por UC** em Pacotes, por cena nas
  demais;
- claro/escuro acompanhando o ambiente (sistema ou `data-theme` de quem hospeda; o viewer
  não tem botão próprio de tema);

tudo num único HTML autocontido (CSP-safe, sem dependências externas além do `<link>` do
Google Fonts). Esse `<link>` é a única requisição de rede da página: bloqueie-o, ou abra o
arquivo offline, e o mapa continua funcionando por completo — só as fontes caem para as do
sistema.

## Tags epistêmicas

Cada use-case carrega um `status` **versionado** no arquivo de dados:

`verificado-humano` · `verificado-agente` · `inferido` · `hipotese` · `desatualizado`

Regra dura: **`verificado-humano` só entra por gesto humano** — pipelines de agente param
em `verificado-agente`. No viewer, o dropdown de status no painel do UC muda um rascunho
local (`localStorage`, marcado com `· local`); o botão *exportar status locais* abre o
JSON `{nome do UC: status}` das alterações para oficializá-las no arquivo versionado via
PR. A fonte de verdade é sempre o repo.

## Pipeline

```
repo alvo
  └─ extractor/extract.mjs (fase-1 vendorada do Understand-Anything: tree-sitter,
       offline, sem LLM — comando único; ver extractor/NOTICE)
  └─ pipeline/prep_data.py   (config do repo + registro de UCs versionado)
  └─ pipeline/prep_extra.py  (endpoints Django/DRF + call edges resolvidos)
  └─ pipeline/inject.py      (dados embutidos no viewer/template.html)
  → matryoshker.html (autocontido; abra no browser ou publique como artifact)
```

`pipeline/suggest_config.py` é o atalho opcional para o primeiro `config/<repo>.json`:
agrega os diretórios do `scan-output.json` por contagem de arquivos e emite um **rascunho**
de `categories`/`rules` para revisar (veja o passo 2 do QUICKSTART).

Veja [QUICKSTART.md](QUICKSTART.md) para o passo-a-passo e [CONTRIBUTING.md](CONTRIBUTING.md)
para contribuir com código **ou com dados** (novos use-cases, bênçãos de status).

## Como funciona

### High-level: três estágios, uma costura

1. **Extrair** (`extractor/extract.mjs`, Node): tree-sitter varre o repo alvo e emite três
   JSONs neutros — inventário de arquivos, mapa de imports resolvidos e estrutura por
   arquivo (classes/métodos/funções com linhas + call graph bruto). Determinístico,
   offline, nada de LLM.
2. **Compor** (`pipeline/*.py`, Python puro): cruza a extração com o que é *seu* —
   `config/<repo>.json` (categorias e regras) e `data/<repo>/ucs.json` (use-cases
   versionados) — e resolve endpoints (Django/DRF) e call edges por heurística de nomes.
   O produto é **um único JSON** (`data.json` + `extra.json`).
3. **Injetar** (`pipeline/inject.py`): replace de string do placeholder `__MATRYOSHKER_DATA__`
   no `viewer/template.html`. Nenhum HTML é gerado em build — o template já É o app;
   ele só recebe os dados embutidos.

O resultado é um HTML autocontido: abrir no browser é o único "deploy". Toda a
renderização acontece em runtime, no `<script>` do próprio template.

### Mid-level: o que o HTML lê

O viewer lê **um objeto JSON embutido** num `<script type="application/json">`, com seis
chaves:

| Chave | Forma (compacta) | Alimenta |
|---|---|---|
| `meta` | `{repo, commit, data, categories[], nfiles…}` | header, legenda, cores por categoria |
| `files` | `[{p: caminho, n: linhas, g: categoria, c: [[classe, ini, fim, [métodos]]…], f: [[função, ini, fim]…]}]` | todas as cenas; o **índice do arquivo neste array** é a identidade usada por todo o resto |
| `imports` | `[[origem, destino]…]` (índices de `files`) | arestas do Contexto (agregadas por pacote), painel importa/importado-por, lente de endpoint (BFS), centralidade `imp` |
| `ucs` | `[{nome, ator, obj, seam, status, regras, hops: [{i: arquivo, s: símbolo, r: papel}]}]` | painel de UCs, overlay com setas, cena Fluxo (cadeia), índice reverso arquivo→UCs, centralidade `UC` |
| `endpoints` | `[{route, view, i: arquivo}]` | painel de endpoints, lente no Contexto, árvore de chamadas no Fluxo |
| `calls` | `{arquivo: {n: [[chamador, chamado, linha]…], x: [[chamador, arquivo-alvo, símbolo, linha]…]}}` | arestas da cena Símbolos (internas e cross-file), árvore de chamadas, centralidade `cham` |

No **boot**, o viewer deriva desses dados os índices que as cenas consomem: adjacência de
imports nos dois sentidos, `ucByFile` (o índice reverso — o mesmo join dos hops, então
UC→arquivos e arquivo→UCs são consistentes por construção) e as três centralidades das
Estrelas (`ucCount`/`impIn`/`callIn`).

Cada **cena** é uma projeção desses índices: Pacotes agrupa `files` por prefixo de caminho
(shelf-packing determinístico — mesmo input, mesmo mapa); Contexto colapsa os clusters e
agrega `imports` entre eles; Símbolos abre `files[i].c/.f` de um arquivo e desenha
`calls[i]`; Fluxo narra `ucs[].hops` em cadeia ou expande `calls[].x` em árvore a partir
de um endpoint. Overlays (dim, setas, halos, lentes) são repinturas sobre a cena, nunca
re-extração.

Duas verdades convivem no runtime: o **JSON embutido** (imutável, vindo do repo) e o
**rascunho local** (`localStorage`: arranjos de drag e overrides de status, por
repo+commit) — o botão de export é a ponte do rascunho de volta ao repo, via PR.

## Contrato de dados (resumo)

- `config/<repo>.json` — `repo`, `commit`, `data`, `categories` (ordenadas; as 6 primeiras
  não-`gray` recebem os slots da paleta categórica validada, e da 7ª em diante repetem o
  último slot; `gray` para neutras, `muted` para ocultas por padrão),
  `rules` (prefixo → categoria), `fallback_category`, `test_path_marker`, `test_category`.
  `urls_files` é anotação: registra quais `urls.py` do repo alimentam o parser de
  endpoints — hoje nenhum script o lê, os caminhos são passados em `prep_extra --urls`.
- `data/<repo>/ucs.json` — lista de use-cases: `nome`, `ator`, `objetivo`, `entry_points`,
  `hops` (`"caminho/arquivo.py:Simbolo — papel"`, em ordem de execução), `async_legs`,
  `failure_paths`, `regras_envolvidas`, `tests`, `seam_crossing`, `status`. O viewer hoje
  consome `nome`, `ator`, `objetivo`, `hops`, `regras_envolvidas`, `seam_crossing` e
  `status`; os demais campos (e extras como `notas`/`preconditions`) ficam no registro
  como documentação e são ignorados pelo `prep_data.py` sem erro.

## Limites conhecidos (v1.3)

- Parser de endpoints é Django/DRF-específico (`router.register` + `path(...as_view)`).
- A extração exige Node 22+; o extractor é vendorado em `extractor/` (derivado mínimo da
  fase-1 do Understand-Anything, MIT, commit pinado em `extractor/NOTICE` — nada de clone
  externo nem build TypeScript). Golden test da paridade: `extractor/golden_check.py`.
- Publicado como Claude Artifact, o HTML é um snapshot (CSP impede fetch externo);
  branch-connect sempre-fresco exige gerar o HTML por branch no CI e hospedar.
- Call edges são resolvidos por heurística de nomes (mesmo arquivo → imports); chamadas
  dinâmicas/reflexivas não aparecem.

## Roadmap curto

1. Compositor de UC no viewer: formulário guiado (nome/ator/objetivo/status) com hops
   montados por **autocomplete sobre o próprio grafo** (arquivo:símbolo validados na
   seleção — mata na origem o problema do símbolo não-conferido) → snippet JSON pronto
   para PR no `ucs.json`. A adição de UC vira fluxo de UI, não edição de JSON na mão.
2. Gate de CI de frescura dos registros (hops/citações resolvidos contra o grafo a cada
   PR) — **etapa separada**, depois da adoção.
3. Geração por branch no CI (branch-connect real).
4. Parsers de endpoint para outros frameworks.

Licença: MIT — veja o arquivo `LICENSE`.
