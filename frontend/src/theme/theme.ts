/* theme.ts — MUI dark mode theme for FakeNews-XAI */

import { createTheme } from "@mui/material/styles";

// palette
const theme = createTheme({
  palette: {
    mode: "dark",
    background: {
      default: "#0f172a",
      paper: "#1e293b",
    },
    primary: {
      main: "#60a5fa",
    },
    secondary: {
      main: "#a78bfa",
    },
    error: {
      main: "#f87171",
    },
    warning: {
      main: "#fbbf24",
    },
    success: {
      main: "#4ade80",
    },
  },

  // typography
  typography: {
    fontFamily: '"IBM Plex Sans", system-ui, sans-serif',
    fontFamilyMonospace: '"IBM Plex Mono", "Courier New", monospace',
  } as import("@mui/material/styles").TypographyVariantsOptions & {
    fontFamilyMonospace: string;
  },

  // shape
  shape: {
    borderRadius: 12,
  },

  // component overrides
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: "none",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid rgba(148, 163, 184, 0.1)",
          backgroundImage: "none",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
        },
      },
    },
  },
});

export default theme;
