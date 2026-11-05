# Template de slides — Google Slides

`do-fundo-do-poco-template.pptx` é o template editável na identidade "Ascensão",
para quando o time montar slides à mão em vez de usar a skill
`/do-fundo-do-poco-interactive-deck`.

## Importar no Google Slides

1. Abra o Google Drive e arraste `do-fundo-do-poco-template.pptx` para uma pasta.
2. Clique com o botão direito → **Abrir com → Apresentações Google**. O Drive
   cria uma cópia em Google Slides (o .pptx original continua lá; pode apagar).
3. Renomeie a cópia, por exemplo "Template — Do Fundo do Poço".
4. Para cada apresentação nova: **Arquivo → Fazer uma cópia** do template.

## O que vem dentro

- **Tema** com as cores da marca (verde-escuro `#102C26`, esmeralda `#16C784`,
  off-white `#F5F3ED`, apoio `#0D4939`) e Montserrat em tudo.
- **7 layouts** em **Slide → Aplicar layout** (ou na seta ao lado de "+"):
  `CAPA`, `DIVISOR`, `CONTEUDO`, `DUAS_COLUNAS`, `NUMERO`, `SO_TITULO`,
  `ENCERRAMENTO`. Logo, curvas, eyebrow com a barrinha esmeralda, rodapé e
  número de página já vêm no layout.
- **12 slides de exemplo** com a estrutura de pitch: capa, roteiro, divisor,
  problema em um número, solução, como funciona, demo (espaço para print ou
  vídeo), divisor, resultados, comparação, próximos passos, perguntas + time.
  Os números são de exemplo: troque pelos reais.

## Regras rápidas

- Eyebrow: `01 / RÓTULO` em caixa alta. Título: uma frase com a mensagem do slide.
- Esmeralda é forma (barras, setas, curvas, destaque em fundo escuro). Texto
  verde no fundo claro é o verde `#0A6E48`.
- Um bloco verde-escuro por slide, no máximo, para o que importa.
- Números em formato brasileiro e sempre com a referência ("94,7%, atual 81,0%").

## Regenerar

`gerar-template.js` é o script que gera o .pptx (pptxgenjs). Ele espera as
imagens do kit rasterizadas em `img/`; está aqui como referência.
