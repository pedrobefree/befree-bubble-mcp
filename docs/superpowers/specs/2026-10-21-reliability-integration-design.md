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

## Proveniência e adaptações

Merge 5e70624 preserva os 32 commits originais do fundamento. Cherry-picks com -x mantêm autor e SHA de origem para cf95377, 0e5f560, c758ae6, 0c46a0f, e6f4dec, 8960c9c, 9a7cb4f, 6dc3651, 40fff27, 8831a33, 6ced754 e 05cd031. O loader por pacote c758ae6 é dependência necessária para evitar colisões com outro bubble_cli. Seu script de atualização de instalações foi removido deste candidato: distribuição será bloco posterior.

Hunks de contexto que incluíam clone, savepoint, context_query, global expressions, modo core e documentação dessas capacidades foram omitidos quando ainda não existem nesta branch. Fixtures mantêm isolamento de configuração e stubs de sessão/listagem de versões, sem stub de savepoint inexistente. Snapshots refletem328 ferramentas nativas. Casos antigos do compilador agora provam key/object_id diferentes, preservando as asserções de resolução de nomes. A análise de tipos mantém o carregamento dinâmico da fronteira legada existente e verifica os160 arquivos não excluídos; nenhuma exclusão nova foi adicionada.
