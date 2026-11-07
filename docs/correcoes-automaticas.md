# Correções automáticas elegíveis

A #224 substitui parcialmente a decisão da #36: a API pode aplicar **aliases da mesma unidade** e **descrições PDM completas sem perda de informação**, com decisão `SYSTEM`. Grupo, NCM (inclusive reformatação), unificações, casos ambíguos e efeitos fora desse escopo continuam humanos. `review_lane` organiza a revisão, mas nunca autoriza sozinho uma escrita.

## Configuração e execução

`AUTOMATIC_CORRECTION_MODE` aceita `OFF` (padrão), `SIMULATE` ou `APPLY`. Configure o mesmo valor na API e no serviço `automatic-corrections`. O modo é capturado pelo servidor na criação de cada job de saneamento por Governança, junto com política e centros autorizados. Nenhum parâmetro público habilita a opção. Jobs anteriores, propostas antigas reutilizadas pelo batch e outros tipos de job não são armados retroativamente. Uma simulação não se transforma depois em aplicação: crie um novo job; propostas já existentes continuam humanas.

O Compose inclui o worker `vx-auto-correct`, da imagem API, que consulta jobs concluídos a cada cinco segundos (`AUTOMATIC_CORRECTION_POLL_SECONDS`). `vx-auto-correct --once` executa uma passagem. Ele usa `DATABASE_URL` com `api_user` para aplicar e auditar; somente a atualização de índice usa `BATCH_DATABASE_URL` com `batch_user`. O batch não pode editar a autorização automática do job. Em AWS execute esse mesmo comando como serviço interno, com segredos separados, sem porta pública, PDM montado e `AUTHORIZED_CENTER_CODES` explícito; não habilite execução automática somente no container de análise. Desligar o modo pausa aplicações, sem desfazer correções confirmadas. A recuperação do índice de correções já aplicadas continua possível com o modo desligado.

O solicitante do job deve continuar ativo, no mesmo tenant e com papel de Governança. Os centros capturados são intersectados com a autorização atual do servidor. A política `safe-corrections-v1` refaz classificação, extração, correção e comparação do conteúdo persistido. A política admite somente as revisões medidas (`aliases_v1@2`, `rule_based_v1@11-quantity-reference-199`); revisar a política e repetir a medição antes de autorizar outra revisão. O hash da proposta, versões do material/PDM e assinatura das regras são revalidados sob a mesma trava por tenant usada pela decisão humana. Mudanças exigem nova análise (`STALE`). Propostas decididas ou em lotes `OPEN`/`RETURNED` não são tomadas pela automação.

## Escrita, simulação e recuperação

Cada proposta tem uma transação própria. A validação compartilhada da aprovação roda em um savepoint e seus efeitos são comparados com o estado anterior: unidade pode mudar somente unidade/versão; descrição pode publicar somente descrição, classe/versão PDM, atributos, identidade/canonicidade e versão. Qualquer alteração incidental desfaz o savepoint inteiro e encaminha à revisão. Snapshots e vínculos de estoque, fabricante/referência, grupo, NCM, status e redirecionamentos são preservados. Colisões de identidade mantêm a proposta para revisão.

`SIMULATE` executa a mesma validação e desfaz o savepoint, guardando apenas o relatório. Não confirma material, decisão, auditoria de aprovação nem remove a proposta da fila. `APPLY` confirma material, proposta e auditoria juntos. O evento `PROPOSAL_AUTO_APPLY` traz ator `SYSTEM`, sem usuário ou papel humano, com proposta/job/material, antes/depois, política, regras, execução e evidências de classificação/atributos. Falhas desfazem o item inteiro e geram resultado `ERROR`; os demais itens continuam.

Após o commit, o índice é atualizado com as credenciais batch. O resultado durável fica `PENDING`, `CURRENT` ou `FAILED`. Enquanto existir aplicação com índice pendente/falho no tenant, as consultas MCP recusam a busca com mensagem explícita, inclusive em instâncias já inicializadas; não devolvem ausência falsa. O worker tenta recuperar a indexação, sem reaplicar o material. O comando autenticado `POST /api/v1/batch/jobs/{id}/automatic-corrections/retry`, com corpo vazio, Origin, CSRF e idempotência, retoma erros e índice de um job já autorizado; não habilita jobs antigos nem muda o modo.

`GET /api/v1/batch/jobs/{id}/automatic-corrections` apresenta contagens avaliadas/elegíveis/aplicadas/revisão/desatualizadas/erros/busca pendente e motivos. Os itens paginados passam pelo guard de recurso. A tela Batch mostra modo e relatório; fila, detalhe e auditoria distinguem sistema e pessoa. Códigos de motivo são preservados para rastreio.

## Medição reproduzível

Na pasta `back`, execute:

```bash
uv run python -m pipelines.measure_automatic_corrections ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

O JSON registra commit, política, assinatura das regras, versão/hash PDM, 23.554 linhas, contagens por tipo/motivo e exemplos. Mede elegibilidade de domínio: estado, autorização, colisões e efeitos transacionais ainda são verificados na API. Contagem elegível/aplicada não prova precisão. Consulte [a medição registrada](medicao-correcoes-automaticas.json) e os exemplos revisados abaixo; não houve validação independente por especialista de materiais.

Exemplos conferidos pela descrição original e pelos atributos extraídos:

- `24794045`: amortecedor em `PCA`; a classe confiável usa `PC`. Somente a grafia muda, com fator 1; estoque original permanece em `PCA`.
- `16454102`: anel O-ring com diâmetro interno 15 mm, seção 2 mm, NBR e dureza 70 Shore A. A descrição formatada conserva as quatro informações; o teste PostgreSQL confirma publicação sem alterações de estoque.
- `24477027`: parafuso Allen sem classe confirmada. Mesmo com alias de unidade conhecido, continua humano.
- `15452229`: mandíbula SANDVIK com referência `458.6479-93 REV A`. O formatador omite `REV A`; a revisão não confirmada pode distinguir peças e deve permanecer para análise humana (`TEXT_LOSS`).
- `29936075`: cabo com a grafia `TESNAO` na origem. Embora a descrição formatada conserve os valores, a regra conservadora sinaliza texto não resolvido e recusa automatizar. Isso ilustra uma recusa adicional, não uma medição de precisão.
