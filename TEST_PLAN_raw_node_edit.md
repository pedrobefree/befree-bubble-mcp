# Plano de teste — feat/raw-node-edit-primitives

Branch sob teste: `feat/raw-node-edit-primitives` @5e70624 (repo `DEV/be-free-mcp`).

## Pré-requisito (obrigatório)

O `~/.claude.json` foi repontado: o MCP `befree-bubble-mcp` agora roda do venv de
`DEV/be-free-mcp` (install editável, o código da branch é executado direto).

Antes: `DEV/auton/befree-bubble-mcp/.venv/Scripts/python.exe`
Agora: `DEV/be-free-mcp/.venv/Scripts/python.exe`

**Cada sessão do Claude Code precisa ser reiniciada** para subir o servidor novo. Uma
sessão já aberta continua falando com o processo antigo e não vai enxergar
`bubble_live_node_read` nem `bubble_node_edit`.

Checagem rápida após reiniciar: as tools `bubble_live_node_read`, `bubble_node_edit` e
`verify_write` devem estar disponíveis. Se não aparecerem, o servidor antigo ainda está no ar.

Regressão conhecida: o commit `ab6e468` ("merge every context root when listing workflows")
está só na branch `fix/workflow-root-overlay-shadowing` e **não** está nesta branch. Se o
listar-workflows vier incompleto em app com múltiplos roots de contexto, é essa ausência,
não um bug novo.

## Perfis disponíveis

- `auto-on` — app `auto-on`, versão `live`
- `mcp-test` — app `mcp-test-app`, versão `test`

Testes destrutivos só em `mcp-test`. Em `auto-on` rodar apenas leitura e dry-run
(`execute=false`).

## 1. `bubble_live_node_read`

Lê um node cru do editor Bubble em execução.

- **1.1 leitura feliz** — pointer para uma action existente, ex.
  `["api","<wf_id>","actions","0"]`. Esperado: corpo cru na forma codificada (não a forma
  traduzida do export), sem tradução de root key.
- **1.2 pointer de container** — pointer para o mapa de actions
  `["api","<wf_id>","actions"]`. Deve devolver o mapa, e escrita nesse pointer deve ser
  recusada (ver 2.4).
- **1.3 pointer inexistente** — resultado estruturado de erro, nunca exceção crua.
- **1.4 `read_timeout_sec` inválido** — `0`, `-5`, `"abc"`. Esperado
  `{"ok": false, "error": "invalid_read_timeout_sec"}` nos três casos.
- **1.5 readiness/retry** — disparar a leitura com o editor ainda carregando. Deve
  reinicializar a página e tentar de novo em vez de falhar direto; a detecção de
  `NotReadyError` é estrutural, não por texto de mensagem.
- **1.6 identidade do app** — a verificação de app_id acontece na mesma avaliação da
  leitura. Passar `app_id` que não bate com o editor aberto deve falhar de forma explícita,
  não devolver o node do app errado.
- **1.7 perfil deslogado** — deve ser detectado e reportado como tal.

## 2. `bubble_node_edit`

Ciclo read-patch-write-verify sobre um node vivo.

- **2.1 `op="patch"` dry-run** — `execute=false`, pointer para UMA action
  (`["api","<wf_id>","actions","3"]`), `leaf_pointer` para uma folha. Nada deve ser escrito;
  o payload previsto deve aparecer no resultado.
- **2.2 `op="patch"` execute** — mesmo caso com `execute=true` em `mcp-test`. Esperado:
  escrita + re-leitura provando que o valor mudou. O resultado carrega `session_id` e a
  forma de intent SetData/Update com índice coerente.
- **2.3 `op="reorder"`** — pointer no mapa de actions, `order` com todas as chaves
  existentes exatamente uma vez. Deve renumerar o mapa e repontar `_index.id_to_path`.
- **2.4 `reorder` que perde passo** — `order` faltando uma chave, ou com chave repetida.
  Deve ser recusado, não escrever.
- **2.5 pointer de container em patch** — deve ser recusado (patch em container é proibido).
- **2.6 corpo do node** — todo node escrito passa por guard; body malformado é recusado
  antes da escrita.
- **2.7 overlay de mutação** — após um `execute` bem-sucedido, o overlay é gravado com o
  `app_id` correto (fallback de `app_id` no overlay foi corrigido).

## 3. Verificação pós-escrita / `verify_write`

`/appeditor/write` devolve HTTP 200 para qualquer corpo, então o 200 não prova nada.

- **3.1 verificação universal** — tools do aria-runtime devem re-ler e provar que a escrita
  entrou. Cobrir pelo menos `add_action` e `log_the_user_in`, onde havia três defeitos de
  escrita silenciosa.
- **3.2 `verify` é control arg** — `verify` não pode vazar para o payload da tool; é
  argumento de controle do runtime.
- **3.3 falso negativo** — escrita que de fato entrou não pode ser reportada como falha.
- **3.4 evidência preservada** — em falha de verificação, o corpo lido e o payload enviado
  devem sobreviver no resultado para diagnóstico (antes eram destruídos).
- **3.5 `verify_write` direto** — chamar a tool isolada sobre uma escrita conhecida boa e
  uma conhecida ruim.

## 4. Resolução de contexto (key vs id)

- **4.1 resolver de contexto** — deve preferir path/key real do node ao `bubble_id`.
- **4.2 page key** — derivada do path real do editor da página crawleada, não do id dela.
- **4.3 workflow por key** — resolução endereçada por key confia no chamador; não deve ser
  sobrescrita pelo discovery.
- **4.4 contexto do perfil** — quando nenhum contexto é passado, carrega o do perfil.

## Como reportar

Para cada item: id do teste, tool chamada, argumentos, resultado (ok/erro), e se bateu com o
esperado. Falha: colar a linha decisiva do erro e o pointer usado. Não colar dump inteiro.
