# Entrega e validação: evidência local (2026-10-21)

PR: https://github.com/pedrobefree/befree-bubble-mcp/pull/47

Base: `1d7243e88f9695fe736d8fa9ce928eb45af67654` (#46).
Candidato executável validado: `0b1bd6698e13917fe987690b66fea395ced310df`.
Revisão independente aprovada nesse mesmo candidato, sem P1/P2 pendentes.
Atualizações documentais posteriores não mudam o código/testes executados.

Ambiente: macOS, Python3.11.9, Node20.20.2 e configuração temporária isolada.
O pipeline de `.github/workflows/ci.yml` foi executado localmente. GitHub Actions
continua desabilitado; o workflow não foi alterado.

| Etapa | Resultado |
| --- | --- |
| `python -m coverage run -m pytest -q` | PASS: 2789 aprovados, 2 UI opt-in ignorados, 646.18s |
| `python -m coverage report` | PASS: 49.7%, piso45.3%, branch coverage habilitado |
| `python -m bubble_mcp.cli.main smoke runtime --suite coverage` | PASS — fixture/synthetic: 2/2 |
| `python -m bubble_mcp.cli.main smoke runtime --suite agent-routing` | PASS — fixture/synthetic: 9/9 |
| `python -m ruff check src tests scripts` | PASS |
| `python -m mypy src` | PASS: 177 arquivos |
| `python scripts/audit_sensitive_paths.py .` | PASS |
| `python scripts/package_smoke.py --python python3.11` | PASS — fixture/synthetic: wheel instalado e servidor iniciado em ambiente isolado |
| `python scripts/setup_smoke.py` | PASS — fixture/synthetic: perfil incompleto esperado, script ok=true |
| `npm test` com Node20 | PASS: 11/11 |
| `git diff --check 1d7243e` | PASS |

## Reparos e nova revisão

A revisão após abertura do PR bloqueou o merge por dois P2:

1. O clone recebia test quando guarda/savepoint resolviam a versão da sessão.
   Agora leituras, escrita e savepoint seguem chamada > perfil > sessão > test.
2. O default de versão do perfil virava override E2E e ignorava a branch da suíte.
   Agora branch explícita > app_version explícita > suíte > perfil > test.
   O scaffold também mantém a branch ao acrescentar casos sem override.

Na revisão dos reparos foi encontrado um P2 adjacente: o scaffold promovia o
app_id padrão do perfil a override e trocava o app explícito de uma suíte existente.
Agora conserva esse app_id, salvo substituição explícita; suítes novas continuam
herdando app/branch do perfil no resolver.

Os commits ef51286 e0b1bd66 incluem24 regressões em
`tests/unit/test_delivery_version_dispatch.py`, exercitando dispatcher, clone com
transporte sintético, preview real do runner e manifestos persistidos pelo scaffold.
Antes dos reparos, 9 cenários reproduziram os dois P2 e outros3 a troca de app_id.
Depois: 187 testes focados aprovados. A revisão independente final executou134
regressões focadas e não encontrou P1/P2 pendentes. O pipeline completo acima passou.

## Integração e histórico

A revisão inicial da integração também corrigiu E2E live/navegação fora da versão,
clone sobre original/irmãos ocupados, cookies sem escopo de versão/autenticação,
permissões dos snapshots, diferenças JSON bool/número e versão do savepoint.
Outras regressões cobrem fonte escalar em clone, ordem das guardas, sessão expirada,
caminhos Windows no POSIX e colisões source/since entre schemas.

O pipeline anterior em2393ca8 tinha2765 testes aprovados, 2 UI ignorados e49.6%.
A corrida na fixture de agendamento foi eliminada reutilizando o horário do preview,
sem alterar a proteção preview_mismatch. A execução atual inclui esses reparos.

O merge6aae52c preserva o prefixo original até19418ec; dez cherry-picks -x mantêm
autoria e referência de origem. Reparos/evidências ficam em commits próprios.
O catálogo nativo contém340 ferramentas sem dependência de extensões pessoais.
A main original segue em0fc8e5e e os dez arquivos não rastreados mantêm os hashes
do manifesto de preservação. Nenhum stash foi reaplicado.

## Limites e autorização

E2E/impersonação: PASS — fixture/synthetic. Aceitação em app Bubble/navegador real:
NOT RUN. Os dois testes UI opt-in exigem configuração explícita e podem criar dados
reais, por isso ficam ignorados no pipeline padrão. Casos Python são código confiável,
não um sandbox; as guardas de navegação não isolam código Python arbitrário.

Não houve deploy ou execução de GitHub Actions. Após os reparos, o usuário autorizou
merge condicionado a pipeline local completo e nova revisão aprovados. Ambas as etapas
foram aprovadas no candidato acima; o merge deve preservar a ancestralidade por merge commit.
Autoupdate, tester, infraestrutura, overrides de política main, expressões globais,
core toolset e backend oficial continuam adiados.
