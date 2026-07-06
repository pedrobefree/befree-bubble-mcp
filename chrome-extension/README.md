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

1. Abra `chrome://extensions`.
2. Ative `Developer mode`.
3. Clique em `Load unpacked`.
4. Selecione esta pasta:
   `/Users/pedroduarte/Documents/Development/Custom/aria/.external/befree-bubble-mcp/chrome-extension`.
5. Abra o popup `Befree Bubble MCP`.
6. Configure a porta do servico local, normalmente `3847`.
7. Configure a capture key se o listener local exigir.
8. Abra o editor Bubble com a extensao ativa.

## Endpoints esperados no servico local

- `GET /health`
- `POST /v1/bubble/crawler/ingest`
- `POST /v1/bubble/crawler/write-ingest`

O listener local deve aceitar JSON e, quando a capture key estiver configurada, validar o header `X-Bubble-MCP-Capture-Key`.
