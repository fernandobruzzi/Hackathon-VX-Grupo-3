# Template de deck — Do Fundo do Poço ("Ascensão")

Copie esta pasta para cada apresentação nova e edite o `index.html`.

## Editar

1. No `<body>`: `data-event` (nome do hackathon) e `data-topic` (nome da solução) — vão para o rodapé.
2. Capa (slide 1): desafio, nome da solução, frase, nomes do time, data.
3. Cada slide: `<section class="slide" data-min="0.5" data-title="…" data-notes="…">`.
   `class="divider"` cria um divisor escuro com as curvas e a seta subindo.
4. Eyebrow: `<p class="eb"><b>01</b> / Rótulo</p>` (a barrinha esmeralda vem sozinha).
5. Logo: `<div data-logo="h"></div>` (horizontal) ou `data-logo="v"` (vertical).
   O engine põe a versão clara ou escura conforme o tema.
6. Demos: registre `hooks[idx('#canvas')] = {enter, leave, redraw, keyframes}`.
   `keyframes` são os estados que viram páginas no PDF (`apply`, `label`, `wait`).
   Use a RNG com semente (`mulberry32`) para tudo que for aleatório.
7. Confira números da demo fora do navegador (ex.: `python3 demo_check.py`).

Fontes (Montserrat, IBM Plex Mono) e logos já estão embutidos no `index.html`;
`fonts/` e `assets/logo/` ficam como originais.

## Rodar local

```bash
python3 -m http.server 8000   # abrir http://localhost:8000
```

## PDF

Tecla `P` (ou botão PDF) → "Salvar como PDF" no Chrome/Edge (respeitam o tamanho 1280×720; o Safari pode ignorar).
Sai sempre no tema claro, uma página por slide e uma por keyframe de demo.

## Deploy (Vercel)

```bash
npm i -g vercel
vercel login
vercel --prod                        # dentro desta pasta
vercel domains add <slug>.cerne.pro  # opcional; CNAME para cname.vercel-dns.com se o DNS não estiver no Vercel
```

Refaça `vercel --prod` depois de cada mudança.
