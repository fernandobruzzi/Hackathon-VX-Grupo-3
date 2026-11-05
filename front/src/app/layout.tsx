import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

const montserrat = localFont({
  variable: "--font-montserrat",
  src: [
    { path: "../fonts/Montserrat-Regular.woff2", weight: "400" },
    { path: "../fonts/Montserrat-Medium.woff2", weight: "500" },
    { path: "../fonts/Montserrat-SemiBold.woff2", weight: "600" },
    { path: "../fonts/Montserrat-Bold.woff2", weight: "700" },
    { path: "../fonts/Montserrat-ExtraBold.woff2", weight: "800" },
  ],
});
const plexMono = localFont({
  variable: "--font-plex-mono",
  src: [
    { path: "../fonts/IBMPlexMono-Regular.woff2", weight: "400" },
    { path: "../fonts/IBMPlexMono-Medium.woff2", weight: "500" },
  ],
});

export const metadata: Metadata = {
  title: "Cadastro de Materiais — Do Fundo do Poço",
  description: "Saneamento, cadastro e enriquecimento de materiais com IA",
  icons: { icon: "/11_avatar.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="pt-BR"
      data-theme="light"
      className={`${montserrat.variable} ${plexMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-dvh bg-ink text-text">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
