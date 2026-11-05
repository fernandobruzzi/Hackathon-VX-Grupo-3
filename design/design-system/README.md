# Do Fundo do Poço — Brand Guidelines ("Ascensão")

Identidade do time Do Fundo do Poço (hackathon de problemas de engenharia
resolvidos com IA), versão **Ascensão**: o poço visto de cima com uma seta
saindo dele. Esta pasta é a referência portátil para site, decks, dashboards,
redes e impressão. Mesma estrutura do design system pessoal (`design-guidelines/`).

Abra `colors.html` e `typography.html` no navegador para a referência visual.
Os logos vetoriais estão em `assets/logo/` (veja `LEIA-ME.txt` do kit). As
fontes estão em `fonts/`.

> A identidade anterior (logo com poço de tijolos, Saira Condensed, adesivo e
> chanfro) foi aposentada. Os arquivos antigos estão em `_to_delete/`.

## Paleta da marca (do kit)

| Nome | Hex | Papel |
|---|---|---|
| Verde-escuro | `#102C26` | o poço — texto, logo, fundo escuro |
| Esmeralda | `#16C784` | a ascensão — seta, curvas, CTA, destaques |
| Off-white | `#F5F3ED` | o fundo claro |
| Verde de apoio | `#0D4939` | curva de fundo das artes escuras (`12_fundo_apresentacao.svg`) |

**Esmeralda não é cor de texto no claro.** `#16C784` sobre `#F5F3ED` dá 1,98:1:
não passa nem para título grande. No claro ele é forma (seta, curvas, barras,
preenchimento do botão com texto verde-escuro); texto verde usa `--verde`
`#0A6E48`, um esmeralda escurecido. O "HACKATHON" esmeralda do logo segue
como está no arquivo (logo não é texto corrido), mas não se copia esse uso
em UI.

## Tema claro — "superfície" (padrão)

| Token | Hex | Papel |
|---|---|---|
| `--ink` | `#F5F3ED` | fundo da página (off-white) |
| `--surface` | `#FFFFFF` | cards, nav, campos |
| `--surface-2` | `#E3DED2` | bordas, divisores, inset |
| `--text` | `#102C26` | texto principal (13,4:1) |
| `--text-muted` | `#4F5E57` | texto secundário (6,2:1) |
| `--verde` | `#0A6E48` | **acento de texto** — links, eyebrows, números de seção (5,7:1) |
| `--verde-glow` | `#085A3B` | hover de link |
| `--esmeralda` | `#16C784` | forma: seta, curvas, barras, fundo do CTA |
| `--on-esmeralda` | `#102C26` | texto sobre esmeralda (6,8:1) |
| `--profundo` | `#102C26` | blocos escuros de destaque |
| `--apoio` | `#0D4939` | segunda cor das curvas, blocos |
| `--on-profundo` | `#F5F3ED` | texto sobre profundo/apoio (13,4:1 / 9,3:1) |
| `--alerta` | `#B3261E` | nota rara — erro/falha, sempre com palavra |
| `--info` | `#1D5FA6` | informação neutra, 3ª série de gráfico |

## Tema escuro — "fundo do poço"

| Token | Hex | Papel |
|---|---|---|
| `--ink` | `#102C26` | fundo da página (verde-escuro) |
| `--surface` | `#173B33` | cards, nav |
| `--surface-2` | `#24503F` | bordas, divisores |
| `--text` | `#F5F3ED` | texto principal (13,4:1) |
| `--text-muted` | `#A9BDB3` | texto secundário (7,5:1) |
| `--verde` | `#16C784` | acento de texto — no escuro o esmeralda puro passa (6,8:1) |
| `--verde-glow` | `#43D79B` | hover |
| `--esmeralda` | `#16C784` | forma, CTA |
| `--on-esmeralda` | `#102C26` | texto sobre esmeralda |
| `--profundo` | `#0D4939` | blocos (no escuro o apoio faz o papel, senão some no fundo) |
| `--apoio` | `#0D4939` | curvas |
| `--on-profundo` | `#F5F3ED` | |
| `--alerta` | `#FF8A7A` | |
| `--info` | `#8CBCF5` | |

## Logo

Arquivos em `assets/logo/` — vetores com letras em curva, sem fonte externa.

| Arquivo | Quando usar |
|---|---|
| `01_logo_horizontal.svg` | padrão, fundo claro |
| `02_logo_horizontal_fundo_escuro.svg` | fundo `#102C26` ou foto escura |
| `03_logo_vertical.svg` / `04_…_fundo_escuro.svg` | capa, cartaz, espaços quadrados |
| `05_logo_monocromatica.svg` | impressão em 1 cor, carimbo |
| `06/07/08_icone_*.svg` | ícone isolado: verde-escuro, esmeralda, branco (sobre escuro) |
| `09_seta.svg` | a seta sozinha — marcador, indicador de progresso |
| `10_elemento_curvas.svg` | curvas de apoio para cantos de layout |
| `11_avatar.svg` | foto de perfil, favicon |
| `12_fundo_apresentacao.svg` | capa de slide 16:9 escura |
| `13_prancha_identidade.svg` | referência da identidade |

- Respiro mínimo: a altura da seta em volta do logo. Largura mínima do
  horizontal: 160px; abaixo disso use o ícone.
- Não recolorir fora das três cores, não esticar, não separar a seta do anel
  (exceto o `09_seta.svg`, que é o elemento oficial isolado).

## Regras de uso

- **Esmeralda é a ascensão.** Use na seta, nas curvas, no CTA e numa barra ou
  número por tela. Se o esmeralda aparecer em mais de um lugar grande, corte.
- **Texto verde é `--verde`.** No claro `#0A6E48`; no escuro o esmeralda.
- **CTA**: fundo `--esmeralda`, texto `--on-esmeralda` (verde-escuro), nos dois
  temas — igual ao board.
- **Curvas, não caixas.** O elemento gráfico é a curva (anel do poço cortado):
  entra pelos cantos, sangrando para fora da página. Uma composição de curvas
  por tela, em `--profundo`/`--apoio` + `--esmeralda`.
- **Plano.** Sem sombra, sem gradiente, sem glow; cantos arredondados suaves
  (`--radius-md` 12px nos cards).
- **`--alerta` é raro** e sempre com palavra ou ícone.
- **Piso de contraste:** texto corrido ≥ 7:1 nos dois temas; acento de texto
  ≥ 4,5:1.

## Forma

| Token | Valor | Uso |
|---|---|---|
| `--radius-sm` | `6px` | inputs, código, tags |
| `--radius-md` | `12px` | cards, botões |
| `--radius-lg` | `24px` | painéis grandes, imagens |
| `--radius-pill` | `999px` | chips, avatares |
| `--rule` | `56px × 4px` | a barrinha esmeralda sob títulos de seção (como em "01 / ASCENSÃO") |

## Raw CSS — cores (copy-paste)

```css
:root {
  --ink: #F5F3ED;
  --surface: #FFFFFF;
  --surface-2: #E3DED2;
  --text: #102C26;
  --text-muted: #4F5E57;
  --verde: #0A6E48;
  --verde-glow: #085A3B;
  --esmeralda: #16C784;
  --on-esmeralda: #102C26;
  --profundo: #102C26;
  --apoio: #0D4939;
  --on-profundo: #F5F3ED;
  --alerta: #B3261E;
  --info: #1D5FA6;

  --radius-sm: 6px;
  --radius-md: 12px;
  --radius-lg: 24px;
  --radius-pill: 999px;
}

[data-theme="dark"] {
  --ink: #102C26;
  --surface: #173B33;
  --surface-2: #24503F;
  --text: #F5F3ED;
  --text-muted: #A9BDB3;
  --verde: #16C784;
  --verde-glow: #43D79B;
  --esmeralda: #16C784;
  --on-esmeralda: #102C26;
  --profundo: #0D4939;
  --apoio: #0D4939;
  --on-profundo: #F5F3ED;
  --alerta: #FF8A7A;
  --info: #8CBCF5;
}
```

## Tipografia

Abra `typography.html` para a referência visual. Uma família só —
**Montserrat** — que é a geometria do wordmark; IBM Plex Mono apenas para
código e métricas.

### Fontes

| Papel | Token | Família | Uso |
|---|---|---|---|
| Display | `--font-display` | Montserrat 800 | Títulos, sempre CAIXA ALTA nos níveis display/H1 |
| Body | `--font-body` | Montserrat 400–600 | Parágrafos, UI, títulos menores |
| Kicker | — | Montserrat 700, tracking 0,5em, CAIXA ALTA | linha de apoio estilo "H A C K A T H O N" |
| Mono | `--font-mono` | IBM Plex Mono 400–500 | código, métricas, saída de modelo |

Arquivos em `fonts/` (woff2, subset latino). Ou via Google Fonts:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

### Escala — nível de página

| Token | Tamanho | Uso |
|---|---|---|
| `--text-display` | `clamp(2.75rem, 6vw, 5rem)` | Hero, capa — 800, CAIXA ALTA, leading 1.0 |
| `--text-h1` | `2.5rem` (40px) | Título de página — 800, CAIXA ALTA |
| `--text-h2` | `1.75rem` (28px) | Seção — 800, sentence case |
| `--text-h3` | `1.25rem` (20px) | Subseção, card — 700 |
| `--text-lead` | `1.125rem` (18px) | Intro |
| `--text-body` | `1rem` (16px) | Parágrafo padrão (leading 1.6) |
| `--text-small` | `0.8rem` (12.8px) | Legendas, eyebrows |

Tracking: `--tracking-display: -0.01em` (Montserrat pesada aperta um pouco) ·
`--tracking-kicker: 0.5em` (o "HACKATHON") · `--tracking-eyebrow: 0.08em`.

**Eyebrow de seção** (do board): `01 / ASCENSÃO` — número em `--verde`, barra
e rótulo em `--text`, Montserrat 800 em caixa alta, com a barrinha esmeralda
de 56×4px embaixo.

### Escala — dentro de artigos

| Nível | Tamanho |
|---|---|
| H1 | `1.75rem` |
| H2 | `1.4rem` |
| H3 | `1.2rem` |
| H4–H6 | `1.05rem` |

### Raw CSS — tipografia (copy-paste)

```css
:root {
  --font-display: 'Montserrat', system-ui, sans-serif;
  --font-body: 'Montserrat', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;

  --text-display: clamp(2.75rem, 6vw, 5rem);
  --text-h1: 2.5rem;
  --text-h2: 1.75rem;
  --text-h3: 1.25rem;
  --text-lead: 1.125rem;
  --text-body: 1rem;
  --text-small: 0.8rem;

  --tracking-display: -0.01em;
  --tracking-kicker: 0.5em;
  --tracking-eyebrow: 0.08em;
}
```

## Voz

PT-BR, meio descontraído, meio profissional. "A gente" falando com "você".
Piada leve no título ("Do fundo do poço ao protótipo"); o corpo é preciso —
números com unidade e baseline. Display em CAIXA ALTA; o resto em sentence
case. Sem emoji: a seta é o único ícone de marca.
