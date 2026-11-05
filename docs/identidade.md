# Identidade, equivalência e revisão de peças

A [#73](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/73)
corrige duas unificações erradas encontradas na amostra da #32, sem alterar os
arquivos originais nem aplicar mudanças ao cadastro.

## Regras compartilhadas

As decisões ficam em `back/domain/identity.py`, versão `identity-v2`.
Os repositórios de candidatos continuam selecionáveis; todos devem respeitar
essas restrições. O construtor de propostas recusa grupos inseguros mesmo se
outro algoritmo os declarar verificados.

- Fabricantes diferentes permanecem separados, inclusive em classes técnicas
  sem o atributo FABRICANTE. O campo estruturado original continua relevante.
  A normalização resolve caixa, acentos e espaços; não supõe relações entre marcas.
- Um fabricante ausente não conecta dois fabricantes conhecidos. Itens sem
  fabricante continuam podendo ser comparados entre si pelas regras do PDM.
- Nomes de peças diferentes ficam separados, mesmo com a mesma chave de referência.
- Um valor que coincide com um MODELO EQUIPAMENTO do catálogo não comprova uma
  referência de peça, inclusive quando vem rotulado como PN ou em coluna estruturada.
  Um PN numérico que não coincide com esses modelos continua utilizável.
- Modelos numéricos explícitos do PDM, como `6030`, são extraídos como modelo.
  Não viram REFERENCIA FABRICANTE por sobra do texto.
- Marcadores como `REV A`, `REV. 01` e `REVISÃO A` são preservados. A falta de
  confirmação de intercambiabilidade impede MERGE, mesmo se os dois registros
  disserem a mesma revisão. Não existe comprovação técnica para liberá-los aqui.
  A palavra REVESTIMENTO não é um marcador de revisão.

As regras não identificam todos os modelos possíveis fora do catálogo. Referências
livres ainda exigem evidência e revisão. Um modelo desconhecido não deve ser
adicionado como referência apenas para aumentar cobertura.

## Os dois erros reproduzidos

| Materiais originais                     | Problema                                              | Resultado atual                                                        |
| --------------------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------- |
| `17590309` PETRONAS e `27863373` MOBIL  | Mesmos atributos de óleo 5W40, fabricantes diferentes | Nenhum MERGE entre eles; candidato a equivalência técnica para revisão |
| `19547027` BUCHA e `22125549` RODA GUIA | `6030`, modelo da escavadeira, era lido como PN       | Modelo preservado, referência ausente e revisão manual; nenhum MERGE   |

Os testes leem essas linhas diretamente do CSV original. As versões observadas,
descrições e campos estruturados ficam no relatório de evidência.

## Equivalências e pendências

Do diretório `back/`, sem banco ou conta AWS:

```bash
uv run vx-back sanitize-report ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Além das contagens e correções, a resposta contém `identity_review`:

- `equivalence_candidates`: mesma identidade técnica, mesmo nome de item e
  fabricantes distintos conhecidos. O estado é `REVIEW_REQUIRED`, com
  `identity_verified: false`. Isso registra semelhança técnica, não comprova
  substituição, equivalência de desempenho ou intercambiabilidade.
- `manual_review`: material e motivos, por exemplo
  `REFERENCIA_DE_PECA_AUSENTE`, `MODELO_NAO_E_REFERENCIA`,
  `REVISAO_DE_PECA_NAO_CONFIRMADA` ou `FABRICANTE_CONFLITANTE`.
- Versões das regras e do PDM, hash do PDM e evidências com descrição,
  fabricante e referência originais, código, versão observada e atributos extraídos.

O comando acima só imprime o relatório. `vx-back sanitize`, com o banco local
configurado, guarda o mesmo diagnóstico via `clients/storage.py`, em
`runs/<tenant>/identity-review/<sha256>.json`, e retorna `identity_review_key`.
Repetir o mesmo conteúdo reaproveita a chave. O armazenamento local é o padrão;
S3 usa o mesmo cliente quando configurado. Esse artefato não entra como MERGE nem
como novo tipo de proposta na fila de aprovação. Os dados financeiros não são
copiados para o diagnóstico.

No Compose, o batch monta o volume `storage-data` em `/storage`, como o bootstrap.
A imagem prepara essa pasta para o usuário sem privilégios; o relatório persiste
entre execuções do container.

Não há edição do cadastro, consolidação de quantidades ou alteração fiscal.
Propostas gravadas por versões anteriores não são apagadas ou aprovadas por
esta correção: os casos inseguros antigos precisam ser recusados ou revistos
pela Governança antes de qualquer aplicação.

## Busca no MCP

A busca reutiliza a revisão de referência e fabricante do domínio, incluindo os
campos estruturados da view autorizada. Uma chave coincidente do índice não
supera uma revisão pendente, conflito ou fabricante diferente/desconhecido.
Esses candidatos continuam pesquisáveis, mas não viram identidade verificada.

A versão do índice passa a incluir `identity-v2`. Depois de atualizar o código,
reconstruir com `vx-back index` ou `docker compose run --rm batch`; a consulta
recusa um índice anterior em vez de comparar identidades de regras diferentes.

## Reavaliação da amostra fixa da #32

A fixture foi preservada, com os rótulos originais e a referência ao commit
`42a2b6ce5cd29f79de8e10304239378ab58a0ee5` do
[PR #71](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/71).
Usa um nome próprio para não depender do merge daquele PR nem alterar sua amostra.
Não foi sorteada outra amostra para substituir os erros conhecidos.

Do diretório `back/`:

```bash
uv run python -m pipelines.measure_merge_identity ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Resultado reproduzido em 6/11/2026, com hashes em
[`evidence/merge-identity-73.json`](evidence/merge-identity-73.json):

| Medida                                                   | Antes                          | Com as novas regras                                           |
| -------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------- |
| Propostas MERGE na base de 23.554 linhas                 | 1.147, segundo a rodada da #32 | 1.049                                                         |
| Grupos da coorte revisada                                | 40: 38 corretos e 2 errados    | 34 grupos remanescentes, 34 corretos e nenhum erro conhecido  |
| Precisão condicionada aos grupos remanescentes da coorte | 38/40 = 95%                    | 34/34 = 100%                                                  |
| Diagnóstico na base inteira                              | Não registrado nesse formato   | 5 grupos de equivalência técnica e 549 materiais para revisão |

**O percentual não estima a precisão da base inteira.** A coorte tem apenas
40 grupos revisados durante desenvolvimento, sem validação de especialista.
A seleção mudou após a correção; os 34 grupos são os remanescentes dessa coorte,
não uma nova amostra aleatória das 1.049 propostas atuais.

Os dois grupos errados deixam de existir como MERGE. Outros quatro grupos
antes rotulados corretos ficam sem MERGE por revisão pendente de peça. Um quinto
grupo mantém apenas os dois membros sem revisão, excluindo o membro `REV A`.
Isso prioriza evitar junções erradas, com perda explícita de cobertura.

As três revisões apontadas inicialmente são `23858996`, `29993231` e `27417776`.
A releitura dos campos originais encontrou ainda `25383520` e `26850088`, também
com `REV A`. Os cinco ficam para confirmação pela manutenção; não foram
reclassificados como tecnicamente confirmados para melhorar a métrica.

Nos 202 pares declarados `USAR COD`, 62 continuam encontrados pelas regras de
candidatos. Os testes contam encaminhamentos para revisão separadamente, sem
confundi-los com identidade confirmada nem reduzir o piso anterior de cobertura
de casos tratados. Uma nova medição aleatória e revisão de especialistas são
necessárias antes de generalizar os resultados ou atualizar o número do pitch.

A amostra própria `back/tests/fixtures/merge_identity_sample_73.json` também foi sorteada novamente com a semente 32 e revisada lendo os textos e campos originais: 40/40 grupos compatíveis. Ela está marcada como `DEVELOPMENT_REGRESSION`, sem independência ou validação de especialista; não substitui a coorte fixa nem comprova precisão populacional.

As duas coortes históricas da avaliação de saneamento permanecem preservadas, com seus rótulos e dúvidas. A amostra da #73 é adicional e não as substitui.

Na coorte histórica após aliases, o avaliador congelado registra 40 grupos, 38
revisões conclusivas e duas inconclusivas. As regras atuais propõem 31 grupos,
todos concordantes com os rótulos conclusivos existentes. Dos 37 positivos
históricos conclusivos, seis deixam de ser propostos; também ficam retidos os
dois inconclusivos e o erro conhecido. A recuperação nessa coorte é 31/37 e a
abstenção é 9/40. A precisão condicionada de 31/31 não remove essa perda de
cobertura e não constitui validação independente. Os rótulos e hashes das coortes
continuam inalterados; `sanitization-evaluate` reproduz os casos individualmente.
