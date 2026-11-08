import { useRef, useState } from "react";
import { cn } from "@/lib/format";
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

/* ---------- Button ---------- */
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";
const btnVariant: Record<ButtonVariant, string> = {
  primary: "bg-esmeralda text-on-esmeralda hover:brightness-105",
  secondary: "bg-profundo text-on-profundo hover:brightness-110",
  ghost: "text-verde ring-2 ring-inset ring-surface-2 hover:bg-surface",
  danger: "text-alerta ring-2 ring-inset ring-surface-2 hover:bg-surface",
};
const btnSize: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-11 px-5 text-[15px]",
  lg: "h-13 px-7 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...p
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return (
    <button
      {...p}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md font-bold whitespace-nowrap transition disabled:cursor-not-allowed disabled:opacity-45",
        btnVariant[variant],
        btnSize[size],
        className,
      )}
    />
  );
}

/* ---------- Badge ---------- */
export type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "info";
const toneCls: Record<Tone, string> = {
  neutral: "bg-surface text-text ring-1 ring-inset ring-surface-2",
  brand: "bg-profundo text-on-profundo",
  success: "bg-surface text-verde ring-1 ring-inset ring-surface-2",
  warning: "bg-surface text-aviso ring-1 ring-inset ring-surface-2",
  danger: "bg-surface text-alerta ring-1 ring-inset ring-surface-2",
  info: "bg-surface text-info ring-1 ring-inset ring-surface-2",
};
const dotCls: Record<Tone, string> = {
  neutral: "bg-muted",
  brand: "bg-esmeralda",
  success: "bg-serie-1",
  warning: "bg-aviso",
  danger: "bg-alerta",
  info: "bg-info",
};
export function Badge({
  tone = "neutral",
  dot = true,
  children,
  className,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold tracking-[0.08em] whitespace-nowrap uppercase",
        toneCls[tone],
        className,
      )}
    >
      {dot && <span className={cn("size-1.5 rounded-full", dotCls[tone])} />}
      {children}
    </span>
  );
}

/* ---------- Card ---------- */
export function Card({
  tone = "default",
  className,
  ...p
}: HTMLAttributes<HTMLDivElement> & { tone?: "default" | "block" }) {
  return (
    <div
      {...p}
      className={cn(
        "rounded-md p-6",
        tone === "block" ? "bg-profundo text-on-profundo" : "bg-surface",
        className,
      )}
    />
  );
}

/* ---------- Eyebrow: "01 / RÓTULO" + barra esmeralda ---------- */
export function Eyebrow({
  n,
  children,
  rule = true,
  className,
}: {
  n?: string;
  children: ReactNode;
  rule?: boolean;
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="text-[13px] font-extrabold tracking-[0.02em] uppercase">
        {n && <span className="text-verde">{n} </span>}
        {n && "/ "}
        {children}
      </p>
      {rule && <span className="mt-2 block h-1 w-14 bg-esmeralda" />}
    </div>
  );
}

/* ---------- PageHeader ---------- */
export function PageHeader({
  n,
  eyebrow,
  title,
  description,
  actions,
}: {
  n?: string;
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <Eyebrow n={n}>{eyebrow}</Eyebrow>
        <h1 className="mt-4 text-[28px] leading-tight font-extrabold tracking-[-0.01em]">
          {title}
        </h1>
        {description && <p className="mt-2 text-[15px] leading-6 text-muted">{description}</p>}
      </div>
      {actions && <div className="flex gap-3">{actions}</div>}
    </header>
  );
}

/* ---------- Form ---------- */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-semibold">{label}</span>
      {children}
      {(error || hint) && (
        <span className={cn("text-xs font-medium", error ? "text-alerta" : "text-muted")}>
          {error ?? hint}
        </span>
      )}
    </label>
  );
}
const inputCls =
  "rounded-sm bg-surface px-3 text-base ring-[1.5px] ring-inset ring-muted placeholder:text-muted hover:ring-2 hover:ring-text focus-visible:ring-2 focus-visible:ring-verde";
const width = (c?: string) => (c && /(^|\s)w-/.test(c) ? "" : "w-full");
export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) => (
  <input {...p} className={cn(inputCls, "h-11", width(className), className)} />
);
export const Textarea = ({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...p} className={cn(inputCls, "py-2.5", width(className), className)} />
);
export const Select = ({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select {...p} className={cn(inputCls, "h-11", width(className), className)} />
);

/* ---------- Tabs (controlado) ---------- */
export function Tabs<T extends string>({
  value,
  onChange,
  items,
  id,
  label,
}: {
  id: string;
  label: string;
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: string; count?: number }[];
}) {
  const buttons = useRef(new Map<T, HTMLButtonElement>());
  const [focused, setFocused] = useState<T | null>(null);
  return (
    <div
      role="tablist"
      aria-label={label}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setFocused(null);
      }}
      className="inline-flex gap-1 rounded-md bg-surface p-1 ring-1 ring-surface-2 ring-inset"
    >
      {items.map((it) => (
        <button
          key={it.value}
          type="button"
          role="tab"
          id={`${id}-tab-${it.value}`}
          aria-controls={`${id}-panel-${it.value}`}
          tabIndex={(focused ?? value) === it.value ? 0 : -1}
          ref={(element) => {
            if (element) buttons.current.set(it.value, element);
            else buttons.current.delete(it.value);
          }}
          onFocus={() => setFocused(it.value)}
          onKeyDown={(event) => {
            const index = items.findIndex((item) => item.value === it.value);
            const next =
              event.key === "ArrowRight"
                ? (index + 1) % items.length
                : event.key === "ArrowLeft"
                  ? (index - 1 + items.length) % items.length
                  : event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? items.length - 1
                      : null;
            if (next === null) return;
            event.preventDefault();
            setFocused(items[next].value);
            buttons.current.get(items[next].value)?.focus();
          }}
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            "flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold",
            value === it.value ? "bg-esmeralda text-on-esmeralda" : "text-text hover:bg-ink",
          )}
        >
          {it.label}
          {it.count !== undefined && <span className="font-mono text-xs">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Mantém os IDs de todos os painéis sem montar conteúdo inativo. */
export function TabPanels({
  id,
  values,
  active,
  enabled = true,
  children,
}: {
  id: string;
  values: string[];
  active: string;
  enabled?: boolean;
  children: ReactNode;
}) {
  if (!enabled) return <>{children}</>;
  return (
    <>
      {values.map((value) => (
        <div
          key={value}
          role="tabpanel"
          id={`${id}-panel-${value}`}
          aria-labelledby={`${id}-tab-${value}`}
          hidden={value !== active}
          tabIndex={0}
        >
          {value === active ? children : null}
        </div>
      ))}
    </>
  );
}

/* ---------- Table ---------- */
export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("overflow-x-auto rounded-md bg-surface", className)}>
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}
export const Th = ({ children, className }: { children?: ReactNode; className?: string }) => (
  <th
    className={cn(
      "border-b border-surface-2 px-4 py-3 text-xs font-bold tracking-[0.04em] text-muted uppercase",
      className,
    )}
  >
    {children}
  </th>
);
export const Td = ({
  children,
  className,
  colSpan,
}: {
  children?: ReactNode;
  className?: string;
  colSpan?: number;
}) => (
  <td colSpan={colSpan} className={cn("border-b border-surface-2 px-4 py-3 align-top", className)}>
    {children}
  </td>
);

/* ---------- KPI ---------- */
export function Kpi({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "block";
}) {
  return (
    <Card tone={tone} className="flex flex-col gap-2">
      <span
        className={cn(
          "text-xs font-extrabold tracking-[0.04em] uppercase",
          tone === "block" ? "text-esmeralda" : "text-verde",
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          "text-[34px] leading-none font-extrabold",
          tone === "block" ? "text-esmeralda" : "text-text",
        )}
      >
        {value}
      </span>
      {sub && (
        <span
          className={cn("font-mono text-xs", tone === "block" ? "text-on-profundo" : "text-muted")}
        >
          {sub}
        </span>
      )}
    </Card>
  );
}

/* ---------- Mono code ---------- */
export const Code = ({ children, className }: { children: ReactNode; className?: string }) => (
  <span className={cn("font-mono text-[13px] font-medium", className)}>{children}</span>
);

/* ---------- Empty / placeholder ---------- */
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-md border-2 border-dashed border-surface-2 p-8">
      <p className="text-lg font-bold">{title}</p>
      {children && <div className="max-w-xl text-sm leading-6 text-muted">{children}</div>}
      {action}
    </div>
  );
}

/* ---------- Arrow mark (09_seta do kit) ---------- */
export function Seta({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 220" aria-hidden="true" className={cn("fill-esmeralda", className)}>
      <path d="M100 15 185 100H130V205H70V100H15Z" />
    </svg>
  );
}
