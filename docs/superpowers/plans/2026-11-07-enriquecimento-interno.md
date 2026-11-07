# Enriquecimento interno e completude — #263

## Objetivo e abordagem

Integrar ao saneamento a medição de completude e propostas de preenchimento com evidência dos arquivos originais. Reutilizar o classificador, extrator, decisão de identidade, armazenamento imutável e aprovação de enriquecimento existentes. A instrução do usuário de prosseguir autoriza a execução neste chat.

Fontes: base original e texto/anexos dos pedidos, delimitados pelo manifesto do dataset e seus hashes. PDM define atributos, condições e valores válidos; não fornece valores de produto. Pesquisa externa continua no fluxo dos 15 produtos reais; NCM oficial permanece na #30. Não há promessa de completude sem fonte.

## Etapas

1. Testar e implementar relatório por material: atributos ausentes, inválidos, condicionais pendentes e opcionais; indexar fontes pela identidade e confirmar cada vínculo pelo motor compartilhado. Guardar divergências, registro, trecho, regra e hash. Não inferir obrigatórios técnicos ausentes por semelhança.
2. Reutilizar a publicação e aprovação de ENRICHMENT para fontes internas com contexto próprio e evidências vinculadas ao dataset. Preservar unidade, NCM e atributos conhecidos; mudanças parciais não tornam o material canônico. Revalidar contexto e impedir evidência externa no caminho interno.
3. Integrar no SANITIZE com relatório imutável, métricas e pendências; considerar atributos já aprovados na próxima execução. Manter idempotência e vincular propostas ao job.
4. Executar análise integral do kit e registrar resultados e limites. Validar suítes back, MCP e API, incluindo PostgreSQL para publicação/aprovação. Não alterar dados de produção.

## Verificações essenciais

Identidade incompleta; referências/sufixos e fabricantes diferentes; valores contraditórios entre fontes; atributos condicionais; corrupção do arquivo original; alteração de evidência ou versão; aprovação parcial; repetição sem novas propostas após aprovação; preservação de estoque, unidade e NCM. A contagem de campos sugeridos não é contagem de campos aplicados.
