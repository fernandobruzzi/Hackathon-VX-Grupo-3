# Plano: testes locais e promoção por homologação

**Objetivo:** reduzir os minutos de CI, integrando entregas em `homologacao`
e executando validação completa apenas nos PRs para `main` (produção).

**Arquitetura:** branches de trabalho partem de `homologacao` e voltam por PR
com evidências locais. A promoção `homologacao → main` preserva commits por merge;
o CI testa o resultado combinado com a base e não repete após o merge.
Após promover, um PR de sincronização `main → homologacao` usa merge commit,
preservando o histórico sem push direto nas branches permanentes.

**Tecnologias:** GitHub Actions, pytest no workspace uv, Node test runner.

## Restrições e decisões

- Preservar todos os jobs e checks completos existentes.
- Ambos os workflows automáticos filtram PRs pelo destino `main`.
- `pytest` roda separadamente em `back/`, `mcp/` e `api/`.
- Homologação é uma branch de integração; esta mudança não cria ambiente AWS.
- Proteções, branch padrão e métodos de merge dependem de administrador.
- Branches permanentes não podem ser apagadas ou sofrer force push.

## Execução

- [x] Registrar e assumir a issue #178; atualizar a base e criar a branch de trabalho.
- [x] Criar `homologacao` a partir da `main` remota, sem alterar produção.
- [x] Testar os filtros de evento e a política de promoção antes de alterá-los.
- [x] Restringir os workflows e aceitar promoção/sincronização no mesmo repositório.
- [x] Atualizar guia, runbook e template com testes locais e procedimentos de promoção.
- [x] Executar pytest por módulo, testes da política e formatação; revisar o diff.
- [x] Preparar branch e descrição para PR em `homologacao`, com evidências locais.

Validação: 721 testes dos módulos passaram, 275 de banco foram pulados sem
`TEST_DATABASE_URL`; scripts: 31 passaram e 1 foi pulado; política: 9 passaram.
YAML foi validado e os jobs foram comparados com a base, sem alterações.
Ruff e revisão independente do fluxo também concluídos.

## Foco da revisão

Retarget de PR para `main` deve validar; pushes e PRs de homologação não devem
rodar CI; forks não podem se passar pela branch de promoção; promoções sucessivas
devem preservar ancestralidade; checks obrigatórios devem existir somente na base
em que os workflows executam. Verificar também a ativação inicial das novas regras
e a preservação da branch permanente após o merge.
