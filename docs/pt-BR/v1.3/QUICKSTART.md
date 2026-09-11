> Snapshot dos docs em português da v1.3. Os docs em inglês na raiz do repositório são canônicos e descrevem a v2 (entry points, build.py). Os comandos abaixo referem-se à CLI da v1.3 (`--urls`, `endpoints`, `ucs.json`), que a v2 não aceita mais — use os docs em inglês para a CLI atual.

# Quickstart

Pré-requisitos: Python 3.10+, Node 22+, git. Testado em Windows (Git Bash) e deve rodar
igual em Unix.

No Windows, `python` pode resolver para uma instalação antiga (shim da Microsoft Store ou
uma entrada anterior no PATH) mesmo com o 3.12 instalado — confira com `python --version`
ou chame `py -3`. Os scripts do pipeline avisam em stderr quando rodam abaixo do 3.10.

## 1. Extração determinística (extractor vendorado)

O extractor vive em `extractor/` — derivado mínimo da fase-1 do Understand-Anything
(MIT, commit pinado; ver `extractor/NOTICE`). Sem LLM, sem rede em runtime; a única
ida à rede é o `npm ci` inicial (grammars tree-sitter pinadas por lockfile).

```bash
cd extractor
npm ci --ignore-scripts
node extract.mjs /caminho/do/repo --out out/ --exclude "dist/*" --lang python
```

Saída em `out/`: `scan-output.json`, `im-output.json`, `es-output.json` (+ os
intermediários, para depuração). `--lang` filtra por linguagem (omita para todas —
o extractor cobre as ~15 linguagens dos grammars vendorados); `--exclude` aceita
padrões gitignore separados por vírgula. Nada é escrito no repo alvo.

## 2. Config do repo

Copie `config/example.json` e ajuste `repo`, `commit`, `data`, `categories` e
`rules` (prefixo de caminho → categoria; as 6 primeiras categorias não-`gray` ganham as
cores; `muted` nasce oculta, com alternador no cabeçalho). `fallback_category`,
`test_path_marker` e `test_category` cobrem o que as regras não pegam.

`urls_files` é anotação: registra quais `urls.py` alimentam o parser de endpoints. Nenhum
script o lê — os caminhos vão na mão em `prep_extra --urls` (passo 3).

### Descobrindo `categories` e `rules`

Caminho primário — deixe o scan propor o rascunho:

```bash
python pipeline/suggest_config.py --scan out/scan-output.json --repo meu-repo \
    --out config/meu-repo.json
```

Ele agrupa os diretórios de topo por contagem de arquivos (descendo ao 2º nível quando o
topo é um monolito único tipo `app/`, `src/` ou `v1/`), emite as categorias nessa ordem —
as 6 primeiras coloridas, pastas `test`/`tests`/`spec` já `gray`+`muted` — e imprime em
stderr uma tabela `dir | arquivos | linguagem`. É **rascunho**: revise pela tabela quais
categorias fundir ou renomear (nome de pasta não é papel de arquitetura), confira que os
diretórios sem regra realmente pertencem a `outros`, e preencha `commit` (sai como
`AJUSTAR`) e `data`.

Fallback manual, se preferir escrever à mão:

1. liste as pastas de topo do repo (e as de 2º nível, se tudo mora sob uma só);
2. agrupe por papel, não por nome — 6 categorias coloridas é o teto útil, o resto vai para
   `outros`;
3. marque as pastas de teste como `gray` + `muted`.

## 3. Compor e injetar

```bash
python pipeline/prep_data.py  --es es-output.json --imports im-output.json \
    --config config/meu-repo.json --ucs data/meu-repo/ucs.json --out data.json
python pipeline/prep_extra.py --es es-output.json --imports im-output.json \
    --urls /caminho/do/repo/app/urls.py --out extra.json
python pipeline/inject.py --template viewer/template.html --data data.json \
    --extra extra.json --out matryoshker.html
```

Os três imprimem contadores — é por eles que se confere o resultado:
`files=… imports=… ucs=… hops=…`, `endpoints=… calls: internos=… cross=…` e o tamanho do
HTML. `hops` menor que o total escrito no `ucs.json` significa hop cujo **arquivo** não
resolveu contra o grafo; o `prep_data.py` detalha cada descarte em stderr e ainda assim
sai com código 0 — leia o stderr (símbolo depois dos dois-pontos ele não valida; veja
CONTRIBUTING.md).

`--ucs` e `--extra` são opcionais; `--urls` aceita vários arquivos
(`--urls a/urls.py b/urls.py`) e, sem nenhum, sai `endpoints=0` — o resto continua.
`endpoints=0` também é o resultado normal quando o repo alvo não é Django/DRF (o parser é
específico desses) — não é erro seu.

## 4. Abrir

`matryoshker.html` é autocontido — abra no browser, sirva estático ou publique como
Claude Artifact. Sem servidor, sem build, sem chaves. A página faz exatamente uma
requisição externa, o `<link>` do Google Fonts no `<head>`; offline ou atrás de uma CSP
que a bloqueie, o mapa funciona por completo e as fontes caem para as do sistema.

Abre em **Pacotes**; *Contexto* sobe um nível, duplo-clique num arquivo desce para
**Símbolos**, e **Fluxo** aparece na migalha quando há UC ou endpoint ativo. Esc sobe um
nível. O tema segue o do ambiente (sistema ou `data-theme` de quem hospeda). Arranjos de
nós e rascunhos de status ficam em `localStorage`, por commit e por navegador.

Sem registro de UCs ainda? Omita `--ucs` — o mapa, os símbolos e os endpoints funcionam;
o painel de use-cases fica vazio até o primeiro `data/<repo>/ucs.json` (veja
CONTRIBUTING.md para semear um).
