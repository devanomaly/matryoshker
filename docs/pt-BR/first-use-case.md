# Mapeie seu primeiro use-case

> Versão em português de [`docs/first-use-case.md`](../first-use-case.md), mantida em
> paridade com ela: mesmos comandos, mesmos contadores, mesmas mensagens. Os nomes de
> arquivo, símbolos e textos do registro ficam em inglês porque são o fixture real.

Este passo a passo adiciona um use-case ao fixture incluído, `examples/sample-drf`, da
primeira pergunta até o pull request revisado. Tudo aqui foi executado contra o pipeline
atual; os contadores e as linhas de stderr citadas são as que você deve ver. Reserve uns
trinta minutos, com o build da demo do README já funcionando.

Dois tipos de orientação se misturam abaixo, e importa qual é qual:

- **Contrato** — o que o pipeline exige ou faz. Dito como tal, apontando para
  [`docs/data-contract.md`](../data-contract.md).
- **Prática** — como este projeto escreve registros para que continuem conferíveis. Bons
  padrões, não regras que a ferramenta impõe.

## 0. O que é uma entrada de use-case

Um use-case é um comportamento que um ator obtém do sistema, explicado como a lista
ordenada dos símbolos por onde ele passa — os *hops* — cada um com um papel de uma linha.
É uma afirmação escrita por uma pessoa ou por um agente, guardada como JSON no
repositório e desenhada pelo viewer por cima do grafo que o extractor produziu. O
pipeline confere que o **arquivo** de cada hop existe na extração e avisa quando o
**símbolo** não existe; ele não confere a ordem, os papéis nem se a lista está completa.
Para isso existe a revisão.

## 1. Escolha o comportamento

**Comportamento:** um membro renova um empréstimo antes do vencimento.
**Ator:** membro da biblioteca. **Objetivo:** ficar com um exemplar por mais um período de
empréstimo quando ninguém está esperando pelo título.

Por que este: é um comportamento real com uma regra de negócio própria (renovações têm
teto e são bloqueadas por fila), é pequeno, e o registro do fixture ainda não o tem. As
cinco entradas que já estão em `examples/sample-drf/usecases.json` são as que você vê na
demo.

Prática: parta de um comportamento que um stakeholder nomearia, não de um módulo.
"Renovar um empréstimo" é um use-case; "`LoanService`" não é.

## 2. Leia o código, com o mapa aberto

Construa o fixture como no README e abra o mapa. Digite `renew` na caixa de busca: a
lista de resultados mostra a função `can_renew` em `policies.py`, o método
`LoanService.renew` em `loan_service.py` e três símbolos de teste. Clique no método; a
cena *Symbols* abre em `lending/services/loan_service.py` com `renew` selecionado, e o
painel direito diz:

```
Symbol
lending/services/loan_service.py
renew
Calls (2)
  can_renew in policies.py :70
  loan_period_days in policies.py :72
Called by (0)
```

Esse painel é a extração falando: `renew` chama duas funções de política, e **nada no
fixture chama `renew`** — nenhuma view, nenhum handler. Guarde esse fato; ele decide o
status mais adiante.

Agora leia os arquivos. Estes foram inspecionados para esta entrada:

| Arquivo | O que foi lido | O que contribui |
|---|---|---|
| `lending/services/loan_service.py` | `LoanService.renew` | a decisão (`can_renew`), o deslocamento da data de devolução, o save no empréstimo |
| `lending/domain/policies.py` | `can_renew`, `loan_period_days`, `MAX_RENEWALS` | a regra: nenhuma reserva aberta, menos de duas renovações; o período por tier |
| `lending/models.py` | campos `due_date`, `renewal_count` de `Loan` | onde o estado é gravado |
| `catalog/views.py`, `lending/handlers/*.py` | busca por quem chama `renew` | ninguém — não há ponto de entrada |
| `tests/test_policies.py` | `RenewalTests` | cobre só `can_renew`, não o método do serviço |

## 3. Escreva a entrada

Acrescente este objeto ao array em `examples/sample-drf/usecases.json` (depois da última
entrada, dentro do `]` final):

```json
{
  "name": "Member renews a loan before it is due",
  "actor": "Library member",
  "goal": "Keep a copy for one more loan period when nobody is waiting for the title",
  "hops": [
    "lending/services/loan_service.py:LoanService.renew — refuses when the title has a queue or the renewals are used up",
    "lending/domain/policies.py:can_renew — the rule: no open reservation and fewer than MAX_RENEWALS",
    "lending/domain/policies.py:loan_period_days — how far the due date moves, by member tier",
    "lending/models.py:Loan — stores the new due date and the renewal count"
  ],
  "async_legs": [],
  "failure_paths": [
    "a reservation is open for the title -> renew returns None, nothing is saved",
    "renewal_count is already MAX_RENEWALS -> renew returns None, nothing is saved"
  ],
  "rules": [
    "no renewal while another member is waiting for the title",
    "at most two renewals per loan (MAX_RENEWALS)"
  ],
  "tests": ["tests/test_policies.py::RenewalTests"],
  "seam_crossing": false,
  "status": "inferred",
  "notes": "Nothing in the fixture calls LoanService.renew: no view, no handler. The hops are read from the code; the actor is the intended one, not an observed caller."
}
```

Contrato, para você saber o que sustenta peso (contrato §4.1):

- só `name` é obrigatório, e precisa ser único no arquivo;
- o pipeline lê `name`, `actor`, `goal`, `entry_points`, `hops`, `rules`,
  `seam_crossing`, `status`. `async_legs`, `failure_paths`, `tests`, `notes` e qualquer
  outra chave ficam no arquivo e são ignorados — documentação para o próximo leitor;
- um hop é `"<caminho/arquivo.ext>[:<Símbolo>] — <papel>"` com travessão (§5.1). Os
  caminhos são relativos à raiz do repositório mapeado;
- `status` ausente significa `inferred`.

Prática: escreva o papel no presente, com menos de umas catorze palavras, dizendo o que
aquele hop *decide ou faz para este comportamento* — não o que a função faz em geral.
Preencha `failure_paths` e `tests` enquanto o código está aberto; custa pouco agora e
muito depois.

## 4. Por que cada hop está ali, e o que ficou de fora

| Hop | Por que é um hop |
|---|---|
| `LoanService.renew` | o comportamento entra aqui; é dono da decisão e da escrita |
| `policies.can_renew` | a regra que pode recusar o comportamento; quem for mudar o teto precisa achar isto |
| `policies.loan_period_days` | a segunda regra, que decide *quanto* a data se desloca; uma preocupação diferente da primeira |
| `models.Loan` | onde o estado é gravado; quem pergunta "o que mudou no banco" para aqui |

Deixado de fora de propósito:

- `loan.save(update_fields=[...])` — detalhe de implementação do último hop, visível no
  momento em que você abre o código;
- `timedelta` — chamada de biblioteca, não uma decisão;
- a checagem de fila `loan.copy.book.reservations.filter(state="open").exists()` — uma
  expressão de ORM sem símbolo próprio; está dobrada no papel do hop 1 ("has a queue")
  em vez de citada como hop;
- `loan_period_days` lendo `LOAN_PERIOD_BY_TIER` — um nível abaixo do que o leitor
  precisa; a cena Symbols mostra de qualquer jeito.

Prática, a regra de granularidade deste projeto: **um hop por fronteira cruzada ou
decisão tomada**. Cite um símbolo quando quem quiser mudar o comportamento teria que
abri-lo; pule quando a cena Symbols já o mostra de graça como chamada interna. De quatro
a oito hops é o tamanho usual. Se você se pegar listando toda função do caminho, está
transcrevendo a árvore de chamadas — o viewer já desenha isso a partir da extração
(*call tree from here*); o use-case vale a pena porque é uma seleção.

Dois hops no mesmo arquivo (`policies.py`) não são problema: a cena Flow desenha os dois,
e o overlay do mapa funde-os num badge só naquele arquivo. Essa fusão é uma regra do
viewer, não motivo para tirar um hop.

## 5. Escolha o status com honestidade

A entrada diz `inferred`. O raciocínio, contra as definições do contrato §4.2:

- não `hypothesis`: cada hop foi lido no código e a extração concorda com a estrutura de
  chamadas (`renew` → `can_renew`, `loan_period_days`);
- não `human-verified`: essa etiqueta é reservada, pela prática deste projeto, a um
  **segundo** leitor que relê os hops e os abençoa na revisão. O autor não se abençoa.
  Há também uma pergunta em aberto que o autor não fecha sozinho: nada chama `renew`,
  então "um membro renova" é o ator *pretendido*, não um observado. Isso está escrito em
  `notes`, onde o revisor vai ver;
- não `agent-verified`: nenhum pipeline de agente produziu ou conferiu esta entrada. Se
  tivesse, pararia nesse valor — um agente nunca escreve `human-verified`
  (CONTRIBUTING.md).

Nada na ferramenta confere isso: o arquivo poderia dizer `human-verified` e o pipeline
o copiaria como está. O status é uma afirmação que você faz aos seus revisores.

**Ponto de entrada.** A entrada não tem a chave `entry_points`. Contrato (§6.2): um
use-case sem ponto de entrada declarado resolvível recebe seu **primeiro hop resolvido**
como ponto de entrada de fallback, do tipo `other`, rotulado com o nome do use-case.
Como ninguém chama `renew`, inventar uma rota HTTP aqui seria mentira; o fallback é a
representação honesta, e o painel vai mostrá-lo em *Other*.

## 6. Construa o mapa

Da raiz do repositório, com o extractor instalado (`npm ci --ignore-scripts` em
`extractor/`, uma vez):

```bash
python pipeline/build.py --repo examples/sample-drf --config config/example.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker.html --lang python --strict
```

Saída esperada (stderr e stdout intercalados; as linhas `build.py: step k/4` omitidas):

```
files=25 imports=33 ucs=6 hops=37 -> out/data.json (10KB)
entry points: 4 from parsers, 5 declared, 2 fallback, 2 duplicates merged
entry_points=9 calls: internal=49 cross=71 -> out/extra.json (6KB)
matryoshker.html: 98KB
```

Leia os contadores contra o que você escreveu: `ucs=6` (cinco mais o seu), `hops=37`
(33 mais os seus quatro), `2 fallback` (o fixture já tinha um use-case sem ponto de
entrada; o seu é o segundo). Nenhuma linha começando com `UC ` apareceu em stderr: o
arquivo de todo hop resolveu e todo símbolo foi encontrado no seu arquivo.

### Como um erro aparece

As duas variantes abaixo foram executadas. **Um símbolo errado** — hop 1 citado como
`LoanService.extend` em vez de `LoanService.renew`:

```
UC Member renews a loan before it is due: 4/4 hops resolved
  unverified symbol [LoanService.extend not declared in lending/services/loan_service.py]: lending/services/loan_service.py:LoanService.extend — refuses when the title has a queue
files=25 imports=33 ucs=6 hops=37 -> ...
```

O hop ainda conta (`4/4`, `hops=37`), ainda é desenhado no mapa com o nome errado, e o
código de saída é **0 mesmo com `--strict`**. O único rastro é aquela linha de stderr.
Leia o stderr.

**Um arquivo errado** — hop 2 citado como `lending/domain/renewal_policy.py:can_renew`:

```
UC Member renews a loan before it is due: 3/4 hops resolved
  dropped [file not found in the extraction]: lending/domain/renewal_policy.py:can_renew — the rule
total: 36/37 hops resolved (1 dropped in 1 use-cases)
strict: 1 citations dropped
```

O hop é descartado (`hops=36`) e, com `--strict`, o build para na etapa 2 com código de
saída 3 e não escreve HTML. Sem `--strict` ele sai com 0 e constrói um mapa com três
hops. Contrato: §5.4, §5.5 e §11.

## 7. O que você deve ver

Abra `matryoshker.html`.

- Barra lateral, *Use-cases*: seis entradas; a sua é a última, com chip `inferred`.
- Barra lateral, *Entry points*, grupo *Other*: uma entrada chamada *Member renews a loan
  before it is due*, `LoanService.renew · loan_service.py` — o fallback.
- Clique no use-case. *Packages*: três badges — `1.` em `loan_service.py`, `2.` em
  `policies.py`, `3.` em `models.py` — porque os dois hops de `policies.py` dividem um
  arquivo. O painel direito lista os quatro hops com seus papéis e as duas regras.
- *Flow*: quatro caixas, de `1.` a `4.`, na ordem do registro.
- Clique no quadrado de `loan_service.py`: *Use-cases passing here (4)* — três use-cases
  existentes e o seu. Este é o índice reverso arquivo → use-cases.
- *open symbol map ⌄*, depois clique em `renew`: *Calls (2)* `can_renew`,
  `loan_period_days`; *Called by (0)*.

## 8. Como um revisor confere

O pull request contém um hunk em `usecases.json`. O revisor:

1. **Abre cada símbolo citado** no código e lê o papel contra ele. Quatro hops, quatro
   leituras. Um papel que descreve a função em geral em vez do seu lugar neste
   comportamento ganha um comentário.
2. **Compara a lista de hops com a extração.** No mapa, o painel de Symbols de `renew`
   lista o que ele chama. Tudo o que o código chama e não é hop precisa ser uma omissão
   deliberada com a qual o revisor concorda (seção 4); tudo o que é citado e o código não
   chama está errado.
3. **Confere o status contra a regra.** `inferred`, de um autor humano que leu o código:
   correto. O revisor também lê `notes` e o `entry_points` ausente e concorda que são a
   representação honesta.
4. **Abençoa, ou não.** Se o revisor releu os hops e concorda, o PR (ou um commit
   seguinte) muda `"status": "inferred"` para `"human-verified"`. A mesma edição pode
   sair do viewer: escolha o valor no dropdown, clique em *export local statuses*, cole
   o valor do trecho no arquivo. De um jeito ou de outro, a bênção é um diff no registro;
   quem a fez e quando está no histórico git e em nenhum outro lugar.

Um revisor que não releu os hops não abençoa. Aprovar o PR com `inferred` intacto é um
desfecho perfeitamente bom.

## 9. Quando o código muda

O registro não acompanha o código sozinho. Depois de uma mudança que toca qualquer
arquivo citado por um use-case, reconstrua com `--strict` e leia o stderr:

| Mudança | O que o build diz | O que você faz |
|---|---|---|
| `renew` renomeado para `extend` | `unverified symbol [LoanService.renew not declared in ...]`, saída 0 | corrija a citação; o status só fica se o comportamento ficou |
| `loan_service.py` movido ou dividido | `dropped [file not found ...]`, saída 3 com `--strict` | corrija o caminho (ou acrescente o diretório a `hop_path_prefixes` no config, §5.3) |
| uma view passa a chamar `renew` | nada — a extração muda, o registro não | acrescente `"entry_points": ["http: ... (catalog/views.py:BookViewSet)"]`, talvez um hop; `notes` ficou velho |
| `MAX_RENEWALS` vira 3 | nada | o texto da regra e o papel do hop 2 ficaram velhos; só uma leitura pega isso |
| a checagem de fila é removida | nada | o papel do hop 1 agora está errado: ponha `status` em `outdated` no mesmo PR da mudança de código, ou corrija a entrada; não a apague |

Dois hábitos tornam isso barato: mexa no registro no **mesmo PR** de uma mudança num
arquivo citado, e atualize `commit` e `date` em `config/<repo>.json` quando reconstruir,
já que o cabeçalho mostra esses valores e nada lê o git por você.

## 10. Para o seu repositório

Os mesmos passos valem com dois arquivos seus. `config/<repo>.json` (copie
`config/example-ddd.json` se você não tem rotas Django/DRF; `config/example.json` se
tem) e `data/<repo>/usecases.json`, que pode começar como `[]`. Construa sem `--ucs`
primeiro para ver só o mapa extraído, escolha o primeiro comportamento a partir do que
vê, e adicione-o. O [QUICKSTART.md](../../QUICKSTART.md) tem os comandos e os caminhos
que você controla; o [CONTRIBUTING.md](../../CONTRIBUTING.md) a gramática de hops e
pontos de entrada, a regra de status e a rotina de manutenção; o §5.1 do contrato os
prefixos `branch:`/`ramo:` e `seam:`/`costura:` para fluxos que bifurcam ou cruzam uma
fronteira de processo.
