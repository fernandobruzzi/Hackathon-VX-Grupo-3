const pptxgen = require("pptxgenjs");
const path = require("path");
const { applyTheme } = require("/root/.claude/skills/synced/8675f805-0200-4f1c-a0bf-583cec9309c0_2b61da0f-ba79-4069-af43-df1dde656f35/pptx/scripts/apply_theme.js");

const D = __dirname;
const img = (f) => path.join(D, "img", f);

// Cores da marca (design/design-system/README.md, identidade "Ascensão")
const HEX = {
  escuro: "102C26", esmeralda: "16C784", offwhite: "F5F3ED", apoio: "0D4939",
  branco: "FFFFFF", verde: "0A6E48", muted: "4F5E57", linha: "E3DED2",
  alerta: "B3261E", info: "1D5FA6", mutedDark: "A9BDB3",
};
const THEME = {
  name: "Do Fundo do Poço — Ascensão",
  headFontFace: "Montserrat",
  bodyFontFace: "Montserrat",
  colors: {
    dk1: HEX.escuro, lt1: HEX.offwhite, dk2: HEX.apoio, lt2: HEX.branco,
    accent1: HEX.esmeralda, accent2: HEX.verde, accent3: HEX.apoio,
    accent4: HEX.info, accent5: HEX.alerta, accent6: HEX.muted,
    hlink: HEX.verde, folHlink: "085A3B",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.title = "Template de slides — Do Fundo do Poço";
pres.author = "Do Fundo do Poço";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const W = 10, H = 5.625, M = 0.5;

// ---------- peças comuns dos layouts ----------
const footer = (dark) => ([
  { text: { text: "DO FUNDO DO POÇO", options: { x: M, y: 5.2, w: 3, h: 0.25, fontSize: 9, bold: true, color: dark ? C.background1 : C.text1, margin: 0, charSpacing: 1 } } },
]);
const slideNum = (dark) => ({ x: W - M - 0.6, y: 5.2, w: 0.6, h: 0.25, fontSize: 9, color: dark ? HEX.mutedDark : HEX.muted, align: "right", margin: 0 });
// Eyebrow "01 / RÓTULO" + barrinha esmeralda 56×4px (≈0.58 x 0.04 in), como no board
const eyebrowPh = (y) => ({ placeholder: { options: { name: "eyebrow", type: "body", align: "left", x: M, y, w: 6, h: 0.3, fontSize: 11, bold: true, color: C.text1, margin: 0, valign: "top" }, text: "01 / RÓTULO DA SEÇÃO" } });
const eyebrowRule = (y) => ({ rect: { x: M, y: y + 0.34, w: 0.58, h: 0.04, fill: { color: C.accent1 }, line: { type: "none" } } });

// Capa
pres.defineSlideMaster({
  title: "CAPA",
  background: { color: HEX.offwhite },
  objects: [
    { image: { path: img("curvas_capa_s.png"), x: W - 5.42, y: 0, w: 5.42, h: H } },
    { image: { path: img("logo_h_s.png"), x: M - 0.12, y: 0.4, w: 3.0, h: 0.97 } },
    eyebrowPh(1.75), eyebrowRule(1.75),
    { placeholder: { options: { name: "title", type: "title", align: "left", x: M, y: 2.3, w: 4.6, h: 1.5, fontSize: 40, bold: true, color: C.text1, valign: "bottom", margin: 0, lineSpacingMultiple: 0.95 }, text: "NOME DA SOLUÇÃO" } },
    { placeholder: { options: { name: "subtitle", type: "body", align: "left", x: M, y: 3.9, w: 4.4, h: 0.5, fontSize: 14, color: HEX.muted, margin: 0, valign: "top" }, text: "Uma frase dizendo o que a solução faz e para quem." } },
    { placeholder: { options: { name: "meta", type: "body", align: "left", x: M, y: 4.55, w: 4.4, h: 0.55, fontSize: 10, color: C.text1, margin: 0, valign: "top" }, text: "Pessoa 1 · Pessoa 2 · Pessoa 3 · Pessoa 4\nNome do Hackathon · data" } },
  ],
});

// Divisor de seção (escuro)
pres.defineSlideMaster({
  title: "DIVISOR",
  background: { color: HEX.escuro },
  objects: [
    { image: { path: img("curvas_div_s.png"), x: 4.0, y: H - 2.05, w: 6.0, h: 2.05 } },
    { placeholder: { options: { name: "numero", type: "body", align: "left", x: M, y: 2.35, w: 3, h: 0.35, fontSize: 12, bold: true, color: C.accent1, margin: 0 }, text: "01 / PARTE 1" } },
    { rect: { x: M, y: 2.72, w: 0.58, h: 0.04, fill: { color: C.accent1 }, line: { type: "none" } } },
    { placeholder: { options: { name: "title", type: "title", align: "left", x: M, y: 2.9, w: 6.5, h: 1.3, fontSize: 48, bold: true, color: C.background1, valign: "top", margin: 0, lineSpacingMultiple: 0.95 }, text: "NOME DA SEÇÃO" } },
  ],
});

// Conteúdo: título + corpo
pres.defineSlideMaster({
  title: "CONTEUDO",
  background: { color: HEX.offwhite },
  objects: [
    eyebrowPh(0.4), eyebrowRule(0.4),
    { placeholder: { options: { name: "title", type: "title", align: "left", x: M, y: 0.9, w: 9, h: 0.95, fontSize: 26, bold: true, color: C.text1, valign: "top", margin: 0 }, text: "Título do slide em uma frase" } },
    { placeholder: { options: { name: "body", type: "body", align: "left", x: M, y: 2.0, w: 9, h: 2.9, fontSize: 16, color: C.text1, valign: "top", margin: 0, paraSpaceAfter: 8 }, text: "Tópico curto" } },
    ...footer(false),
  ],
  slideNumber: slideNum(false),
});

// Duas colunas: texto à esquerda, bloco escuro à direita
pres.defineSlideMaster({
  title: "DUAS_COLUNAS",
  background: { color: HEX.offwhite },
  objects: [
    eyebrowPh(0.4), eyebrowRule(0.4),
    { placeholder: { options: { name: "title", type: "title", align: "left", x: M, y: 0.9, w: 9, h: 0.95, fontSize: 26, bold: true, color: C.text1, valign: "top", margin: 0 }, text: "Título do slide em uma frase" } },
    { placeholder: { options: { name: "body", type: "body", align: "left", x: M, y: 2.0, w: 4.3, h: 2.9, fontSize: 16, color: C.text1, valign: "top", margin: 0, paraSpaceAfter: 8 }, text: "Tópico curto" } },
    { rect: { x: 5.2, y: 2.0, w: 4.3, h: 2.9, fill: { color: C.text1 }, line: { type: "none" }, rectRadius: 0.12 } },
    { placeholder: { options: { name: "destaque", type: "body", align: "left", x: 5.45, y: 2.2, w: 3.8, h: 2.5, fontSize: 16, color: C.background1, valign: "top", margin: 0, paraSpaceAfter: 6 }, text: "Destaque: a ideia que importa" } },
    ...footer(false),
  ],
  slideNumber: slideNum(false),
});

// Número grande
pres.defineSlideMaster({
  title: "NUMERO",
  background: { color: HEX.offwhite },
  objects: [
    eyebrowPh(0.4), eyebrowRule(0.4),
    { placeholder: { options: { name: "numero", type: "body", align: "left", x: M, y: 1.35, w: 5.2, h: 1.9, fontSize: 96, bold: true, color: C.accent2, valign: "bottom", margin: 0 }, text: "3 DIAS" } },
    { placeholder: { options: { name: "legenda", type: "body", align: "left", x: M, y: 3.3, w: 5.0, h: 0.5, fontSize: 14, color: HEX.muted, valign: "top", margin: 0 }, text: "O que esse número mede" } },
    { placeholder: { options: { name: "body", type: "body", align: "left", x: 5.9, y: 1.6, w: 3.6, h: 2.4, fontSize: 15, color: C.text1, valign: "middle", margin: 0, paraSpaceAfter: 8 }, text: "Contexto do número" } },
    { placeholder: { options: { name: "fonte", type: "body", align: "left", x: M, y: 4.75, w: 9, h: 0.3, fontSize: 9, color: HEX.muted, valign: "top", margin: 0 }, text: "Fonte: de onde vem o número" } },
    ...footer(false),
  ],
  slideNumber: slideNum(false),
});

// Só título (para cards, tabelas, prints)
pres.defineSlideMaster({
  title: "SO_TITULO",
  background: { color: HEX.offwhite },
  objects: [
    eyebrowPh(0.4), eyebrowRule(0.4),
    { placeholder: { options: { name: "title", type: "title", align: "left", x: M, y: 0.9, w: 9, h: 0.95, fontSize: 26, bold: true, color: C.text1, valign: "top", margin: 0 }, text: "Título do slide em uma frase" } },
    ...footer(false),
  ],
  slideNumber: slideNum(false),
});

// Encerramento (escuro)
pres.defineSlideMaster({
  title: "ENCERRAMENTO",
  background: { color: HEX.escuro },
  objects: [
    { image: { path: img("logo_v_dark_s.png"), x: W - M - 2.0, y: 0.4, w: 2.0, h: 1.46 } },
    { placeholder: { options: { name: "title", type: "title", align: "left", x: M, y: 0.45, w: 6.5, h: 1.0, fontSize: 48, bold: true, color: C.background1, valign: "top", margin: 0 }, text: "PERGUNTAS?" } },
    { placeholder: { options: { name: "contatos", type: "body", align: "left", x: M, y: 4.55, w: 9, h: 0.5, fontSize: 11, color: HEX.mutedDark, valign: "top", margin: 0 }, text: "deck: link · código: github.com/time/repo" } },
  ],
});

// ---------- helpers de conteúdo ----------
const bullets = (items, opts = {}) => items.map((t, i) => ({ text: t, options: { bullet: { indent: 18 }, breakLine: i < items.length - 1, ...opts } }));
const card = (slide, x, y, w, h, dark, name) => slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: dark ? C.text1 : C.background2 }, line: { type: "none" }, objectName: name });
const cardText = (slide, x, y, w, h, runs, name) => slide.addText(runs, { x, y, w, h, margin: 0, valign: "top", isTextBox: true, objectName: name });

// ---------- slides de exemplo ----------
pres.addSection({ title: "Abertura" });
let s = pres.addSlide({ masterName: "CAPA", sectionTitle: "Abertura" });
s.addText("02 / MANUTENÇÃO PREDITIVA", { placeholder: "eyebrow" });
s.addText("NOME DA SOLUÇÃO", { placeholder: "title" });
s.addText("Uma frase dizendo o que a solução faz e para quem.", { placeholder: "subtitle" });
s.addText([{ text: "Pessoa 1 · Pessoa 2 · Pessoa 3 · Pessoa 4", options: { bold: true, breakLine: true } }, { text: "Nome do Hackathon 2026 · 08/11/2026" }], { placeholder: "meta" });
s.addNotes("Abrir com o problema em uma frase, não com o nome do time.");

s = pres.addSlide({ masterName: "SO_TITULO", sectionTitle: "Abertura" });
s.addText("00 / ROTEIRO", { placeholder: "eyebrow" });
s.addText("Do fundo do poço até a solução, em 6 minutos", { placeholder: "title" });
[["01", "O problema", "Quem sofre e quanto custa."], ["02", "A solução", "O que construímos e como funciona."], ["03", "Demo ao vivo", "O modelo rodando em dados simulados."], ["04", "Resultados", "Métricas contra o método atual."]].forEach(([n, t, d], i) => {
  const x = M + i * 2.31, dark = i === 2;
  card(s, x, 2.0, 2.13, 2.2, dark, `roteiro_card_${i + 1}`);
  cardText(s, x + 0.2, 2.2, 1.75, 1.85, [
    { text: n, options: { fontSize: 12, bold: true, color: dark ? C.accent1 : C.accent2, breakLine: true } },
    { text: t, options: { fontSize: 15, bold: true, color: dark ? C.background1 : C.text1, breakLine: true, paraSpaceBefore: 6 } },
    { text: d, options: { fontSize: 12, color: dark ? C.background1 : C.text1, paraSpaceBefore: 6 } },
  ], `roteiro_txt_${i + 1}`);
});
s.addNotes("Não ler a lista. Dizer só: problema, solução, demo, resultados.");

pres.addSection({ title: "O problema" });
s = pres.addSlide({ masterName: "DIVISOR", sectionTitle: "O problema" });
s.addText("01 / PARTE 1", { placeholder: "numero" });
s.addText("O PROBLEMA", { placeholder: "title" });

s = pres.addSlide({ masterName: "NUMERO", sectionTitle: "O problema" });
s.addText("01 / O PROBLEMA", { placeholder: "eyebrow" });
s.addText("3 DIAS", { placeholder: "numero" });
s.addText("de produção parada por mês, por linha", { placeholder: "legenda" });
s.addText(bullets(["Motores falham sem aviso.", "A inspeção é manual, a cada 30 dias.", "Cada parada não planejada custa R$ 120 mil."]), { placeholder: "body" });
s.addText("Fonte: substituir pela fonte real (relatório do desafio, artigo, entrevista).", { placeholder: "fonte" });
s.addNotes("Falar o número devagar e dizer de onde ele vem.");

pres.addSection({ title: "A solução" });
s = pres.addSlide({ masterName: "DUAS_COLUNAS", sectionTitle: "A solução" });
s.addText("02 / A SOLUÇÃO", { placeholder: "eyebrow" });
s.addText("Avisar a falha antes de ela parar a linha", { placeholder: "title" });
s.addText(bullets(["Lê vibração e temperatura dos sensores que já existem.", "Um modelo marca o que foge do normal.", "A manutenção recebe o alerta com horas de antecedência."]), { placeholder: "body" });
s.addText([
  { text: "O DIFERENCIAL", options: { fontSize: 11, bold: true, color: C.accent1, breakLine: true } },
  { text: "Sem sensor novo e sem dados rotulados: o modelo aprende o \"normal\" de cada motor.", options: { fontSize: 16, bold: true, color: C.background1, paraSpaceBefore: 8 } },
], { placeholder: "destaque" });

s = pres.addSlide({ masterName: "SO_TITULO", sectionTitle: "A solução" });
s.addText("02 / COMO FUNCIONA", { placeholder: "eyebrow" });
s.addText("Quatro etapas, do sensor ao alerta", { placeholder: "title" });
[["1 · COLETA", "Sensores", "Vibração e temperatura a cada 5 s."], ["2 · JANELA", "Média móvel", "O \"normal\" recente de cada motor."], ["3 · SCORE", "Desvio em σ", "Quanto o ponto foge do normal."], ["4 · ALERTA", "Limiar k", "Acima de k·σ, a manutenção é avisada."]].forEach(([k, t, d], i) => {
  const x = M + i * 2.31, on = i === 2;
  card(s, x, 2.05, 1.95, 2.0, on, `etapa_card_${i + 1}`);
  cardText(s, x + 0.18, 2.25, 1.6, 1.65, [
    { text: k, options: { fontSize: 10, bold: true, color: on ? C.accent1 : C.accent2, breakLine: true } },
    { text: t, options: { fontSize: 15, bold: true, color: on ? C.background1 : C.text1, breakLine: true, paraSpaceBefore: 6 } },
    { text: d, options: { fontSize: 12, color: on ? C.background1 : C.text1, paraSpaceBefore: 6 } },
  ], `etapa_txt_${i + 1}`);
  if (i < 3) s.addImage({ path: img("seta_s.png"), x: x + 2.03, y: 2.92, w: 0.2, h: 0.22, rotate: 90, objectName: `etapa_seta_${i + 1}` });
});
s.addText([{ text: "O limiar k é a decisão de negócio: ", options: { color: C.text1 } }, { text: "alarme demais cansa, alarme de menos deixa passar.", options: { color: C.text1, bold: true } }], { x: M, y: 4.35, w: 9, h: 0.5, fontSize: 14, margin: 0, isTextBox: true, objectName: "etapas_nota" });

s = pres.addSlide({ masterName: "SO_TITULO", sectionTitle: "A solução" });
s.addText("03 / DEMO", { placeholder: "eyebrow" });
s.addText("O modelo rodando: limiar de alerta em ação", { placeholder: "title" });
card(s, M, 2.0, 6.2, 2.95, false, "demo_area");
s.addText("Cole aqui o print ou o vídeo da demo", { x: M, y: 2.0, w: 6.2, h: 2.95, fontSize: 14, color: HEX.muted, align: "center", valign: "middle", isTextBox: true, objectName: "demo_area_txt" });
card(s, 6.95, 2.0, 2.55, 2.95, true, "demo_resultado");
cardText(s, 7.15, 2.2, 2.15, 2.6, [
  { text: "SIMULAÇÃO", options: { fontSize: 10, bold: true, color: C.accent1, breakLine: true } },
  { text: "100%", options: { fontSize: 40, bold: true, color: C.accent1, breakLine: true, paraSpaceBefore: 6 } },
  { text: "recall com k = 3σ", options: { fontSize: 12, color: C.background1, breakLine: true } },
  { text: "8 acertos · 0 falsos alarmes", options: { fontSize: 12, color: C.background1, paraSpaceBefore: 10 } },
], "demo_resultado_txt");
s.addNotes("Dizer o que vai acontecer antes de clicar. Se a demo ao vivo falhar, este slide é o plano B com o print.");

pres.addSection({ title: "Resultados" });
s = pres.addSlide({ masterName: "DIVISOR", sectionTitle: "Resultados" });
s.addText("04 / PARTE 2", { placeholder: "numero" });
s.addText("RESULTADOS", { placeholder: "title" });

s = pres.addSlide({ masterName: "SO_TITULO", sectionTitle: "Resultados" });
s.addText("04 / RESULTADOS", { placeholder: "eyebrow" });
s.addText("Melhor que o método atual nas três métricas", { placeholder: "title" });
[["RECALL", "94,7%", 0.947, 0.81, "atual 81,0%"], ["ANTECEDÊNCIA MÉDIA", "6,2 h", 0.62, 0.0, "atual 0 h (falha já ocorrida)"], ["FALSOS ALARMES / SEMANA", "1,3", 0.13, 0.40, "atual 4,0"]].forEach(([k, v, ours, base, lg], i) => {
  const x = M + i * 3.07, w = 2.86, dark = i === 1;
  card(s, x, 2.0, w, 2.45, dark, `metrica_card_${i + 1}`);
  cardText(s, x + 0.22, 2.2, w - 0.44, 1.2, [
    { text: k, options: { fontSize: 10, bold: true, color: dark ? C.accent1 : C.accent2, breakLine: true } },
    { text: v, options: { fontSize: 36, bold: true, color: dark ? C.accent1 : C.accent2, paraSpaceBefore: 4 } },
  ], `metrica_txt_${i + 1}`);
  const bx = x + 0.22, bw = w - 0.44, by = 3.55;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: bx, y: by, w: bw, h: 0.1, rectRadius: 0.05, fill: { color: dark ? HEX.apoio : HEX.linha }, line: { type: "none" }, objectName: `metrica_trilho_${i + 1}` });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: bx, y: by, w: Math.max(0.1, bw * ours), h: 0.1, rectRadius: 0.05, fill: { color: C.accent1 }, line: { type: "none" }, objectName: `metrica_barra_${i + 1}` });
  s.addShape(pres.shapes.RECTANGLE, { x: bx + bw * base - 0.015, y: by - 0.06, w: 0.03, h: 0.22, fill: { color: dark ? C.background1 : C.text1 }, line: { type: "none" }, objectName: `metrica_base_${i + 1}` });
  s.addText(lg, { x: bx, y: 3.8, w: bw, h: 0.3, fontSize: 11, color: dark ? HEX.mutedDark : HEX.muted, margin: 0, isTextBox: true, objectName: `metrica_legenda_${i + 1}` });
});
s.addText("Barra = nossa solução · traço = método atual. Valores de exemplo: trocar pelos resultados reais.", { x: M, y: 4.6, w: 9, h: 0.3, fontSize: 10, color: HEX.muted, margin: 0, isTextBox: true, objectName: "metricas_fonte" });

s = pres.addSlide({ masterName: "SO_TITULO", sectionTitle: "Resultados" });
s.addText("04 / POR QUE ESSA ABORDAGEM", { placeholder: "eyebrow" });
s.addText("Sem histórico de falhas, a nossa abordagem é a única que avisa com antecedência", { placeholder: "title" });
const hdr = (t) => ({ text: t, options: { bold: true, color: C.text1, fontSize: 11 } });
const cel = (t, o = {}) => ({ text: t, options: { color: C.text1, fontSize: 13, ...o } });
const us = (t, o = {}) => ({ text: t, options: { color: C.text1, fontSize: 13, bold: true, fill: { color: "DDF4E9" }, ...o } });
s.addTable([
  [hdr("Abordagem"), hdr("Sensor novo?"), hdr("Dados rotulados?"), hdr("Antecedência"), hdr("Quando é melhor")],
  [cel("Inspeção manual", { bold: true }), cel("não"), cel("não"), cel("nenhuma", { color: C.accent5 }), cel("poucos motores")],
  [cel("Classificador supervisionado", { bold: true }), cel("não"), cel("sim, muitos", { color: C.accent5 }), cel("alta"), cel("histórico de falhas rotulado")],
  [us("Nossa solução"), us("não"), us("não"), us("horas", { color: C.accent2 }), us("sem histórico, muitos motores")],
], { x: M, y: 2.05, w: 9, colW: [2.15, 1.2, 1.5, 1.65, 2.5], rowH: 0.48, valign: "middle", border: { type: "solid", pt: 0.75, color: HEX.linha }, margin: [0, 0.1, 0, 0.1], objectName: "comparacao_tabela" });

pres.addSection({ title: "Fechamento" });
s = pres.addSlide({ masterName: "SO_TITULO", sectionTitle: "Fechamento" });
s.addText("05 / PRÓXIMOS PASSOS", { placeholder: "eyebrow" });
s.addText("Do protótipo ao chão de fábrica em seis meses", { placeholder: "title" });
[["30 DIAS", "Piloto", "Uma linha, 40 motores, dados reais."], ["90 DIAS", "Integração", "Alertas no sistema de manutenção existente."], ["6 MESES", "Escala", "Todas as linhas, limiar ajustado por motor."]].forEach(([p, t, d], i) => {
  const x = M + i * 3.07;
  card(s, x, 2.0, 2.86, 2.0, false, `passo_card_${i + 1}`);
  cardText(s, x + 0.22, 2.2, 2.42, 1.65, [
    { text: p, options: { fontSize: 11, bold: true, color: C.accent2, breakLine: true } },
    { text: t, options: { fontSize: 16, bold: true, color: C.text1, breakLine: true, paraSpaceBefore: 6 } },
    { text: d, options: { fontSize: 13, color: C.text1, paraSpaceBefore: 6 } },
  ], `passo_txt_${i + 1}`);
});

s = pres.addSlide({ masterName: "ENCERRAMENTO", sectionTitle: "Fechamento" });
s.addText("PERGUNTAS?", { placeholder: "title" });
[["Pessoa 1", "Modelo e dados"], ["Pessoa 2", "Back-end"], ["Pessoa 3", "Hardware"], ["Pessoa 4", "Pitch e produto"]].forEach(([n, r], i) => {
  const x = M + i * 2.31;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 3.25, w: 2.13, h: 1.05, rectRadius: 0.1, fill: { color: C.text2 }, line: { type: "none" }, objectName: `time_card_${i + 1}` });
  s.addText([
    { text: n, options: { fontSize: 15, bold: true, color: C.background1, breakLine: true } },
    { text: r, options: { fontSize: 11, color: HEX.mutedDark, breakLine: true } },
    { text: "email@exemplo.com", options: { fontSize: 10, color: C.accent1 } },
  ], { x: x + 0.18, y: 3.38, w: 1.8, h: 0.85, margin: 0, valign: "top", isTextBox: true, objectName: `time_txt_${i + 1}` });
});
s.addText("deck: link · código: github.com/time/repo", { placeholder: "contatos" });

(async () => {
  const out = path.join(D, "do-fundo-do-poco-template.pptx");
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("ok", out);
})();
