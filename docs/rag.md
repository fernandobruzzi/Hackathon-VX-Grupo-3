# Contexto recuperado para o chat e o auditor

A tool MCP `retrieve_material_context(query, pdm_class_id?, limit=5)` devolve contexto
de referência. O chat com Bedrock a chama depois das validações de domínio e entrega
o resultado à etapa de redação. O planejador local continua sem chamadas ao modelo.
Consumidores como o auditor também podem chamar essa tool, vinculada à identidade
autenticada do processo. Para execução dentro do batch, `domain.contracts` expõe
`RagMaterialRepository` e `RagScope`, e `domain.rag_context` fornece `build_context`;
o consumidor fornece um repositório autorizado e registra o pacote junto à sua chamada ao modelo. Os
contratos ficam em `domain/contracts.py`; o algoritmo `context_v1` em
`repositories/rag` é selecionado por `RAG_REPOSITORY`. Novas implementações entram
no registro sem remover a atual e passam pelos mesmos testes de contrato.

## Fontes e escopo

- **Materiais:** vizinhos no pgvector com o adaptador selecionado por
  `EMBEDDING_REPOSITORY`. Sem embeddings, usa full-text e rotula
  `FULL_TEXT_NO_EMBEDDINGS`; falha do modelo usa `FULL_TEXT_EMBEDDING_UNAVAILABLE`.
  A consulta aplica tenant, centros e dataset vigente antes do ranking e do limite.
  Snapshots históricos e centros não autorizados não fornecem exemplos nem afetam
  quais materiais entram no limite. Não há escrita, reserva nem movimento.
- **Procedência:** prefere cadastro com classe técnica aprovada e revisão fiscal
  aprovada. `APPROVED_MASTER` e `INDEX_PROPOSAL` distinguem valores persistidos de
  inferências do índice. `FISCALLY_APPROVED` e `UNREVIEWED_MASTER` são independentes
  dessa procedência técnica. O pacote registra a versão do índice; índice
  desatualizado ou sem os vetores esperados retorna `INDEX_UPDATING`.
- **PDM:** classe candidata e classes dos exemplos, atributos admitidos, condições,
  valores permitidos e referências NCM, com versão e hash do workbook.
- **NCM:** somente o snapshot selecionado no servidor, íntegro e com procedência
  `OFFICIAL_DOWNLOAD`, fornece descrições fiscais. O parser preserva os registros
  originais de capítulos, posições e subposições em `hierarchy`, separadamente dos
  códigos completos usados na checagem de existência. O contexto só inclui
  ancestrais presentes no arquivo; nunca cria descrições a partir de prefixos.
  Data de captura, vigência, URL e hash acompanham cada trecho. Sem referência
  oficial disponível, `ncm_status=UNAVAILABLE`; o PDM não comprova existência fiscal.

A identidade nunca é parâmetro da tool. O chamador precisa estar ativo e ter
`materials:read`. A view de estoque vem de `inventory_view(caller)` para verificar
o escopo; preço, valor e saldo não fazem parte da projeção enviada ao modelo.
Sem `inventory:read`, o pacote contém somente referências públicas PDM/NCM, sem
exemplos privados nem associações de materiais a centros.
Mesmo um repositório simulado que devolva registros fora do escopo é filtrado
novamente pelo construtor compartilhado. Somente atributos admitidos no PDM
entram na projeção do material.

Os centros dos exemplos são estruturados como `centers[].center_code`. A API
acumula esses centros no histórico da conversa: revogar acesso a um centro também
impede abrir ou retomar conversas cujo contexto RAG tenha usado seus materiais.

## Orçamento e citações

O pacote `rag_context_v1` tem até **12.000 caracteres no JSON inteiro**, incluindo
manifesto, até cinco exemplos de materiais e até doze itens. Fontes PDM, materiais
e NCM são intercaladas para dividir o orçamento. Um item que não cabe é omitido
inteiro e `truncated=true`; ele não recebe citação. Textos de materiais são
excertos limitados. Não há recorte de JSON nem citação apontando para item ausente.

`context_id` vincula hashes de consulta, escopo, conteúdo, versões e método de
recuperação. Cada fonte registra `citation_id`, URI, versão, rótulo e SHA-256 do
conteúdo efetivamente entregue. Esses dados e os itens ficam no registro da
chamada MCP persistido pela API; o painel de diagnóstico continua restrito a
`chat:diagnostics`.

O prompt `material_registration_system_v2` trata referências como dados não
confiáveis e pede citações como `[R1]`. A versão anterior permanece no código.
Na resposta final, apenas identificadores presentes no pacote são aceitos.
As fontes citadas recebem rótulos legíveis e `used_citation_ids` registra quais
foram usadas, separadamente das fontes apenas recuperadas. O contexto não muda
atributos aceitos, prontidão, identidade nem revisão fiscal. A apresentação
determinística de estoque identificado permanece sob controle do domínio.

## Verificação e dependências externas

Os testes de domínio usam repositórios simulados para verificar escopo,
procedência, orçamento, hashes e ausência de campos financeiros. Os testes de
PostgreSQL/pgvector usam embeddings simulados e o protocolo stdio real, incluindo
55 candidatos de outro centro para conferir que o filtro precede o limite,
dataset histórico, tenant alheio, preferência por aprovados, fallback e índice
pendente. API e chat cobrem citações, diagnósticos e revogação de acesso ao histórico.

`simulated_v1` continua rotulado na assinatura e recusado fora do ambiente local,
inclusive em runtime AWS. Esses testes verificam o contrato e o isolamento da
recuperação. A medição Titan da #288 está em [embeddings-titan.md](embeddings-titan.md),
que mantém seu uso optativo na AWS. Essa avaliação da busca de identidade não
estima a qualidade do ranking RAG `context_v1`.
A captura da tabela oficial permanece na #30; o código suporta seu conteúdo,
mas não apresenta fixtures ou importações não verificadas como referência oficial.
