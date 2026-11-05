export const cn = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const int = new Intl.NumberFormat("pt-BR");

export const fmtBRL = (v: string | number | null) => (v === null ? "—" : brl.format(Number(v)));
export const fmtInt = (v: number | null) => (v === null ? "—" : int.format(v));
export const fmtPct = (v: number | null, d = 1) => (v === null ? "—" : `${(v * 100).toFixed(d).replace(".", ",")}%`);
export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
export const fmtNcm = (n: string | null) => n ?? "sem NCM";
