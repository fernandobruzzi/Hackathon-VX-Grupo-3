# Preparar a revisão independente

A homologação da #113 permanece **pendente**: não há revisor técnico independente
nomeado nem evidência confirmada de intercambiabilidade de revisões de peça. O
exportador prepara material de trabalho; não atribui autoria, não rotula casos e
não publica métricas. A avaliação de desenvolvimento da #85 continua separada.

Da raiz, sem banco ou AWS:

```bash
uv run vx-back review-handoff data/desafio01/01_base_materiais.csv --pdm-workbook data/desafio01/03_padrao_cadastro_PDM.xlsx --seed 113 --size 40 > /tmp/revisao-preparo.json
```

O JSON contém hashes de dados, PDM e fontes Python instaladas, versões do Python e
openpyxl, assinatura das regras, frame completo de propostas ordenado por ID e a
seleção reproduzível feita por `sample_merges`. O tamanho efetivo é limitado ao
frame disponível. A unidade é o grupo inteiro; pares de um grupo não são novas
observações independentes. O frame contém somente propostas MERGE: não permite
estimar recall nem avaliar materiais sobre os quais o algoritmo se absteve.

`review_cases` guarda todas as colunas originais dos membros selecionados e fichas
vazias por grupo, classe e campo. `predictions` guarda as previsões separadamente.
As fichas de campo usam os nomes da classe prevista, portanto isso não constitui
cegamento completo; o revisor deve poder corrigir a classe e acrescentar campos.
Guarde o pacote original imutável e seu `packet_sha256`; o hash usa o JSON com
`ensure_ascii=False, sort_keys=True`, antes de acrescentar a própria chave.

Entregue ao revisor uma cópia das fichas com o hash do pacote, os originais e o PDM,
mantendo previsões e rótulos históricos separados durante a primeira leitura.
Preencher `author`, participação no ajuste das regras, evidência técnica e
conflitos exige revisão real; os `null` iniciais significam ausência de revisão,
nunca aprovação. No grupo, `label` responde se todos os membros são o mesmo item:
verdadeiro, falso ou nulo (inconclusivo). Na classe/campo, `value` registra a
classe/valor técnico sustentado ou permanece nulo; mantenha `label` vazio na
primeira leitura e registre acerto/erro/inconclusivo somente ao comparar com a
previsão separada. Registre cada revisor em uma cópia identificada e preserve divergências,
sem votar por maioria nem alterar a folha original. O comando não importa essas
respostas nem decide sua homologação.

Para anexar um histórico fornecido, acrescente `--historical-source caminho.json`
(repetível). O arquivo deve trazer sua origem conhecida, por exemplo commit/URL e
método; o pacote conserva caminho, hash dos bytes e documento inteiro em
`historical_sources`. Rótulos antigos nunca preenchem as fichas. O exportador não
busca históricos na rede nem inventa conclusões sobre `REV A`; forneça as fontes
da coorte e os registros técnicos pertinentes quando disponíveis.

Esta preparação usa as regras presentes no momento da execução. A correção de
identidade #73 e o protocolo da #85 já estão integrados: **gere um novo pacote
nessa base**, registre/congele a nova coorte e o protocolo antes de ajustar regras
a partir dos seus resultados e preserve as coortes anteriores. Uma semente
nova não garante independência. Nomeação de revisores fora do ajuste, evidência
de intercambiabilidade e homologações separadas para dashboard e pitch continuam
necessárias; nenhum dado deste pacote autoriza unificação ou publicação.
