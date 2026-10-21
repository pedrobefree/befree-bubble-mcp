# Integração gradual: entrega e validação

Decisão aprovada na conversa: integrar savepoints, clonagem, duplicação, E2E e impersonação após confiabilidade (PR46, merge1d7243e). Abrir PR para revisão; sem merge ou deploy neste bloco.

## Contratos

- Preservar os contratos de IDs, patches parciais, tombstones, verificação acumulada e distinção bool/número já integrados.
- Savepoint por sessão de escrita é tentativa reportada, não garantia de undo individual ou pré-condição global de sucesso; preview não cria savepoint. Restauração exige execução/confirmação explícita.
- Clone reminta apenas IDs próprios e atualiza índices; duplicação de elementos preserva subárvores e referências internas, relata referências externas e confirma nós/índices lidos após escrita. Nunca recuperar irmãos de cache obsoleto para sobrescrever uma substituição.
- Impersonação mantém sessão por app/versão/usuário, armazena cookies sem exposição pública e com permissão restrita. Lookup em live é recusado. Preview não abre browser nem executa um fluxo.
- E2E executa apenas no ambiente selecionado de desenvolvimento/branch, recusa live e apresenta passos, artefatos e erros. Falhas de um caso não ocultam os demais; resultado sintético não é prova Bubble real.
- Headers e credenciais de preview são resolvidos explicitamente e nunca devolvidos como segredos no MCP. Preservar campos omitidos ao atualizar perfis.
- Políticas do PR46 continuam aplicáveis. Nenhum teste local deve usar contas pessoais, abrir browser real ou disparar deploy por padrão.
- Preservar ancestralidade por merge do prefixo do fork até19418ec (9 novos commits após5e70624). Transportar capacidades posteriores selecionadas com cherry-pick -x.
- Fora do escopo: autoupdate, provisionamento/noVNC/túnel de produção, tester, main_write_policy overrides, expressões globais, core toolset e backend oficial.

## Critério de conclusão

Pipeline de .github/workflows/ci.yml inteiro local: Python3.11, cobertura >=45.3%, Ruff/Mypy sem novas exclusões, auditoria, smokes e Node20. Revisão independente sem P1/P2 pendentes. Publicar PR no pedrobefree/main; GitHub Actions permanece desabilitado. Original main0fc8e5e e10 arquivos não rastreados intactos.

## Proveniência e adaptações

O merge6aae52c preserva o prefixo original até19418ec. Os cherry-picks -x de
f563173, f22c21d, e3b3164, aeb8ac4, 2a749cb, abdb4c5, 0a9a882, e2446f3,
cfdf02b e273dec1 preservam a autoria das capacidades posteriores. Conflitos
retêm as guardas e correções de confiabilidade do upstream. Hunks de core toolset,
context_query e expressões globais foram omitidos por pertencerem aos blocos adiados.

As regressões locais reproduziram fontes escalares em clone, caminhos Windows
aceitos no POSIX, colisões source/since nos schemas e ferramentas novas sem guarda
de sessão no preview. Os reparos preservam os contratos existentes. Testes isolam
configuração/sessão/savepoint e não dependem de Playwright instalado para previews sintéticos.

## Revisão final

Os sete achados da revisão independente foram reparados com regressões; detalhes e
resultados em docs/delivery-validation-local-validation.md. O pipeline local passou
em2393ca8, e o PR47 está aberto para revisão humana. Aceitação Bubble real não executada.
