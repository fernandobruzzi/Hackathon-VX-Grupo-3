# Pedidos de cadastro

Fluxo de um material novo, do pedido à publicação (#24). Validar no chat não publica nada; a
publicação passa pela Governança e pelo Fiscal.

## Estados

| Estado | Quando |
|---|---|
| `DRAFT` | Pedido aberto e ainda não encaminhado pelo dono |
| `OUT_OF_SCOPE` | O classificador não achou classe do PDM. Pode ser falso negativo: a Governança ainda vê o pedido |
| `INCOMPLETE` | Falta atributo obrigatório; `missing_attributes` diz quais |
| `EXISTING` | Já existe ativo com a mesma identidade; `candidate_material_ids` aponta quais |
| `READY_FOR_REVIEW` | Completo e sem duplicidade: aguarda a Governança |
| `PENDING_FISCAL` | Aprovado pela Governança: aguarda o NCM do Fiscal |
| `REGISTERED` | Publicado como material ativo e principal da sua identidade |
| `REJECTED` | Rejeitado pela Governança ou pelo Fiscal |

## Avaliação

O texto e o anexo passam pelos mesmos classificador e extrator do saneamento, e o PDM diz o
que falta. A duplicidade é a identidade exata (regra geral 10) contra o índice de busca da
versão atual e contra os principais já publicados. Sem índice da versão atual, a API responde
503 `SEARCH_INDEX_MISSING`: sem índice não dá para afirmar que o item é novo.

## Decisão e publicação

- `POST /api/v1/registration-orders/{id}/submit`: só o dono, de `DRAFT` ou `INCOMPLETE`.
- `POST /api/v1/registration-orders/{id}/decide`: a Governança (`orders:decide`) decide
  `READY_FOR_REVIEW`; o Fiscal (`ncm:decide`) decide `PENDING_FISCAL`.

Antes de cada aprovação o pedido é avaliado de novo com as regras atuais e a duplicidade é
conferida outra vez. Se apareceu um ativo com a mesma identidade, o pedido vira `EXISTING` e nada
é publicado. A aprovação do Fiscal cria o material com o próximo código numérico, status `ATIVO`,
principal da identidade, unidade padrão da classe e NCM aprovado. O NCM só é definido quando o
PDM não deixa escolha: código único na classe, exceção do próprio item ou sobressalente da
aplicação informada. Em outro caso a API responde 422 `NCM_UNDETERMINED` e o pedido continua no
Fiscal. Cada passo grava auditoria e aceita `Idempotency-Key`.

O replay de uma chave só devolve a resposta original após conferir tenant, centro e autorização
atual sobre o pedido. Na decisão, a etapa registrada na auditoria original define a permissão
exigida: uma aprovação técnica repetida continua exigindo Governança, mesmo após a publicação.
A submissão repetida também exige que o usuário continue sendo o dono. Revogar o acesso impede
recuperar a resposta armazenada; repetir com acesso mantido não aplica efeitos nem duplica auditoria.

## Importar os pedidos do kit

Depois do bootstrap e do índice, que o `docker compose up` já constrói, na raiz:

```bash
docker compose run --rm bootstrap vx-import-orders
```

Os 520 pedidos entram com `origin=IMPORT` e sem solicitante. Repetir não duplica. Na base do kit,
com as regras atuais: 169 prontos para revisão, 205 incompletos, 86 fora de escopo e 60 já
existentes.

## Enviar uma ficha do chat

O botão “Enviar pedido para revisão” chama `POST /api/v1/chat/{session_id}/submit`,
com `expected_session_version`, CSRF e `Idempotency-Key`. O corpo não aceita classe,
atributos, centro nem identidade: a API usa a ficha e o centro do último turno
concluído, confere o dono, valida o PDM atual e consulta novamente a identidade no
cadastro. Sem índice da versão atual, o envio é recusado.

A transação cria um pedido `CHAT`, vincula a conversa e grava a auditoria e o
resultado idempotente. O pedido fica `READY_FOR_REVIEW`, ou `EXISTING` se um ativo
igual surgiu desde a última busca. Em ambos os casos a resposta traz `order_id`;
a interface só confirma o envio depois desse sucesso. Uma resposta perdida pode
ser recuperada repetindo a mesma chave e o mesmo corpo. A mesma conversa gera no
máximo um pedido, inclusive com duas requisições simultâneas ou chaves diferentes.

O texto original reúne as mensagens do solicitante, na ordem da conversa. A
classe, o nome do item e os atributos confirmados ficam separados: aprovações
revalidam essa ficha estruturada no PDM atual, sem reextrair uma informação antiga
que já foi corrigida na conversa. Pedidos legados sem nome do item continuam com
a análise textual anterior. A migração acrescenta esse nome sem alterar os dados
originais do kit.

Depois do envio, a conversa fica disponível como evidência e não aceita novos
turnos que poderiam mudar a ficha encaminhada; para outro item, use “Nova conversa”.
A Governança e o Fiscal continuam aprovando pelo fluxo de pedidos existente.

## Listagem paginada

`GET /api/v1/registration-orders?mine=true` limita a consulta aos pedidos cujo dono é o usuário
autenticado, independentemente do nome de exibição. Centro, propriedade e estado são filtrados
no servidor antes do limite. A ordenação usa atualização decrescente e UUID para desempate.
Use `next_cursor` para a página seguinte na mesma consulta; cursor inválido recebe 422.
A tela oferece **Carregar mais pedidos** e reinicia a coleção ao trocar aba ou identidade.
