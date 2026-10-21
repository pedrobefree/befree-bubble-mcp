# Integração gradual: confiabilidade

Decisão aprovada na conversa: usar pedrobefree/main como base canônica e integrar primeiro confiabilidade, preservando alterações locais e autoria/histórico do fork. Entregar PR para revisão; não fazer merge nem deploy.

## Contrato

- Manter os contratos estruturais/internal IDs e patches parciais dos PRs #44/#42.
- Integrar leitura de nós e ciclo read/patch/write/read-back necessários à confirmação de escrita. Bytes confirmados não significam renderização aprovada.
- Verificar sessão antes de trabalho dependente do editor; login deve provar acesso ao app, não apenas presença de cookie.
- Resolver versão alvo explicitamente, incluindo headers de editor; live nunca recebe edição. Main só recebe escrita quando não existem branches; falha na descoberta mantém main bloqueada.
- Atualizar perfil campo a campo sem perder campos omitidos. Configuração de teste temporária, sem contas pessoais ou rede real nos testes.
- Preservar a ancestralidade do primeiro bloco do fork por merge até 5e70624. Transportar correções posteriores selecionadas com autoria original e trailer de origem, sem importar E2E, savepoints, duplicação, tester, autoupdate ou integração oficial.
- Executar todos os comandos de .github/workflows/ci.yml localmente, com Python3.11. GitHub Actions continua desabilitado por orientação do mantenedor.

## Critérios

Regressões de escritas parciais, contratos de referência, compilador, schemas, sessão e política passam. Suíte inteira, cobertura >=45.3%, lint, tipos, auditoria, smokes e Node passam. Revisão independente sem P1/P2 pendente. Documentar a distinção entre teste sintético e prova Bubble real.
