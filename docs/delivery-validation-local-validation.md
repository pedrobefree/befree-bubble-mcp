# Entrega e validação: evidência local (2026-10-21)

PR: https://github.com/pedrobefree/befree-bubble-mcp/pull/47

Base: `1d7243e88f9695fe736d8fa9ce928eb45af67654` (#46).
Candidato validado: `2393ca86421e0ec76ffa577366fd2fed73d0e548`.
Código revisado: `166049a5ef39733af971bde0a2b2fbac4434cd91`.
O commit2393ca8 altera apenas seis confirmações de horário nos testes de agendamento.
Atualizações documentais posteriores não mudam o candidato executável validado.

Ambiente: macOS, Python3.11.9, Node20.20.2, configuração temporária e isolada.
O mesmo conjunto de comandos de `.github/workflows/ci.yml` foi executado localmente;
GitHub Actions continua desabilitado. O workflow não foi alterado.

| Etapa | Resultado |
| --- | --- |
| `python -m coverage run -m pytest -q` | PASS: 2765 aprovados, 2 UI opt-in ignorados, 700.60s |
| `python -m coverage report` | PASS: 49.6%, piso45.3%, branch coverage habilitado |
| `python -m bubble_mcp.cli.main smoke runtime --suite coverage` | PASS — fixture/synthetic: 2/2 |
| `python -m bubble_mcp.cli.main smoke runtime --suite agent-routing` | PASS — fixture/synthetic: 9/9 |
| `python -m ruff check src tests scripts` | PASS |
| `python -m mypy src` | PASS: 177 arquivos |
| `python scripts/audit_sensitive_paths.py .` | PASS |
| `python scripts/package_smoke.py --python python3.11` | PASS — fixture/synthetic: wheel instalado e servidor iniciado em ambiente isolado |
| `python scripts/setup_smoke.py` | PASS — fixture/synthetic: perfil incompleto esperado, scriptok=true |
| `npm test` com Node20 | PASS: 11/11 |
| `git diff --check 1d7243e` | PASS |

## Revisão e regressões

A revisão independente inicial bloqueou o candidato eea59a5. Foram corrigidos:

1. E2E live vindo da suíte, perfil ou override.
2. Navegação E2E fora da origem/versão selecionada, incluindo traversal, navegação direta e redirecionamentos antes de novas ações.
3. Clone sobre o original/irmãos existentes; reserva de slots estruturais no gerador de IDs.
4. Estado de impersonação sem versão e falso sucesso com cookie analytics; identidade e cookie de autenticação específicos do alvo.
5. Cópias de cookies com permissão pública; arquivos0600/diretórios0700.
6. Deploy diff confundindo booleanos e números JSON.
7. Savepoint de uma versão diferente da versão resolvida da escrita.

Nova revisão em166049a: sem P1/P2 pendentes; 112 testes focados executados pelo revisor.
A suíte completa revelou também uma corrida na fixture de agendamento: duas leituras do
relógio podiam produzir horários diferentes para preview e confirmação. O teste agora
reutiliza o horário salvo no preview, mantendo intacta a proteção preview_mismatch.
Revisão adicional em2393ca8: 16 testes de agendamento aprovados, sem P1/P2.
O pipeline completo acima passou após esse ajuste.

Outras regressões de integração cobrem fonte escalar no clone, ordem das guardas antes de
savepoints, sessão expirada no preview/impersonação, caminhos Windows E2E no POSIX e
colisões de campos source/since entre schemas. O catálogo nativo contém340 ferramentas,
sem dependência dos pacotes pessoais de extensão.

## Preservação e limites

O merge6aae52c preserva o prefixo original até19418ec; dez cherry-picks -x mantêm autoria e
referência da origem. A main original permanece em0fc8e5e; os dez arquivos não rastreados
continuam com os hashes do manifesto de preservação. Nenhum stash foi reaplicado.

E2E e impersonação: PASS — fixture/synthetic. Aceitação em app Bubble/navegador real:
NOT RUN. Os dois testes UI opt-in exigem configuração explícita e podem criar dados reais;
por isso ficaram ignorados no pipeline padrão. A suíte Python é código confiável, não um
sandbox. Guardas de navegação não substituem isolamento de código arbitrário ou autorização
para operações externas feitas por um caso.

Não houve merge, deploy ou execução de GitHub Actions. Autoupdate, tester, infraestrutura,
overrides de política main, expressões globais, core toolset e backend oficial ficam adiados.
