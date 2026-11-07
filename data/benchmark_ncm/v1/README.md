# Benchmark documental de NCM — v1

Par de bases congeladas para avaliar NCM de parafusos, válvulas e anéis. Cada arquivo tem **6.271 cadastros**, na mesma ordem, com os mesmos identificadores e as 15 colunas originais preservadas.

| Arquivo | Uso | Colunas |
|---|---|---:|
| [base_sem_gabarito.csv](base_sem_gabarito.csv) | Entrada do sanitizador; conserva o NCM original a corrigir ou preencher | 18 |
| [base_com_gabarito.csv](base_com_gabarito.csv) | Referência de avaliação; inclui alvos, evidências, regras e pendências | 32 |
| [manifesto.json](manifesto.json) | Versão, procedência, esquema, contagens e SHA-256 dos CSVs | — |

A entrada contém as 15 colunas originais mais `ID_BENCHMARK`, `GRUPO_PARTICAO` e `LINHA_ORIGEM`. Os campos de resposta e de revisão aparecem somente na base com gabarito; não forneça essa versão ao sanitizador.

## Cobertura

| Família | Cadastros | NCM pontuável | Revisão técnica pendente |
|---|---:|---:|---:|
| Parafusos | 3.730 | 3.713 | 17 |
| Válvulas | 1.338 | 1.338 | 0 |
| Anéis | 1.203 | 857 | 346 |
| **Total** | **6.271** | **5.908** | **363** |

Nos 5.908 pontuáveis, a entrada tem 5.213 NCMs corretos, 395 incorretos e 300 ausentes. Os demais 363 não têm alvo NCM definitivo: são 17 parafusos sem material/classe técnica conclusiva, 44 O-rings sem composição e 302 anéis mecânicos que dependem de catálogo/desenho. Entre os pendentes há outros 20 NCMs vazios; não contá-los como preenchimentos com resposta conhecida.

## Avaliação

1. Execute o sanitizador sobre `base_sem_gabarito.csv` e una as previsões ao gabarito por `ID_BENCHMARK`.
2. Pontue NCM apenas onde `ELEGIVEL_BENCHMARK_NCM=true`. Compare a previsão normalizada com `NCM_GABARITO`.
3. NCM com pontos/espaços equivale ao mesmo código de oito dígitos: `7318.15.00` e `73181500` são a mesma classificação. Aceite somente dígitos, pontos e espaços antes da normalização; não extraia números de texto inválido nem complete/trunque códigos.
4. Nos pendentes, avalie encaminhamento para `REVISAO_MANUAL`, sem usar alvo vazio como resposta correta de classificação.
5. Relate preservação dos corretos, correção dos incorretos e preenchimento dos ausentes, separados por família. Manter o cadastro já alcança 88,24% de acurácia nos pontuáveis; cobertura documental de 94,21% não é acurácia do sanitizador.
6. Em uma eventual partição de desenvolvimento/teste, mantenha cada `GRUPO_PARTICAO` inteiro. Os grupos reúnem descrições repetidas e referências de fabricante; nenhuma partição foi criada nesta versão.

O alvo foi derivado das características descritivas, independentemente do NCM cadastrado. Na revisão das válvulas, a função retenção prevalece sobre o elemento esfera: uma válvula de retenção tipo esfera recebe `84813000`, não `84818095`.

## Procedência e limites

O manifesto identifica o arquivo recebido, seu hash, a versão e as fontes. O CSV com gabarito é cópia exata do artefato documental revisado; não substitui rótulos ou coortes anteriores do projeto. O kit em `data/desafio01/` não foi alterado.

A reprodução pública da tabela atribuída ao Siscomex está datada de **29/09/2026**. A consulta direta ao portal ficou bloqueada pela rede; não foi confirmada atualização posterior. Os rótulos são documentais e não têm homologação fiscal nem revisão humana independente registrada. A compatibilidade com a descrição não substitui certificado, inspeção física ou análise completa das notas legais. Não apresentar este corpus como avaliação externa independente do método que o produziu.

Arquivos CSV em UTF-8 com BOM, delimitador vírgula e cabeçalho. Trate NCM, códigos e identificadores como texto. Preserve esta versão e seus hashes; correções futuras devem criar uma nova versão, com evidência e autoria da revisão.
