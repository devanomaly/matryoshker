> Snapshot dos docs em português da v1.3. Os docs em inglês na raiz do repositório são canônicos e descrevem a v2 (entry points, build.py). Os comandos abaixo referem-se à CLI da v1.3 (`--urls`, `endpoints`, `ucs.json`), que a v2 não aceita mais — use os docs em inglês para a CLI atual.

# Contribuindo

Matryoshker aceita dois tipos de contribuição — e a segunda é tão importante quanto a
primeira: **código** (viewer/pipeline) e **dados** (use-cases, status, configs de repo).
A manutenção do modelo mental coletivo passa por qualquer pessoa do time conseguir
alimentar novos use-cases e abençoar os existentes.

## Contribuindo com DADOS

### Adicionar um use-case

Edite `data/<repo>/ucs.json` e adicione uma entrada:

```json
{
  "nome": "Ator faz objetivo de negocio",
  "ator": "Analista",
  "objetivo": "uma frase",
  "entry_points": ["POST /v1/rota (arquivo.py:Classe)"],
  "hops": [
    "v1/views/x_views.py:XViewSet.acao — valida e despacha (papel em <=14 palavras)",
    "v1/services/x_service.py:XService.executar — regra central"
  ],
  "async_legs": [], "failure_paths": [], "regras_envolvidas": [], "tests": [],
  "seam_crossing": false,
  "status": "inferido"
}
```

Regras dos hops: em **ordem de execução**, separador em-dash (` — `; ` - ` e ` – ` também
são aceitos, mas padronize no em-dash), símbolo existente no arquivo (prefira
`Classe.metodo` a número de linha).

O que o `prep_data.py` checa — e o que ele **não** checa:

- Ele resolve o **arquivo** do hop contra o grafo. Hop cujo arquivo não resolve é
  descartado, e o prep imprime o hop e o motivo em stderr (não achou o arquivo, ou o
  nome de arquivo é ambíguo) mais um resumo `N/M hops resolvidos`. Leia o stderr: o
  **exit code é 0 mesmo com todos os hops de um UC descartados**, então "rodou sem erro"
  não é prova de nada — o que vale é `hops=` no fim bater com o que você escreveu.
- Ele **não** valida o símbolo depois dos dois-pontos. `arquivo.py:MetodoQueNaoExiste`
  resolve, conta no total e aparece no mapa como se fosse real. Confira o símbolo você
  mesmo, no arquivo.
- Sem nenhum dos separadores aceitos, a linha inteira vira citação e **o papel some sem
  aviso**. Com separador, o papel é truncado em 140 caracteres.

Dos campos acima, o viewer só renderiza `nome`, `ator`, `objetivo`, `hops`,
`regras_envolvidas`, `seam_crossing` e `status`. Os demais (`entry_points`,
`preconditions`, `async_legs`, `failure_paths`, `tests`, `documented`, `notas`) são
registro versionado para humanos e agentes — valem o esforço, mas não aparecem no mapa.

### Status epistêmico (a regra que não se negocia)

- Novo UC escrito por humano sem releitura completa: `inferido`.
- UC estruturado/conferido por pipeline de agentes: **no máximo** `verificado-agente`.
- **`verificado-humano` só entra quando um humano releu os hops e dá a bênção — nunca
  por agente, nunca por default.**
- Achou um UC que o código contradiz? Marque `desatualizado` no PR (não delete — o
  histórico da divergência é informação).

No viewer, o dropdown de status no painel do use-case é rascunho local (`localStorage`,
marcado com `· local` ao lado); *exportar status locais* abre o JSON
`{"<nome do UC>": "<status>"}` das suas alterações para você aplicar no `ucs.json` via PR.
O arquivo versionado é a única fonte de verdade coletiva.

### Novo repo

`config/<repo>.json` (copie o exemplo) + `data/<repo>/ucs.json` (pode nascer vazio: `[]`).

## Contribuindo com CÓDIGO

### Viewer (`viewer/template.html`)

- Arquivo único, **zero dependências externas** (CSP de artifact: nada de CDN; a única
  exceção tolerada é Google Fonts). Esse `<link>` é a única requisição de rede da página, e
  o viewer tem de continuar funcionando por completo quando ela falha: mantenha um fallback
  genérico (`sans-serif`, `monospace`, `system-ui`) no fim de todo `font-family`. Nada de
  framework — SVG + DOM vanilla.
- Temas: todo cor passa por tokens CSS definidos nos três blocos (`:root` claro,
  media-query dark guardada, `[data-theme="dark"]`). Cor definida só num bloco = bug.
- Paleta categórica: as cores dos slots foram validadas (CVD + contraste) nos dois temas —
  não troque hex sem revalidar.
- Dados chegam pelo placeholder `__MATRYOSHKER_DATA__` (nome interno estável do ponto de
  injeção — não renomeie: `inject.py` aborta se ele sumir); o viewer não conhece repo
  nenhum.
- Especificidade de repo no viewer = defeito. Vai para `config`/`data`.

### Pipeline (`pipeline/*.py`)

- Python puro, sem dependências; CLIs com `argparse`; nunca escrever no repo alvo.

### Checklist mínimo antes do PR

1. rodar `prep_data.py`, `prep_extra.py` e `inject.py` (QUICKSTART, passo 3) e **ler o
   stderr** — hop descartado não vira exit code;
2. checar a sintaxe do script do HTML gerado:

   ```bash
   python -c "import re;h=open('matryoshker.html',encoding='utf-8').read();open('check.js','w',encoding='utf-8').write(re.findall(r'<script>(.*?)</script>',h,re.S)[-1])"
   node --check check.js
   ```

3. abrir o HTML e passar pelas quatro cenas — Contexto, Pacotes, duplo-clique num arquivo
   para Símbolos, e Fluxo (que só aparece com UC ou endpoint ativo) — nos dois temas: o
   claro/escuro segue o ambiente, então alterne a preferência do sistema/navegador ou
   force `data-theme="dark"` / `data-theme="light"` no `<html>` pelo devtools;
4. se mexeu num painel da barra lateral, confira os dois estados dele: com dados (entry
   points abertos por padrão, stars listando só arquivos para os quais algo aponta) e sem
   (um build feito sem `--ucs`, em que a seção de entry points some e a lista de stars
   mostra a mensagem de estado vazio);
5. UC overlay: selecionar um UC, conferir badges/setas, e que Esc sobe um nível de cada
   vez até limpar a seleção;
6. clicar num arquivo do overlay e conferir o bloco *Use-cases que passam aqui* (índice
   reverso) — ele é o que quebra quando o vínculo hop→arquivo muda.

PRs pequenos e com um propósito. Descreva o que muda para o usuário do mapa, não só o
que muda no código.
