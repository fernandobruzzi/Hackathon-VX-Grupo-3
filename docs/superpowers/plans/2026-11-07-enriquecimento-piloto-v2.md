# Enriquecimento: piloto por família e evidência — plano de implementação

> **For agentic workers:** implementação em frentes independentes com TDD; revisão integrada ao final. Não fazer merge.

**Goal:** Ampliar o PR #272 com recuperação de informação existente, fontes complementares, diagnóstico acionável e avaliação por atributo.

**Architecture:** Reutilizar classificador, extrator, PDM, identidade e aprovação atuais. Documentos adicionais são arquivados com hash e vinculados ao dataset; IA opcional propõe leituras citadas para revisão, sem criar identidade ou fatos por inferência. Valores aprovados e originais permanecem rastreáveis.

**Tech Stack:** Python 3.12, boto3/Bedrock opcional, PostgreSQL/SQLAlchemy, Next.js/TypeScript. Sem novas dependências.

**Spec:** solicitação do usuário para implementar as seis melhorias discutidas, localmente e no PR #272, sem merge; docs/enriquecimento-interno.md.

## Restrições

- Nenhum merge em homologacao ou main. Atualizar apenas o PR existente.
- PDM valida estrutura; valores precisam de documento ou confirmação humana.
- Não relaxar identidade, combinar produtos conflitantes ou propagar propostas pendentes como fonte.
- Pesquisa externa de produto continua restrita aos 15 códigos reais; documentos adicionais são fontes internas fornecidas.
- IA desativada por padrão; chamadas exigem modelo e orçamento configurados. Medição padrão não chama modelo nem inventa custo/precisão.
- Preservar medições históricas e rotulagem congelada. Publicar novo artefato comparativo.

## Frentes e interfaces

### 1. Recuperação determinística

- [x] Testes RED/GREEN para aliases inequívocos e leitura independente de descrição longa/curta/estruturados.
- [x] Compartilhar `extract_material_fields` entre saneamento e validação da origem; conflitos não confirmam identidade.
- [x] Regressões nas classes PDM110, PDM050 e PDM001 e famílias reconhecíveis sem inventar liga/acabamento/conexão.

### 2. Fontes documentais internas

- [x] Loader versionado de bundle `internal-documents-v1`, dataset_id e documentos com id/título/texto.
- [x] Rejeitar identificadores duplicados, escopos inválidos, tipos externos e campos desconhecidos; não buscar URLs.
- [x] CLI arquiva bytes em `references/internal-sources/<dataset>/<sha256>.json`; relatório e aprovação vinculam chave/hash.
- [x] Fontes novas não alteram os originais, não atestam aprovação por autodeclaração e não usam propostas como evidência.

### 3. Leitura assistida opcional

- [x] Cliente Bedrock Converse com injeção do cliente para testes, limites de entrada/saída e validação de resposta.
- [x] Candidato informa atributo, valor, campo de origem e trecho literal; valor deve ser sustentado pela leitura PDM do trecho.
- [x] Orçamento de chamadas explícito, uso registrado e nenhuma chamada padrão; candidatos seguem para complemento humano.

### 4. Diagnóstico, tratamento e revisão

- [x] Separar status do classificador, conflitos dentro do registro/entre fontes e causas por atributo.
- [x] Gerar perguntas direcionadas e mostrar causas/candidatos na pendência, com contrato/tipos atualizados.
- [x] Integrar documentos novos e IA limitada ao batch/relatório sem publicação automática de candidatos de IA.
- [x] Pacote congelado de revisão por atributo e avaliação SUPPORTED/UNSUPPORTED/INCONCLUSIVE com identidade/evidência vinculadas.

### 5. Verificação e publicação

- [x] Medição integral comparada ao artefato anterior, com modelo desligado e amostras inspecionadas.
- [x] Back, MCP e API completos; PostgreSQL para API/MCP; contratos, tipos, front, build e estilo.
- [x] Revisão independente, correções verificadas, commit e push na branch do PR #272; atualizar descrição. Sem merge.

## Foco da revisão

Descrição curta contraditória/truncada; alias ambíguo; documento de outro dataset ou bytes alterados; trecho de IA ausente/não comprovante; propagação circular; fonte externa em material fictício; mudança de referência durante aprovação; pacote de avaliação alterado ou revisão inconclusiva.

## Verificação registrada

- Back completo: 1.215 testes passaram.
- API completa com PostgreSQL: 749 passaram. MCP completo com PostgreSQL: 378 passaram. Sem skips.
- Front: 89 testes, typecheck, contrato, build e formato passaram.
- Após os ajustes de grupo original/documental, módulos afetados reexecutados: 99 back e 30 API/PostgreSQL passaram.
- Ruff, formato Python, diff e política de branch/commits passaram.
- Medição final: 401 sugestões em 336 materiais; 232 potencialmente completos após aprovação. Amostra congelada de 100 candidatos sem rótulos.
- Entrega no PR #272, preservando a decisão de não fazer merge.
