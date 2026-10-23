import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider } from "@mui/material";
// Self-hosted fonts (no CDN). Latin + Latin Extended only — covers Romanian diacritics.
import "@fontsource/geist/latin-400.css";
import "@fontsource/geist/latin-ext-400.css";
import "@fontsource/geist/latin-500.css";
import "@fontsource/geist/latin-ext-500.css";
import "@fontsource/geist/latin-600.css";
import "@fontsource/geist/latin-ext-600.css";
import "@fontsource/geist-mono/latin-400.css";
import "@fontsource/geist-mono/latin-600.css";
import App from "./App";
import theme from "./theme/theme";

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement);

root.render(
  <React.StrictMode>
    {/* defaultMode="system" follows the OS until the user picks light/dark (stored in localStorage) */}
    <ThemeProvider theme={theme} defaultMode="system">
      <CssBaseline enableColorScheme />
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
