# Busca coerente com o cadastro atual

A API publica pedidos e aplica aprovações na master. Cada alteração incrementa
`materials_master.version`; materiais novos começam na revisão 1. O batch grava
`material_search_index.source_version` junto da interpretação. MCP continua com
SELECT somente nas views autorizadas, sem credenciais da API ou do batch.

A versão de regras continua incluindo PDM/hash, classificação, extração, identidade
e embeddings. O formato `search-index-v2` também invalida interpretações legadas que
foram produzidas sem considerar os valores aprovados. Uma linha só está atual
quando regras e revisão da fonte correspondem ao cadastro.

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
O atributo `is_canonical` não é usado como substituto da proveniência.

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
índice incompleto. Uma identidade atual já encontrada pode ser confirmada.

O indexador registra `INDEX_REFRESH_FAILED`, retira sua saúde e tenta novamente
no próximo ciclo. Inspecione `docker compose logs index`; depois de corrigir a
causa, a recuperação acontece automaticamente. Para uma operação pontual,
`vx-back index --if-stale` usa a mesma lógica. O comando sem `--watch` continua
finito, inclusive nas tasks de preparação do deploy.

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
