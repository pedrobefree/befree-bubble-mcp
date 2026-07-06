# Befree Bubble MCP Chrome Companion

Extensao local para capturar eventos do editor Bubble e envia-los para o servico local do Befree Bubble MCP.

Esta copia fica em `chrome-extension/` dentro do repositorio standalone do MCP para ser distribuida junto do projeto.

## Escopo

- Sem login por email e senha.
- Sem token de conta.
- Sem relay remoto.
- Comunicacao apenas com `http://127.0.0.1:<porta>`.
- Toggle para ligar/desligar a captura.
- Porta local configuravel.
- Capture key opcional enviada no header `X-Bubble-MCP-Capture-Key`.
- Resumo de eventos capturados, enviados, writes e erros.

## Como carregar no Chrome

1. Inicie o listener local do MCP:
   `bubble-mcp extension companion serve --port 3847`
2. Alternativamente, em um checkout de desenvolvimento:
   `PYTHONPATH=src python -m bubble_mcp.cli.main extension companion serve --port 3847`
3. Ou via npm:
   `npm run chrome:companion`
4. Abra `chrome://extensions`.
5. Ative `Developer mode`.
6. Clique em `Load unpacked`.
7. Selecione esta pasta:
   `/Users/pedroduarte/Documents/Development/Custom/aria/.external/befree-bubble-mcp/chrome-extension`.
8. Abra o popup `Befree Bubble MCP`.
9. Configure a porta do servico local, normalmente `3847`.
10. Configure a capture key se o listener local exigir.
11. Abra o editor Bubble com a extensao ativa.

Se o popup mostrar `Servico local nao encontrado`, o listener local nao esta rodando ou a porta configurada no popup nao corresponde a porta do comando acima.

## Uso com tool-authoring

Para capturar writes diretamente em uma sessao de aprendizado de tool:

1. Crie a sessao com `bubble-mcp tool-wizard start ...`.
2. Inicie o companion com `bubble-mcp extension companion serve --port 3847`, se ele ainda nao estiver rodando.
3. Execute as acoes no editor Bubble com a extensao ativa.
4. Ao finalizar, retorne ao Codex/MCP e finalize a sessao com `bubble-mcp tool-wizard finalize <session.id>`.

`tool-wizard start` marca a sessao criada como alvo ativo da extensao. O dev nao precisa informar o id na extensao nem rodar uma etapa separada de ativacao. Para recuperar uma sessao existente, rode `bubble-mcp tool-wizard activate <session.id>`. O parametro `--tool-session-id <session.id>` no companion continua disponivel como override explicito.

## Endpoints expostos pelo listener local

- `GET /health`
- `POST /v1/bubble/crawler/ingest`
- `POST /v1/bubble/crawler/write-ingest`

O listener local aceita JSON e, quando a capture key estiver configurada, valida o header `X-Bubble-MCP-Capture-Key`.
