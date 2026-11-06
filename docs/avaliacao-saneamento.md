# Avaliação do saneamento

O relatório da #85 é uma **avaliação de desenvolvimento**, sem revisão técnica
independente. Acerto no PDM significa que um valor respeita o formato e os valores
permitidos; não prova que ele descreve o produto correto. Nenhuma métrica autoriza
unificação, publicação ou alteração fiscal.

## Executar sem banco ou AWS

Da raiz:

```bash
uv run vx-back sanitization-evaluate data/desafio01/01_base_materiais.csv --pdm-workbook data/desafio01/03_padrao_cadastro_PDM.xlsx
```

O comando só lê o kit e escreve JSON em stdout. Usa os mesmos repositórios de
classificação, extração, normalização, candidatos e correções do batch. Registra
hash do dataset, hash/versão do PDM e revisões das regras em `analysis_signature`.
`--repository` seleciona os candidatos. Para verificar no pacote instalado:

```bash
docker compose run --rm --no-deps --build batch vx-back sanitization-evaluate /app/data/desafio01/01_base_materiais.csv --pdm-workbook /app/data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Resultado registrado: [sanitization-development-v1.json](measurements/sanitization-development-v1.json).
Reexecute depois da correção de identidade da #73. A homologação independente
posterior está registrada na #113. Os erros conhecidos continuam
visíveis até deixarem de ser propostos; o relatório não altera o algoritmo.

## Coortes e unidades

| Coorte | Unidade | Seleção e limite |
|---|---|---|
| 40 grupos históricos | Proposta/grupo inteiro | Sorteio original com semente 32; rótulos lidos no desenvolvimento, sem especialista |
| 95 pares históricos | Par de materiais | Escolhidos durante o desenvolvimento; regressões, não amostra aleatória da base |
| 17 materiais técnicos | Atributo rotulado | Sete classes, seleção dirigida com dimensões, pressão, aliases, ausências, ambiguidade e erros conhecidos |
| Colunas ocultas | FABRICANTE ou referência preenchida | Apenas FIL01/SOB01 classificáveis; as colunas do kit são o proxy de gabarito |
| Redirecionamentos | Par positivo declarado no kit | 202 relações `USAR COD`; compara chaves extraídas, não propostas aplicáveis nem falsos positivos |

Cada taxa traz numerador e denominador. **Precisão** usa somente previsões com
rótulo decidido; dúvidas permanecem contadas e recebem limites de sensibilidade.
**Cobertura de previsão** conta quantos casos receberam proposta. **Cobertura de
revisão** conta rótulos decididos. **Abstenção** conta casos sem proposta, incluindo
grupos alterados que não podem herdar a revisão. **Recuperação** divide os positivos
encontrados pelos positivos conhecidos daquela coorte; não é recall de todas as
duplicidades da base. Sem denominador, o valor é `null`.

A cobertura da base inteira reaproveita o cálculo do batch: um desfecho por material,
com soma igual ao total de entrada. Proposta, pendência e registro sem mudança não
significam acerto técnico. Motivos de pendência podem se sobrepor.

Um grupo incorreto não torna automaticamente negativos todos os seus pares. A
avaliação por pares usa seus próprios rótulos. Grupos ampliados ficam como
`CHANGED_GROUP`; grupos retirados ficam `NOT_PROPOSED`, mantendo os códigos e a
história anteriores. Uma nova amostra não substitui a coorte histórica.

## Rótulos e revisão

As cópias congeladas ficam em `pipelines/evaluation_data`, incluídas na imagem
batch. O manifesto guarda os hashes das fontes e do dataset. Alterar uma cópia
sem atualizar sua versão é recusado. A seleção corrente do algoritmo não é usada
para reescrever os casos antigos.

Os autores das revisões legadas não foram registrados: aparecem como
`UNRECORDED_LEGACY`, sem inventar autoria ou independência. Os novos artefatos
identificam `bepo7` como responsável de desenvolvimento (`DEVELOPMENT_ARTIFACT_OWNER`),
o que não representa certificação pessoal por especialista. A amostra técnica
registra o texto original e os campos efetivamente rotulados. `null` num atributo
significa que o texto não sustenta um preenchimento inequívoco, não que o produto
fisicamente não tenha esse atributo. Os demais campos não entram no gabarito.
Separadores de referência são ignorados na comparação de grafia, mas `REV A` e
`-00` não são removidos pelo avaliador como se provassem intercambiabilidade.

Cada revisão de grupo/par exige `author`, `label` booleano ou nulo e uma lista
não vazia de `evidence`. Dois registros do mesmo autor não contam como duas
revisões. Discordância entre revisores ou qualquer dúvida explícita deixa o caso
inconclusivo; não há voto de maioria. Uma resolução técnica exige evidência e
nova revisão versionada, preservando a história. A inspeção feita durante o
ajuste do algoritmo continua sendo desenvolvimento, mesmo que os textos tenham
sido separados das previsões.

Os três grupos com `REV A` conservam o rótulo histórico positivo e a observação
original, mas passam a inconclusivos na avaliação atual: faltou confirmar sua
intercambiabilidade. Os dois grupos errados da #73 continuam como contraexemplos.

Para registrar outra versão, copie a pasta da coorte, preserve os arquivos
históricos, acrescente revisões no manifesto e selecione-o explicitamente:

```bash
uv run vx-back sanitization-evaluate data/desafio01/01_base_materiais.csv --pdm-workbook data/desafio01/03_padrao_cadastro_PDM.xlsx --cohort-manifest /caminho/coorte-v2/manifest.json
```

Esse comando continua identificado como desenvolvimento. Um conjunto independente
precisa ser congelado antes de afinar regras, revisado por pessoas fora desse
ajuste e homologado antes de fundamentar números do produto.

## Incerteza e comunicação

Nos grupos decididos, o relatório calcula o intervalo bilateral de Wilson a 95%,
com a [formulação do NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
Ele é condicional à parte decidida da coorte e à hipótese binomial; não corrige
viés de seleção, ausência de revisão independente ou dúvidas sistemáticas nos
rótulos. Os limites incluindo rótulos desconhecidos mostram separadamente a
sensibilidade a essas dúvidas. Pares e atributos correlacionados de uma seleção
dirigida não recebem intervalo binomial apresentado como populacional.

Com as regras registradas no primeiro relatório, a coorte de grupos apresenta
35/37 decididos (94,59%), dois erros e três dúvidas em 40 grupos. O intervalo
condicional fica aproximadamente em 82,30%–98,50%; os limites de sensibilidade
incluindo as três dúvidas são 87,5%–95%. Isso não é uma estimativa independente
de precisão da base inteira. Um resultado 60/60 na coorte de pares de regressão
não contradiz esses erros: os denominadores e a seleção são diferentes.

O dashboard mantém precisão e recall indisponíveis até haver uma avaliação
independente homologada, sem importar este relatório de desenvolvimento. O pitch
pode citar os casos demonstrados e as limitações; não deve chamar esses resultados
de precisão de produção, recuperação de todas as duplicidades ou economia realizada.
