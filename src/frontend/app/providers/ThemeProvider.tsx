import React from "react";
import { ThemeProvider as NextThemeProvider } from "next-themes";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemeProvider
      attribute="data-theme"
      defaultTheme="dark"
      enableSystem
      disableTransitionOnChange
      themes={["dark", "light"]}
      storageKey="stokai-theme"
    >
      {children}
    </NextThemeProvider>
  );
}
