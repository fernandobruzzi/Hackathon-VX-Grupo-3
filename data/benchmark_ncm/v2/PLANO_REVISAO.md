# Gabarito documental de NCM para todos os grupos — plano

> Execução sequencial solicitada pelo usuário: revisar todos os grupos, salvar as bases em `data/`, abrir PR e fazer merge conforme o fluxo do repositório.

**Objetivo:** cobrir os 23.554 cadastros dos 15 grupos de mercadoria, preservando os originais e a versão v1.

**Estrutura:** uma entrada consolidada sem rótulos, uma base consolidada com gabarito, referências separadas por grupo cadastrado e resumos por grupo/família. Cada alvo nasce da descrição e de características técnicas, antes de examinar o NCM de entrada.

**Referência:** nomenclatura reproduzida do Siscomex, datada de 29/09/2026; registrar limites de acesso e vigência, sem atribuir homologação fiscal independente.

## Restrições

- As 15 colunas originais e o kit do desafio são imutáveis.
- Preservar `data/benchmark_ncm/v1/`; rótulos sem evidência suficiente ficam pendentes.
- Não usar NCM cadastrado, moda da família ou referência PDM isolada como verdade.
- Não confundir código de peça com máquina completa, elemento de fechamento com função da válvula, pressão de trabalho com ruptura ou tensão de bobina com tensão do circuito.
- Todos os alvos de oito dígitos precisam existir na referência consultada; não inferir vigência posterior à cópia.

## Sequência de entregas

- [x] 1. Conferir fonte, esquema e escopo; ordenar os 15 grupos cadastrados e identificar as 80 famílias descritivas.
- [x] 2. Revisar em sequência cada grupo e suas famílias, com alvo único, evidência literal, regra e pendência. Registrar candidatos condicionais separadamente do gabarito.
- [x] 3. Consolidar as duas bases pareadas e os gabaritos por grupo. Documentar cobertura, correções dos rótulos anteriores e agrupamento de repetições.
- [x] 4. Verificar cobertura integral, preservação de dados, independência do NCM de entrada, códigos, evidências e contagens. O relatório está em `validacao_integridade.json`.

A integração segue a issue #293: executar as suítes e o estilo exigidos sobre a base atualizada; abrir PR, verificar CI, fazer rebase-merge e limpar a branch concluída. Os resultados desses passos ficam registrados no PR.

## Foco de revisão

1. Nomes parecidos podem ser produtos diferentes: luva EPI, conexão e peça mecânica exigem regras distintas.
2. Informação ausente pode impedir apenas o desdobramento final; prefixos e candidatos não devem virar alvos de oito dígitos automaticamente.
3. Peças com código próprio e materiais excluídos não recebem a classificação da máquina apenas pela aplicação.
4. Cadastros com NCM vazio e classificação inconclusiva continuam pendentes; vazio não é uma resposta correta de NCM.
5. Preservar IDs da v1 e registrar mudanças dos grupos de partição quando o universo aumenta.
