# Do Fundo do Poço — Identidade de apresentações ("Ascensão")

Como o time apresenta no hackathon: decks web interativos (um `index.html`),
com HUD de apresentador, demos ao vivo e exportação para PDF. É a versão
Do Fundo do Poço da skill `interactive-deck`, com as mesmas exigências
(cronômetro, ritmo, notas, keyframes, deploy no Vercel) e a identidade de
`../design-system/`.

- `template/` — deck inicial pronto para copiar: 13 slides com todos os
  layouts abaixo, uma demo funcionando, fontes e logos **embutidos no
  `index.html`** (abre sozinho, até no preview do app), `vercel.json`.
- `previews/` — capturas dos layouts nos dois temas e o PDF exportado do
  template (`template-exemplo.pdf`, 15 páginas: 12 slides + 3 keyframes da demo).
- A skill `/do-fundo-do-poco-interactive-deck` monta um deck novo a partir daqui.

Se este README e o design system discordarem nas cores, o design system vence.

## O conceito: ascensão

O nome é a história de todo pitch: começar no fundo (o problema) e subir (a
solução). A identidade "Ascensão" desenha isso com os vetores do kit:

- **Curvas** — o anel do poço cortado vira as curvas que entram pelos cantos.
  A capa usa as curvas de `12_fundo_apresentacao.svg` (`--apoio` + `--esmeralda`)
  sangrando à direita; os divisores usam `10_elemento_curvas.svg` no canto.
- **A subida** — cada divisor mostra um trilho com um degrau por seção e a
  seta do kit (`09_seta.svg`) parada no degrau da seção atual. Ao longo do
  deck a seta sobe. O engine gera isso a partir das `section.divider`.
- **Eyebrow de seção** — `01 / O problema`: número em `--verde`, rótulo em
  `--text`, Montserrat 800 em caixa alta, barrinha esmeralda de 56×4px embaixo.
  É o "01 / ASCENSÃO" do board.
- **Marcadores** — a seta, pequena, em esmeralda.
- **Plano e arredondado** — cards de 12px, painéis de 24px, sem sombra, sem
  contorno. O destaque de um slide é um bloco `--profundo` (verde-escuro).

O logo entra só pelos arquivos do kit (horizontal na capa, vertical no
fechamento), na versão clara ou escura conforme o tema — o deck troca sozinho.

## Tema

- **Claro (off-white `#F5F3ED`) é o padrão para projetar.**
- **Escuro (verde-escuro `#102C26`)** com a tecla `D`, ou automático via
  `prefers-color-scheme` se o `data-theme` for removido do `<html>`.
- Divisores são sempre escuros (bloco `--profundo`), nos dois temas.
- **O PDF sai sempre no claro**: o export força o tema e restaura depois.

## Regras de slide

- **Esmeralda é forma, não texto, no claro** (1,98:1 no off-white): seta,
  curvas, barras, fundo do CTA. Texto verde é `--verde` (`#0A6E48` no claro,
  esmeralda no escuro).
- **Um destaque por slide**: um bloco `--profundo`, ou um número grande em
  `--verde`. `--alerta` no máximo uma vez, sempre com palavra.
- **Pouco texto no slide.** Tópicos, números e frases curtas; o que falar vai
  em `data-notes` (tecla `N`).
- **Números em formato brasileiro** (vírgula decimal, `R$ 120 mil`, `6,2 h`)
  e sempre com a referência: "94,7% (atual 81,0%)".
- **Fonte em todo número de problema/mercado**, no `.src` do slide.

## Tipografia no palco 1280×720

Montserrat para tudo; IBM Plex Mono só para leituras, código e rodapé.

| Classe | Fonte | Tamanho | Uso |
|---|---|---|---|
| `.big` | Montserrat 800, CAIXA ALTA | 80–180px | Capa, divisores, número do problema, "Perguntas?" |
| `.t` | Montserrat 800 | 40px | Título de slide (sentence case, ≤ 2 linhas) |
| `.eb` | Montserrat 800, CAIXA ALTA | 15px | `<b>01</b> / Rótulo` + barrinha esmeralda |
| `.kicker` | Montserrat 700, tracking 0,5em | 15px | linha estilo "H A C K A T H O N" |
| `.lead` | Montserrat 400 | 21px | Subtítulo, frase de apoio |
| corpo / `ul.pts` | Montserrat 400 | 19px | Tópicos com seta esmeralda |
| `.card h3` | Montserrat 700 | 21px | Título de card |
| `.ro` / `.ro.main` | Plex Mono 15px / Montserrat 800 56px | | Leituras de demo; o número principal |
| `.foot` | Plex Mono 12px + nome do time em Montserrat 800 | | Rodapé injetado |

## Layouts do template

| # | Slide | Classe / padrão | Preview |
|---|---|---|---|
| 1 | Capa | `.cover` — logo horizontal, eyebrow do desafio, `.big`, time, curvas do kit | `claro-01.png`, `escuro-01.png` |
| 2 | Roteiro | `.g4` de cards, o da demo em `.card.hi` | |
| 3 | Divisor | `.divider` — bloco escuro, eyebrow, `.big`, curvas, a subida | `claro-03.png` |
| 4 | Problema em um número | `.big` gigante + tópicos + `.src` | |
| 5 | Solução | `.g2`: tópicos + `.card.hi` com `.sim-tag` e `.eq` | `claro-05.png` |
| 6 | Como funciona | `.pipe` — etapas ligadas por setas, a ativa em `--profundo` | `claro-06.png` |
| 7 | Demo | canvas + controles + leituras + `.sim-tag` + mensagem didática | `claro-07.png`, `escuro-07.png` |
| 9 | Resultados | `.g3` de `.metric`: valor, barra esmeralda (nós), traço (método atual) | `claro-09.png` |
| 10 | Comparação | `table.cmp`, nossa linha em `--profundo` | |
| 11 | Próximos passos | `.g3` com prazos | |
| 12 | Síntese | 4 cards, cada um amarrado a um momento do pitch | |
| 13 | Perguntas | `.closing` — `.big`, logo vertical, cards do time, links | `claro-13.png` |

## Componentes de demo

- **`.sim-tag`** — pílula `--profundo` com ponto esmeralda, em toda demo:
  `simulação`, `dados reais`, `amostra`, `agregado`, `protótipo`, `modelo treinado`.
- **`.ctl`** (label + `<output>` + range em `--verde`), **`.seg`** (botões com
  `aria-pressed`, ativo em esmeralda com texto verde-escuro), **`.checks`**,
  **`.btn.pri`** (esmeralda + verde-escuro) / **`.btn.ghost`**.
- **`.msg`** — mensagem didática com filete `--alerta` quando o público faz a
  coisa "errada".
- **Gráficos** — séries `--serie-1..4`. No claro a série 1 é `#0C8A5A`
  (esmeralda escurecido, 3,9:1 no off-white) porque marca com significado
  precisa de 3:1; no escuro é o esmeralda. Erro = `--alerta`, "não
  aconteceu" = contorno tracejado `--alerta`.
- **Foco** em `--verde`, 2px, offset 2px; `aria-label` em todo canvas.

## HUD do apresentador

| Tecla | Ação |
|---|---|
| ← → Espaço PageUp PageDown Home End | navegar; clicar num segmento do progresso pula para o slide |
| T / ▶ | iniciar/pausar cronômetro |
| R R / ↺ ↺ | zerar |
| N | notas (título, minutos, início previsto, notas, próximo) |
| D | tema claro/escuro |
| F | tela cheia |
| P / PDF | exportar PDF com keyframes |
| ? / Esc | atalhos / fechar |

- Relógio `mm:ss / total`, ritmo "no ritmo / X atrasado / X adiantado".
- **Tolerância do ritmo = 5% do total, mínimo 5 s.**
- Barra de orçamento do slide fica vermelha quando estoura.
- Funciona dentro de preview em sandbox: URL, tela cheia e impressão
  bloqueadas não quebram a navegação.

## Orçamento de tempo para hackathon

| Slide | `data-min` |
|---|---|
| capa, roteiro | 0,25 |
| divisor | 0,1 |
| slide comum | 0,4–0,75 |
| demo ao vivo | 1–2 |
| Perguntas | 0 |

Estrutura do template (6 min): capa → roteiro → problema → solução → como
funciona → **demo** → resultados → comparação honesta → próximos passos →
síntese → perguntas. Ajuste ao tempo do edital e aos critérios da banca.

## Demo de exemplo (slide 7)

Detecção de anomalia por limiar em σ sobre um sinal simulado (semente 7).
Os três keyframes do PDF, conferidos fora do navegador com
`template/demo_check.py`:

| Estado | Resultado |
|---|---|
| k = 3σ | 8 acertos, 0 falsos — recall 100% |
| k = 1,5σ | 8 acertos, 30 falsos — precisão 21%, aparece a mensagem de alarme demais |
| k = 5σ | 3 acertos, 5 perdidas — recall 38% |

Os números dos slides 4 e 9 são de exemplo: troque pelos reais.
