# Busca coerente com o cadastro atual

A API publica pedidos e aplica aprovações na master. Cada alteração incrementa
`materials_master.version`; materiais novos começam na revisão 1. O batch grava
`material_search_index.source_version` junto da interpretação. MCP continua com
SELECT somente nas views autorizadas, sem credenciais da API ou do batch.

A versão de regras continua incluindo PDM/hash, classificação, extração, identidade
e embeddings. O formato `search-index-v2` também invalida interpretações legadas que
foram produzidas sem considerar os valores aprovados. Uma linha só está atual
quando regras e revisão da fonte correspondem ao cadastro. A cobertura é contada
somente no tenant autenticado; pendências de outra empresa não alteram o estado
da busca nem permitem consultar seus materiais.

## Atualização automática local

`docker compose up --build` mantém o serviço `index` existente em
`vx-back index --watch`, com polling de dois segundos. O primeiro ciclo saudável
libera a inicialização do Agent. Depois, `--if-stale` reanalisa somente materiais
novos ou alterados; não precisa iniciar outro saneamento depois de cada aprovação.
O intervalo aceita de 1 a 60 segundos por `--poll-seconds`.

A descrição PDM e os atributos presentes na master são dados atuais, inclusive em
materiais ainda não canônicos. Prevalecem sobre extrações sugeridas. Os originais
permanecem nas colunas `original_description_*`; interpretações e identidades
sugeridas ficam no índice, enquanto os valores aprovados permanecem na master.
O atributo `is_canonical` não é usado como substituto da proveniência. A busca
revalida a mesma fonte atual usada pelo indexador, incluindo substantivo e
atributos aprovados, em vez de sobrescrevê-los com uma extração do texto histórico.
Sem valores aprovados, as contradições do original continuam impedindo a
identidade verificada. Revisões de peça no original e conflitos entre os campos
estruturados atuais e os atributos continuam exigindo revisão; uma atualização
do índice não homologa intercambiabilidade.

Um advisory lock por tenant serializa indexadores. Cada lote é confirmado numa
transação e não sobrescreve uma revisão mais recente. Se a master muda durante a
análise, a linha conserva a revisão efetivamente lida, fica pendente e é retomada
no próximo ciclo. O reset da demo espera a análise anterior antes de reaproveitar
IDs e revisões da carga inicial.

## Durante atualização ou falha

MCP verifica cobertura completa e revisões na mesma transação `REPEATABLE READ`
somente leitura que executa as consultas. Assim, uma mudança entre a checagem e a
busca não mistura estados. Enquanto faltar uma linha atual, devolve
`INDEX_UPDATING` e orienta nova tentativa; não conclui que não existe item igual.
A verificação de duplicidade de pedidos também recusa conclusões negativas com
índice incompleto. Uma chave coincidente apenas recupera candidatos: API e MCP
revalidam a mesma fonte atual e usam a decisão compartilhada de identidade.
A análise do pedido também conserva o texto recebido, anexos e complementos:
a descrição formatada não substitui essa evidência, pois pode omitir `REV A`.
No chat, os atributos confirmados continuam prevalecendo sobre referências antigas
corrigidas; conservar o texto não faz uma nova extração desses valores obsoletos.
A verificação automática e a avaliação de pedidos liberam `EXISTING` somente
com `SAME_MATERIAL`, inclusive para cadastros canônicos. O chat também conserva
a escolha explícita do solicitante por um candidato similar recém-oferecido;
essa escolha encerra a ficha como reutilização, sem criar um pedido de cadastro. Um conflito confirmado é descartado como duplicidade; uma evidência
inconclusiva fica na revisão técnica, com candidatos e motivo visível em
`missing_attributes`. Confirmar ou publicar enquanto essa dúvida persiste retorna
`IDENTITY_REVIEW_REQUIRED`, sem aprovar uma equivalência por decisão genérica. Uma identidade atual já encontrada pode ser confirmada. Na API, candidatos e
cobertura são calculados numa única instrução SQL para não misturar uma lista
antiga com uma cobertura já reconstruída. A decisão que pode publicar um pedido
adquire primeiro o lock das aprovações do tenant (seed 0) e depois o lock já
existente dos pedidos (seed 1); retém ambos até o commit. Assim, uma aprovação
não altera o cadastro entre a última verificação e a publicação.

O indexador registra `INDEX_REFRESH_FAILED`, retira sua saúde e tenta novamente
no próximo ciclo. Inspecione `docker compose logs index`; depois de corrigir a
causa, a recuperação acontece automaticamente. Um ciclo pendente ou ocupado
também retira a saúde anterior; somente um ciclo completo volta a liberá-la. Para uma operação pontual,
`vx-back index --if-stale` usa a mesma lógica. O comando sem `--watch` continua
finito, inclusive nas tasks de preparação do deploy.

## Verificações salvas no chat

A API guarda uma prova privada por tenant (quantidade e soma das revisões dos
materiais, versão das regras/PDM e dataset de estoque vigente, escolhido por
`imported_at DESC, id DESC`). Antes de encaminhar o contexto ao Agent,
compara essa prova com o catálogo atual. Uma publicação ou aprovação invalida a
verificação antiga e suas escolhas; sessões legadas sem prova são revalidadas uma
vez. Sem mudança de catálogo ou ficha, escolhas e descartes continuam válidos sem
repetir a busca. A prova não integra o contrato do Agent.

A conclusão confere novamente a prova sob os mesmos locks dos escritores. Se o
catálogo mudou durante o turno, devolve `CATALOG_CHANGED` sem gravar mensagens nem
avançar a versão da conversa. A liberação da reserva e a invalidação são
confirmadas antes do erro; basta repetir a mensagem. Um botão de escolha antigo
pode disparar essa recuperação, mas nunca confirma um candidato desatualizado.
Falhas da busca deixam a ficha pendente e não renovam a prova antiga.

## AWS e EC2

As tasks de migração/bootstrap/indexação do deploy permanecem finitas. A
invalidação segura se aplica também nesses ambientes; para atualização automática,
a operação deve manter a imagem batch com `vx-back index --watch`, conexão
`batch_user` e o mesmo PDM/repositórios do Agent como processo contínuo supervisionado.
Não rode o modo contínuo na etapa one-shot que o deploy espera terminar.

A configuração e homologação desse processo contínuo na AWS fazem parte da #6;
a equivalência operacional na EC2 acompanha a #29. O Compose local está integrado,
mas isso não é evidência de homologação AWS. Sem o processo contínuo, a busca
permanece pendente de forma segura após alterações, até uma indexação compatível.


## Estado da integração

A migração `0016_search_content_version` sucede `0015_order_fiscal_review`; as migrações
0011 a 0015 de lotes, estoque vigente, revisão manual, complementos e revisão fiscal
permanecem intactas.
Os testes de busca e API verificam essa cadeia única, a correspondência com os
modelos e a convivência com a revisão manual e o histórico de conversas.

A configuração do serviço contínuo no Compose não substitui sua execução real.
A aceitação de `docker compose up --build`, incluindo o ciclo de publicação,
atualização e busca, continua pendente nesta preparação. O PR permanece em
rascunho até essa verificação; resultados de testes em PostgreSQL descartável
não comprovam esse critério operacional nem a homologação na AWS.


Complementos também passam pela avaliação de identidade atual. O texto bruto original,
o anexo e os complementos ficam em `OrderAnalysis.source_text`, separados dos delimitadores
usados para extrair atributos. Na ficha do chat, os valores confirmados continuam
prevalecendo. A assinatura técnica inclui essa evidência bruta; mudá-la exige nova
revisão antes da publicação fiscal, mesmo quando os atributos extraídos continuam iguais.

Complemento, detalhe e reabertura usam a mesma avaliação de três resultados: estado,
candidatos e pendências. Uma chave coincidente com evidência inconclusiva continua como
revisão de identidade, inclusive na ficha de revisão; a interface bloqueia aprovação,
mas conserva rejeição e reabertura conforme as permissões atuais.


Ao publicar um pedido, `original_description_long` do novo material recebe a concatenação
ordenada, separada por quebras de linha, do texto original, anexo e complementos presentes.
É evidência derivada de múltiplos registros brutos, não uma cópia exata de um único campo nem
uma descrição corrigida. Os campos originais do pedido e cada complemento com origem, autor e
data continuam separados e preservados, com auditoria da operação. Isso mantém contradições
como `REV A` acessíveis à indexação e à decisão compartilhada depois da publicação.
