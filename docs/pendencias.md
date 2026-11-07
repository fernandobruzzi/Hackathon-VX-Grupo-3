# Pendências para revisão manual

A Governança acessa **Sanear → Pendências manuais** (`/pendencias/`). A tela usa
somente dados persistidos, com filtro por motivo, código exato e paginação. Cada
linha apresenta o material observado pelo batch e seus motivos, sem inventar
um estado corrigido. A fila de propostas continua em `/saneamento/`.

## Registrar as observações

A migração `0013_manual_reviews`, posterior a `0012_current_inventory_dataset`,
cria `manual_reviews`. Depois de atualizar a aplicação, execute
um novo saneamento: execuções anteriores não possuíam essas observações.

```bash
docker compose run --rm --build batch
```

Um job iniciado em `/batch/` também registra as pendências. Depois que termina,
**Ver pendências** abre exatamente a execução selecionada. Sem seleção, a tela
mostra a execução mais recente com observações disponíveis. Jobs em andamento
ou falhos não são expostos para encaminhamento. A execução sem job pela CLI
possui um identificador derivado do dataset, regras e versões dos materiais;
repeti-la não duplica as observações.

O produtor usa o mesmo `pending_by_code` que alimenta a cobertura e a contagem
de motivos do relatório. Cada motivo é contado uma vez por material, inclusive
quando o material também recebeu uma proposta automática. Um material pode ter
mais de um motivo; somar os motivos não equivale ao total de materiais.
Materiais bloqueados e obsoletos aparecem com o motivo correspondente, mas
não podem ser corrigidos.

As contagens representam a observação histórica da execução, inclusive após
encaminhamentos e aprovações. Não são um contador de tarefas ainda abertas.
Com acesso a todos os centros, correspondem a `corrections.pending` do relatório
daquela execução. Com acesso restrito, mostram somente os materiais cujos
centros estão todos autorizados; nenhum código ou contador de outro escopo é
exposto. Cada execução preserva os dados e a versão usados pelo produtor.

## Encaminhar para aprovação

1. A Governança abre **Revisar**, confirma a classe e o nome do item no PDM.
2. Confere os atributos, o NCM e a fonte. Os valores extraídos são sugestões,
   não evidência técnica independente. Campos condicionais continuam sujeitos
   ao validador compartilhado do PDM.
3. Se a unidade original difere da unidade da classe, informa fator e fonte da
   conversão. Embalagens sem fator confirmado continuam pendentes. A API confere
   também os snapshots de estoque e os vínculos de consolidação existentes.
   Aliases da mesma unidade usam fator 1 e a regra de normalização, inclusive
   quando o snapshot preserva a grafia anterior à correção do mestre.
4. Registra fonte e justificativa e escolhe **Criar proposta para aprovação**.
5. Abre o vínculo da proposta, revisa seu antes/depois e usa o fluxo normal de
   aprovação. Alterar NCM ou sua base técnica exige também revisão fiscal. A coerência
   condicional é reavaliada pela mesma regra da aprovação e registrada na proposta.
   Todo encaminhamento manual recebe nível 3, de revisão individual.

O encaminhamento cria uma `PDM_CORRECTION` com versão observada, hash, fontes e
PDM de referência, além de evento de auditoria com o autor autenticado. Não
altera descrição, atributos, unidade, NCM ou estoque do mestre. A proposta
passa pelas mesmas validações e aplicação transacional das demais propostas.
Uma proposta rejeitada ou desatualizada permite novo encaminhamento enquanto
a versão observada do material continuar atual; caso contrário, rode outro
batch. O histórico da proposta anterior e sua auditoria permanecem disponíveis.

Escritas exigem Origin, CSRF e `Idempotency-Key`. Repetir a mesma operação e
conteúdo devolve a mesma proposta; trocar o conteúdo com a mesma chave recebe
409. Uma pendência já vinculada a proposta pendente ou aplicada não recebe uma
segunda proposta. Troca de versão do material ou da referência PDM exige novo
batch. Falha ao gravar proposta, vínculo ou auditoria desfaz a transação inteira.

## Contratos e acesso

- `GET /api/v1/manual-reviews`: `run_id`, `reason`, `material_code`, `cursor`, `limit`.
  Retorna observações e contagens da execução, antes dos filtros de motivo/código.
- `GET /api/v1/manual-reviews/catalog`: classes, nomes, atributos, unidades e
  referências NCM do PDM carregado, usados no formulário.
- `POST /api/v1/manual-reviews/{review_id}/propose`: dados conferidos, fontes,
  justificativa e versão; retorna o ID da proposta pendente.

As três rotas exigem `merge:decide` na identidade e na matriz do papel. O banco
permite ao batch inserir observações e à API atualizar apenas seu vínculo com a
proposta; motivos e dados observados não podem ser reescritos pelas aplicações.
O MCP não recebe acesso à tabela. Nenhum valor financeiro é incluído na projeção.

Os testes verificam correspondência das contagens na base inteira, repetição sem
duplicação, escopo, CSRF, versões, referências, fontes de conversão, auditoria e
aprovação pela API sem edição antecipada do material.

Para estoque sem unidade no registro importado, a origem da conversão é uma
string vazia (`from_unit: ""`). Fator positivo e fonte continuam obrigatórios,
mesmo quando o fator informado é 1. O encaminhamento não deduz a unidade nem
altera o snapshot; a aprovação normal aplica a conversão e conserva o valor
contábil e os registros originais.
