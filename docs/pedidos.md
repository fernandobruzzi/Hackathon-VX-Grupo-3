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

## Complementar um pedido

O dono pode complementar pedidos próprios; a Governança pode complementar importados sem dono,
sempre nos centros autorizados. `can_complement` na resposta indica a ação disponível. Apenas
`DRAFT`, `INCOMPLETE` e `OUT_OF_SCOPE` aceitam essa operação; revisão, publicação e rejeição não
são reabertas. O complemento não atribui um dono e nunca publica um material.

`POST /api/v1/registration-orders/{id}/complement` recebe versão, texto complementar, origem da
informação e motivo, com CSRF e Idempotency-Key. Preserva os textos original e do anexo; grava
cada complemento com autor e data e audita antes/depois na mesma transação. O motor PDM reavalia
classe, atributos e duplicidade; informação insuficiente mantém as pendências. Na ficha estruturada
confirmada pelo chat, preenche somente atributos ausentes e preserva os valores já confirmados.
Por exemplo, `SC-202600011` com `BITOLA: M12` pode seguir para revisão técnica. Informação aceita
não significa cadastro aprovado nem decisão fiscal.

A migração `0014_order_supplements` sucede `0013_manual_reviews` e deve ser aplicada antes
de servir esta versão da API. Migrações já aplicadas permanecem intactas.

## Revisão da ficha e escolha fiscal

**Revisar pedido** consulta `GET /api/v1/registration-orders/{id}` antes da decisão: originais,
anexo, item, atributos, descrição proposta, identidades existentes e versões de PDM/índice.
A Governança registra a aprovação técnica vinculada à classe, item, atributos e regras atuais.
O Fiscal confere condições e alternativas NCM; quando o código não é único pelo fluxo anterior,
informa uma escolha explícita com fonte e justificativa. O servidor usa o avaliador compartilhado
de NCM: pertencer à mesma classe não basta se a condição do código for incompatível.

O pedido `SC-202600010` aceita a escolha fiscal consistente com seu tipo de filtro, sem adivinhar
entre todos os códigos da classe. A aprovação persiste código normalizado, fonte, ator, motivo,
versão e avaliação na mesma transação da publicação; o material usa exatamente essa decisão.
A repetição explícita mantém chave e payload, inclusive após perda da resposta.

A escolha fica vinculada ao hash da avaliação apresentada e à ficha aprovada tecnicamente.
Alterar atributos, item, PDM ou regras após a aprovação técnica impede publicar
(`TECHNICAL_REVIEW_CHANGED`); uma avaliação fiscal diferente exige nova consulta
(`NCM_ASSESSMENT_CHANGED`). Pedidos legados já no Fiscal, sem a ficha técnica registrada pela
nova versão, também permanecem pendentes para revisão; a migração não inventa aprovação anterior.
A Governança não define NCM. Sem o snapshot oficial da #30, existência e vigência continuam
`null`: a concordância com o PDM e a aprovação humana não confirmam vigência oficial.

Para recuperar um pedido legado ou uma ficha alterada que ainda está `PENDING_FISCAL`, a
Governança abre **Revisar pedido**, informa o motivo e escolhe **Reavaliar e devolver à revisão
técnica** (`POST /{id}/reopen-technical-review`). A transição confere escopo, versão e idempotência,
reexecuta PDM/duplicidade e audita a remoção das revisões antigas. O resultado pode ser
`READY_FOR_REVIEW`, `INCOMPLETE`, `OUT_OF_SCOPE` ou `EXISTING`; nenhuma aprovação é criada. Uma ficha
pronta passa novamente pela aprovação técnica e depois pela fiscal. Fiscal não reabre a revisão;
pedidos registrados e rejeitados permanecem fechados.

A migração `0015_order_fiscal_review` sucede `0014_order_supplements`; aplique-a antes de servir
a revisão fiscal. Ela acrescenta o registro das decisões e não fabrica aprovações de pedidos legados.
