# Estado da demo

Aprovar uma proposta no ensaio altera materiais, consome a proposta e grava auditoria. O
`vx-demo reset` volta o banco ao estado inicial da demonstração, sempre o mesmo, para o próximo
ensaio começar igual ao pitch.

## O que o reset faz

1. Apaga o estado operacional: auditoria, idempotência, consolidações de estoque, conversas,
   snapshots de qualidade, pedidos, enriquecimento, propostas, índice de busca, jobs, saldos, materiais e datasets.
2. Garante as contas das personas (`SOLICITANTE_OPERACAO`, `GESTOR_CADASTRO`,
   `AUDITOR_FISCAL` e `DEV_TI`), ativas e com o papel fixo do servidor.
3. Recarrega o kit como veio, com os mesmos identificadores do `vx-bootstrap`.
4. Refaz o índice de busca e as propostas, com as mesmas regras do batch.
5. Importa os 520 pedidos do kit pela mesma importação de `vx-import-orders` (`IMPORT`, sem
   solicitante), já analisados contra o PDM e o índice. O resumo traz a contagem por status.
6. Escolhe as propostas do roteiro e imprime um resumo em JSON.

Ficam como estavam: usuários, sessões de login, versões de referência e arquivos no
armazenamento. Quem já entrou continua logado depois do reset.

Os identificadores vêm do kit e do conteúdo das propostas, então repetir o reset sempre chega ao
mesmo estado. O resumo traz `state.sha256`, a impressão digital desse estado, e
`vx-demo status` mostra a do estado atual sem alterar nada. Se a impressão digital mudar entre
dois resets sem mudança de código ou de dados, algo ficou de fora: abra uma issue.

## Proteções

- Só roda com `DEMO_MODE=true`.
- Exige `--confirm <banco>` com o nome do banco de `MIGRATION_DATABASE_URL`, que será apagado.
- Usa a credencial `migration_user`, a única que pode apagar conversas e auditoria.
- A lista de tabelas apagadas é explícita. Uma tabela nova ligada a elas faz o reset falhar, em
  vez de ser apagada sem revisão.

## Como rodar

Localmente, com a stack de pé (`docker compose up`), na raiz:

```bash
DEMO_MODE=true scripts/load_demo_data.sh
```

O script roda o serviço `demo` do Compose, equivalente a:

```bash
DEMO_MODE=true docker compose --profile demo run --rm --build demo reset --confirm vx_materiais
```

Sem Docker, em `api/`:

```bash
DEMO_MODE=true MIGRATION_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:5432/vx_materiais uv run vx-demo reset --data-dir ../data/desafio01 --confirm vx_materiais
```

Na AWS, rode uma task avulsa da imagem `api` com o comando `vx-demo reset --confirm vx_materiais`,
`DEMO_MODE=true` e `MIGRATION_DATABASE_URL` vindo do Secrets Manager. O deploy (#6) define como
disparar essa task.

O reset leva cerca de 30 segundos. Não rode durante o pitch: as telas mostram dados
incompletos enquanto ele trabalha.

## Antes de cada ensaio

1. Rode o reset e guarde o JSON impresso.
2. Confira `state.sha256` com o do ensaio anterior. Mudou sem mudança de código? Pare e investigue.
3. Entre com as três personas. Localmente, pela tela de login. Na AWS, com as contas do Cognito.
4. Abra o `review_path` de `demo_proposals.governance` e de `demo_proposals.fiscal`. Os
   identificadores mudam quando as regras de unificação mudam, então leia sempre do resumo.
5. Confira que o chat começa sem conversas e que a fila mostra as propostas pendentes.

## Propostas do roteiro

O resumo traz duas unificações sem conflito, da classe do roteiro (parafuso sextavado) quando
houver:

- `governance`: só revisão técnica. Aprovada pela Governança, aplica na hora.
- `fiscal`: exige revisão técnica e fiscal. A Governança aprova a técnica, a proposta continua
  pendente, e a aplicação só acontece quando o Auditor fiscal aprova a fiscal. Mostra a separação
  de papéis e os dois eventos de auditoria.

## Limites

- O enriquecimento dos produtos reais (#23) é apagado com os materiais. Quando ele tiver um
  comando, o reset deve chamá-lo também.
- Contas do Cognito não são criadas pelo reset. Conversas e pedidos próprios de cada persona
  começam vazios.
