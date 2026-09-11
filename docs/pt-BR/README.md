# Matryoshker

> Este é o caminho de entrada **atual** em português: o que a ferramenta responde, a
> demo, um tour guiado, o build local, o primeiro use-case e os limites das etiquetas de
> status. Os arquivos em inglês na raiz do repositório são os canônicos e cobrem tudo o
> resto (referência técnica: [`docs/data-contract.md`](../data-contract.md)). O snapshot
> dos docs da v1.3 em português está preservado em [`v1.3/`](v1.3/) e **não** descreve o
> pipeline atual.

**Quando este comportamento muda, que partes do sistema eu preciso olhar?**

Matryoshker é um mapa navegável de código que responde a essa pergunta para um
repositório. Ele junta duas coisas que normalmente vivem separadas:

- **O que o código diz**, extraído automaticamente: arquivos, pacotes, imports, classes,
  funções e as chamadas entre elas. Determinístico, offline, sem LLM.
- **O que as pessoas sabem**, escrito e versionado ao lado do código: *use-cases* — "um
  membro pega um exemplar emprestado" — cada um uma lista curta dos símbolos por onde o
  comportamento passa, em ordem, com um papel de uma linha para cada, e um *status
  epistêmico* dizendo o quanto aquela explicação já foi conferida.

O viewer desenha a segunda camada por cima da primeira, em três níveis aninhados —
pacotes, arquivos, símbolos, como bonecas matryoshka — mais uma cena *Fluxo* que mostra
um comportamento como cadeia numerada. Selecione um use-case e o mapa esmaece tudo o que
ele não toca. Clique num arquivo e ele lista todos os use-cases que passam por ali. Essa é
a ideia inteira: o grafo automático diz o que *pode* chamar o quê; os use-cases curados
dizem o que *importa* e por quê, e dizem o quão certa alguém está disso.

Tudo o que é específico de um repositório — categorias, regras de caminho, parsers de
rota, os próprios use-cases — vive em `config/` e `data/`, nunca no viewer.

## Experimente a demo

**[devanomaly.github.io/matryoshker](https://devanomaly.github.io/matryoshker/)** — o
fixture `examples/sample-drf` (uma pequena app Django/DRF de empréstimo de livros) com
seus cinco use-cases, reconstruído por `.github/workflows/pages.yml` a cada push em
`main`. A interface da demo está em inglês (`"lang": "en"` em `config/example.json`); com
`"lang": "pt-BR"` no config o mesmo build sai com a interface em português, e este tour
cita os dois nomes quando eles diferem.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/demo-use-case-dark.png">
  <img src="../images/demo-use-case-light.png" width="1440"
       alt="O viewer Matryoshker com o use-case 'Member borrows a copy of a title' selecionado. A cena Packages mostra caixas de pacotes com quadrados de arquivo; os seis arquivos por onde o use-case passa levam badges numerados ligados por setas, o resto está esmaecido. A barra lateral esquerda lista os pontos de entrada por tipo e os use-cases com chips de status; o painel direito mostra o ator, o dropdown de status em human-verified, os sete hops com seus papéis e as regras de negócio envolvidas.">
</picture>

*A cena Packages da demo com "Member borrows a copy of a title" selecionado. Os badges
numeram os arquivos na ordem dos hops; o painel direito lista os hops em si. Capturado de
um build local do fixture a 1440×900 (as variantes clara e escura seguem a preferência de
tema do leitor).*

O cabeçalho da demo diz `sample-drf @ 0000000 · 2026-09-05`: esses dois valores vêm de
`config/example.json`, digitados à mão, não lidos do git (veja
[O que as etiquetas dizem e não dizem](#o-que-as-etiquetas-dizem-e-não-dizem)).

### Um tour de cinco minutos

Todos os controles abaixo existem na demo com exatamente estes nomes (em pt-BR entre
parênteses quando o texto muda).

1. **Escolha um use-case.** Na barra lateral esquerda, abra *Use-cases* e clique em
   *Member borrows a copy of a title*. O mapa (cena *Packages* / *Pacotes*) esmaece todo
   arquivo que o use-case não toca e numera os que toca, na ordem dos hops. O painel
   direito mostra o ator, o objetivo, o dropdown de status, a lista *Hops* e as *Rules
   involved* (*Regras envolvidas*). Tudo isso vem do arquivo de registro
   `examples/sample-drf/usecases.json`; nada aqui foi extraído.
2. **Leia o Fluxo.** Clique em *Flow* (*Fluxo*) na migalha. O mesmo use-case agora é uma
   cadeia vertical, uma caixa por hop: arquivo, símbolo, papel. É a explicação curada,
   desenhada hop a hop. Dois hops no mesmo arquivo ganham um badge só no mapa, mas duas
   caixas aqui.
3. **Afaste, aproxime.** *Context* (*Contexto*) mostra os pacotes como caixas com arestas
   de import agregadas. De volta em *Packages*, clique num quadrado de arquivo (por
   exemplo `loan_service.py` em `lending/services`) — o painel direito mostra as classes,
   os imports e, em *Use-cases passing here* (*Use-cases que passam aqui*), todo use-case
   cujos hops tocam o arquivo. Esse índice reverso é a resposta à pergunta de abertura.
   Depois *open symbol map ⌄* (*abrir mapa de símbolos ⌄*), ou duplo-clique no quadrado:
   a cena *Symbols* (*Símbolos*) desenha classes e funções como pílulas com as arestas de
   chamada **extraídas**, e as caixas tracejadas à direita são os outros arquivos que ele
   chama. Clique numa pílula — `renew`, por exemplo — e o painel lista *Calls* (*Chama*)
   e *Called by* (*Chamado por*) vindos da extração. Essa é a segunda fonte de informação:
   o que o código diz, sem curadoria. Comparar isso com a lista de hops é como um revisor
   confere um use-case.
4. **Siga um ponto de entrada.** Em *Entry points* (*Pontos de entrada*), clique em
   *POST /api/books/{id}/borrow*. A migalha ganha `entry point: … ×` (`ponto de entrada:
   … ×`), a cena *Flow* passa a mostrar uma **árvore de chamadas** enraizada na view
   (profundidade 3, busca em largura sobre as chamadas extraídas), e o painel direito
   lista os use-cases que entram ali. Uma árvore de chamadas e o Fluxo de um use-case se
   parecem, mas são coisas diferentes: a árvore é mecânica e exaustiva até sua
   profundidade; o use-case é uma seleção feita por uma pessoa. Clique no `×` da migalha
   e o Fluxo volta ao use-case. *call tree from here* (*árvore de chamadas a partir
   daqui*), no painel de Símbolos, faz o mesmo a partir de qualquer arquivo ou símbolo.
5. **Leia o status.** Cada use-case carrega um chip: `human-verified`, `agent-verified`,
   `inferred`, `hypothesis` ou `outdated` (os valores não são traduzidos: são
   identificadores). O dropdown no painel muda o status **localmente** (marcado
   `· local`, guardado no `localStorage` do seu navegador); *export local statuses*
   (*exportar status locais*) transforma esses rascunhos num trecho JSON para aplicar ao
   registro num pull request. O arquivo de registro é a única verdade compartilhada —
   leia a seção sobre etiquetas antes de confiar num chip.

Esc sobe um nível de cada vez; a linha de dica no rodapé do mapa lista os gestos do
mouse.

## Construa você mesmo

Pré-requisitos: Python 3.10+, Node 22+, git.

```bash
git clone https://github.com/devanomaly/matryoshker.git && cd matryoshker
cd extractor && npm ci --ignore-scripts && cd ..        # o único passo que usa a rede
python pipeline/build.py \
    --repo examples/sample-drf --config config/example.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker.html --lang python
```

Abra `matryoshker.html` no navegador. O build imprime uma linha de contadores por etapa; a
que importa é `files=25 imports=33 ucs=5 hops=33` — `hops` conta os hops que resolveram
contra a extração, e qualquer hop que não resolveu é reportado em stderr logo acima. No
Windows, `python` pode resolver para um interpretador antigo; `py -3` é a grafia segura.

Os comandos são os mesmos do [QUICKSTART.md](../../QUICKSTART.md) (em inglês), que
também cobre: apontar o mesmo comando para o seu repositório, construir sem registro de
use-cases, quais caminhos de saída você controla (`--out`, e `--extract-out`, cujo padrão
`out/` é relativo ao diretório atual — o repositório alvo é apenas lido, mas se você
apontar essas flags para dentro dele os arquivos vão parar lá), e as quatro etapas do
pipeline separadas.

## Mapeie seu primeiro use-case

[first-use-case.md](first-use-case.md) adiciona um use-case ao fixture do começo ao fim:
escolher um comportamento, ler os arquivos, escrever a entrada do registro, decidir a
granularidade dos hops, escolher um status com honestidade, construir o mapa, conferir o
resultado no viewer e o que um revisor faz com isso. A entrada que ele escreve é real e
constrói limpa. Leia antes de escrever a sua primeira entrada para o seu repositório;
[CONTRIBUTING.md](../../CONTRIBUTING.md) tem a gramática de referência e
[data-contract.md](../data-contract.md) cada campo.

## O que as etiquetas dizem e não dizem

Verificado contra o pipeline e o viewer atuais; os detalhes, com comandos, estão em
[CONTRIBUTING.md](../../CONTRIBUTING.md#what-the-status-labels-establish).

- **Um status é uma afirmação de quem escreveu o registro, mantida por revisão, não por
  código.** `human-verified` deve entrar só quando uma pessoa releu os hops. Nada no
  pipeline garante isso: o arquivo de registro pode dizer `human-verified` diretamente,
  o dropdown do viewer oferece o valor a qualquer um como rascunho local, e o trecho
  exportado é JSON puro. A salvaguarda é o pull request que o aplica.
- **Nenhuma identidade de revisor, data ou evidência é registrada.** O contrato não tem
  campo para isso; o viewer mostra só o valor do status. Um time que queira esses dados
  pode acrescentar chaves próprias à entrada (chaves extras são preservadas e ignoradas
  pelo pipeline) ou confiar no histórico git do arquivo de registro.
- **Mudar o código não muda um status.** O pipeline copia `status` como está a cada
  build. O que ele detecta, em stderr, é um hop cujo **arquivo** não existe mais (o hop
  é descartado, e `--strict` transforma isso em código de saída 3) e um hop cujo
  **símbolo** não está mais declarado naquele arquivo (um aviso; o hop continua contando
  e sendo desenhado, e `--strict` não falha por ele). Um método renomeado aparece,
  portanto, como um aviso que você precisa ler, sob um status que ainda diz
  `human-verified`.
- **O commit e a data do cabeçalho são valores do config**, digitados em
  `config/<repo>.json`. Nada lê o git. Atualizá-los quando você reconstrói faz parte da
  rotina de manutenção, não é automático.
- **Mudanças de status no viewer são rascunhos num navegador só.** Vivem no
  `localStorage`, sob o repo e o commit do config, nunca chegam ao arquivo, e só viram
  mudança real quando alguém cola o trecho exportado no registro e faz o merge.

Nada disso torna as etiquetas inúteis: torna-as **revisáveis**. Uma entrada do registro é
uma afirmação pequena, versionada, com diff, e o mapa dá ao revisor as arestas de chamada
extraídas para conferi-la. A ferramenta não verifica autoria, não prova que um use-case
está completo e não o mantém atualizado sozinha. A rotina de manutenção que funciona com o
que existe hoje está em [CONTRIBUTING.md](../../CONTRIBUTING.md#keeping-a-registry-current)
e, aplicada a uma entrada, na seção 9 de [first-use-case.md](first-use-case.md).

## O que é extraído, o que você fornece

| Vem da extração (automático) | Vem de você ou de um agente (curado) |
|---|---|
| arquivos, contagem de linhas, pacotes (dois primeiros segmentos do caminho) | nomes de categoria e as regras de caminho que as atribuem (`config/`) |
| arestas de import entre arquivos | nome, ator, objetivo e status do use-case |
| classes, métodos, funções com faixas de linha | os hops: quais símbolos, em que ordem, um papel cada |
| arestas de chamada, resolvidas por heurística de nomes (mesmo arquivo, depois imports) | regras de negócio, testes, caminhos de falha (campos só de documentação) |
| rotas HTTP, quando há parser de rotas configurado (só Django/DRF hoje) | pontos de entrada declarados (um comando, um evento, um job agendado, uma rota que o parser não pegou) |
| o ranking *Stars*, o índice reverso arquivo → use-cases, as árvores de chamadas | o `commit` e a `date` do cabeçalho |

## Limites conhecidos

- O único parser de pontos de entrada é específico de Django/DRF (`router.register` +
  `path(...as_view)`); outros frameworks precisam de um parser novo (seção 6.3 do
  contrato). Sem parser, os pontos de entrada vêm só do registro.
- A extração exige Node 22+; o extractor é vendorado em `extractor/` (derivado mínimo da
  fase-1 do Understand-Anything, MIT, commit pinado em `extractor/NOTICE`). O QUICKSTART
  lista as linguagens que ele analisa.
- Arestas de chamada são resolvidas por heurística de nomes; chamadas dinâmicas ou
  reflexivas não aparecem. A resolução é afinada para Python: para as outras linguagens
  as arestas saem mais ruidosas ou mais ralas (seção 8 do contrato).
- Leque de hops (`branch:`/`ramo:`): sem aninhamento; duas alternativas laterais
  adjacentes se fundem num leque só; um irmão que termina no meio da cadeia ainda é
  desenhado reconvergindo; e o overlay do mapa é por arquivo, então um leque cujos irmãos
  moram no arquivo do próprio seletor não aparece lá — a cena Fluxo mostra.
- Um mapa é um snapshot de um build. Mantê-lo fresco por branch exige gerar o HTML no CI
  e hospedar; o workflow de Pages incluído faz isso só para o `main` deste repositório.
- A frescura do registro é uma rotina humana; o gate de CI que reconferiria as citações
  a cada PR está no roadmap ([`docs/ROADMAP.md`](../ROADMAP.md)), não implementado.

Roadmap, atribuição do extractor e licença (MIT): veja o [README em inglês](../../README.md).
