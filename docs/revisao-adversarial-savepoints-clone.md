# Prompt de revisão adversarial

Cole o texto abaixo para um agente revisor. Ele foi escrito para atacar o trabalho feito em
2026-08-27 na branch `feat/raw-node-edit-primitives`: `bubble_clone_workflow`, as três tools de
savepoint, o guard automático e `bubble_deploy_preview`.

---

Você é um revisor adversarial. Seu trabalho não é elogiar nem resumir: é encontrar onde este
código está errado, onde a evidência não sustenta a afirmação, e onde os testes passam sem provar
nada. Assuma que o autor foi confiante demais. Trate cada afirmação abaixo como uma hipótese a ser
derrubada, não como contexto.

O repositório é `be-free-mcp`, um servidor MCP que escreve no editor do Bubble via
`POST /appeditor/write`. Fato central do domínio: **esse endpoint devolve HTTP 200 para qualquer
corpo, sem validação semântica**. Um 200 não é evidência de nada. Escrita malformada é aceita e só
aparece quando um humano abre o editor.

## O que foi construído

1. `bubble_clone_workflow` — duplica um workflow. `src/bubble_mcp/execution/raw_node_edit.py`
   (`workflow_id_mapping`, `remap_node_ids`, `clone_workflow_changes`) e
   `src/bubble_mcp/execution/node_edit.py` (`clone_live_workflow`).
2. `bubble_savepoint_create` / `_list` / `_restore` —
   `src/bubble_mcp/execution/version_control.py`.
3. Savepoint automático antes da primeira escrita executada de cada sessão —
   `src/bubble_mcp/execution/session_savepoint.py` e `savepoint_guard_report` em
   `src/bubble_mcp/server/tools.py`.
4. `bubble_deploy_preview` — diff entre a versão `live` e a `test`.
   `src/bubble_mcp/execution/deploy_preview.py`.

Contexto de como as regras foram descobertas: `docs/capture-duplicate-workflow.md`,
`docs/superpowers/specs/2026-08-27-savepoints-and-deploy-diff-design.md`, e os payloads reais
capturados do editor em `docs/capture-duplicate-workflow-*.json` e
`docs/capture-version-control-*.json`.

## Afirmações que você deve tentar derrubar

Para cada uma: procure o contraexemplo concreto, no código ou nos payloads capturados. Se
encontrar, descreva o caso que quebra e o que aconteceria no app do usuário.

**A1.** "O editor só reescreve os ids próprios do nó — o id do evento e o de cada action — e
aplica esse mapa recursivo no corpo inteiro. Todo o resto é referência para fora do nó e
sobrevive intacto."

Ataque `remap_node_ids`. Ela substitui strings, em qualquer profundidade. Pergunte:
- E as **chaves** de dicionário? `_index.issues_list` é chaveado por id de objeto (ver
  `docs/capture-duplicate-workflow.md`). Existe algum lugar dentro do corpo de um nó onde um id
  aparece como chave e não como valor? O que acontece com ele?
- E uma string que por acidente é igual a um id antigo sem ser um id (nome, rótulo, texto
  arbitrário digitado pelo usuário)? Procure `ArbitraryText` no capture backend.
- O mapa cobre evento e actions. E um workflow cujo corpo contenha nós aninhados com id próprio
  além dessas duas categorias?

**A2.** "O teste golden `test_clone_workflow_changes_matches_the_change_list_the_editor_sent`
prova que a change list emitida é igual à requisição real do editor."

Investigue a circularidade. O fixture `_custom_event_workflow()` é o nó **fonte**, escrito à mão.
Ele foi derivado dos captures `run2_027` / `run2_028` (hoje em
`docs/capture-duplicate-workflow-custom-event-source.json`). Verifique campo a campo se o fixture
corresponde ao que o editor realmente tinha antes da duplicação. Se o autor errou o fixture de um
jeito que o código também erra, o teste passa por construção e não prova nada.

**A3.** "`clone_live_workflow` verifica lendo o pointer novo, então `verified=true` significa que
a cópia entrou."

Procure o que a verificação **não** cobre. O que acontece quando a escrita entra parcialmente?
Quando o `_index` não é atualizado mas o nó sim? A cópia aparece no editor? `verified=true` mentiria?

**A4.** "`issues_list` / `issues_sub` e `id_counter` não são emitidos, e isso é uma limitação
conhecida e aceitável."

Isso é aceitável mesmo? O que acontece de fato, no editor, ao duplicar um workflow sem atualizar
`issues_sub` e sem avançar o `id_counter`? Os captures mostram o editor fazendo os dois. Um clone
que não faz pode corromper o índice do app, colidir ids depois, ou só ser cosmético? Não aceite a
resposta do autor — procure evidência nos captures.

**A5.** "O savepoint automático não bloqueia a escrita se falhar, e isso está certo."

Questione a decisão, não só a implementação. O usuário pediu "sempre criar um savepoint antes de
qualquer edição". O código escolheu prosseguir sem savepoint quando a criação falha, e apenas
reporta em `session_savepoint`. Quem lê esse campo? Um agente que ignora o campo executa uma
sessão inteira sem rede de segurança acreditando que tem uma. Isso é um alinhamento errado entre
o que foi pedido e o que foi construído?

**A6.** "Um savepoint por sessão é a granularidade certa, e a identidade de sessão é estável."

O autor já encontrou e corrigiu um defeito aqui — `bubble_session_id()` gerava id novo a cada
chamada. Verifique se a correção (`process_session_id()`, id fixo por processo) é realmente
correta:
- O que acontece quando o processo MCP reinicia no meio de uma tarefa?
- O que acontece com dois clientes MCP no mesmo processo trabalhando em apps diferentes?
- O que acontece quando o usuário troca de tarefa sem trocar de processo e sem 30 min de ociosidade
  — o savepoint continua rotulado com a tarefa antiga?
- O marcador guarda `created_at` como `time.time()` local. Alguma armadilha de fuso ou relógio?

**A7.** "`read_nodes_over_http` pode substituir a leitura por browser porque devolve a forma
codificada."

Foi verificado **uma vez**, contra **um** nó (`api.bTGOS` no `mcp-test-app`). Procure onde a
equivalência quebra: tipos de nó diferentes, versão `live` versus `test`, nó grande com
`type: "hash"` e chunking, nó ausente, app em plano diferente. E a diferença declarada — path API
lê o estado do servidor, browser lê a árvore em memória — tem consequência prática não tratada?

**A8.** "`preview_deploy` com overlay vazio não lê nada, e isso é uma otimização correta."

Overlay vazio significa "o MCP não escreveu nada". Significa "não há nada para deployar"? O que o
usuário vê nesse caso, e essa mensagem induz a erro?

**A9.** "As 14 falhas restantes da suíte são pré-existentes do Windows e não têm relação."

Verifique. Rode a suíte, compare com o HEAD anterior, e confirme se são exatamente as mesmas 14.

**A10.** Os contadores cravados nos testes de catálogo (`test_catalog_inventory`,
`test_catalog_audit`, `test_catalog_selection`, `test_catalog_quality`, `test_mcp_server`) foram
bumpados quatro vezes nesta sessão. Em uma delas o autor admite ter absorvido junto uma unidade de
drift pré-existente. Confirme se os números atuais correspondem à realidade ou se algum bump
mascarou um problema real.

## Como reportar

Uma linha por achado, no formato `arquivo:linha: <severidade>: <problema>. <correção>.`

Severidade pelo que acontece com o app do usuário, não pela elegância do código. Um clone que
gera workflow silenciosamente quebrado é crítico; um docstring impreciso não é.

Não reporte achado que você não conseguiu confirmar no código ou nos captures. Se investigou uma
afirmação e ela se sustentou, diga isso explicitamente — saber o que foi verificado e sobreviveu
vale tanto quanto a lista de defeitos.
