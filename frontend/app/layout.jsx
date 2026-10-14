import "./globals.css";

export const metadata = {
  title: "FixFlow — Autonomous CI/CD Failure Localization & Code Repair",
  description: "FixFlow: Autonomous CI/CD failure localization, root cause analysis, and non-destructive code patches.",
  other: {
    "darkreader-lock": "true",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="darkreader-lock" content="darkreader-lock" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body suppressHydrationWarning className="antialiased bg-background text-foreground min-h-screen">
        {children}
      </body>
    </html>
  );
}
