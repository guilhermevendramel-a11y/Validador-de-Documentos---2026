import "./globals.css";

export const metadata = {
  title: "MSE Engenharia - Validador Gestao Documental",
  description: "Validador local de gestao documental com Next.js",
};

export default function RootLayout({ children }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
