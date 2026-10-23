/* theme.ts — FakeNews-XAI design tokens: light + dark color schemes (MUI 9 CSS variables) */

import { createTheme } from "@mui/material/styles";

const FONT_SANS = '"Geist", system-ui, -apple-system, "Segoe UI", sans-serif';
export const FONT_MONO = '"Geist Mono", ui-monospace, "Cascadia Code", monospace';

const theme = createTheme({
  // CSS variables + class selector → the toggle switches schemes without re-rendering the tree
  cssVariables: { colorSchemeSelector: "class" },

  colorSchemes: {
    light: {
      palette: {
        primary: { main: "#2563EB", contrastText: "#FFFFFF" },
        secondary: { main: "#4F46E5" },
        error: { main: "#D92D20" },
        warning: { main: "#DC6803" },
        success: { main: "#079455" },
        info: { main: "#0E7090" },
        background: { default: "#F6F7F9", paper: "#FFFFFF" },
        text: { primary: "#101828", secondary: "#475467" },
        divider: "#E4E7EC",
      },
    },
    dark: {
      palette: {
        primary: { main: "#528BFF", contrastText: "#FFFFFF" },
        secondary: { main: "#8098F9" },
        error: { main: "#F97066" },
        warning: { main: "#F79009" },
        success: { main: "#47CD89" },
        info: { main: "#22CCEE" },
        background: { default: "#0C111D", paper: "#161B26" },
        text: { primary: "#F5F5F6", secondary: "#94969C" },
        divider: "#262D3D",
      },
    },
  },

  typography: {
    fontFamily: FONT_SANS,
    h4: { fontWeight: 600, letterSpacing: "-0.02em" },
    h5: { fontWeight: 600, letterSpacing: "-0.015em" },
    h6: { fontWeight: 600, fontSize: "1rem" },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
  },

  shape: { borderRadius: 10 },

  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { WebkitFontSmoothing: "antialiased" },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: ({ theme: t }) => ({
          backgroundImage: "none",
          boxShadow: "none",
          border: `1px solid ${t.vars.palette.divider}`,
          borderRadius: 14,
        }),
      },
    },
    MuiCard: {
      defaultProps: { elevation: 0 },
    },
    MuiAccordion: {
      styleOverrides: {
        root: { "&::before": { display: "none" } },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 8, minHeight: 40, paddingInline: 16 },
        sizeSmall: { minHeight: 32, paddingInline: 12 },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 999, fontWeight: 500 },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 500 },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { fontSize: 12, borderRadius: 8 },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 12 },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: ({ theme: t }) => ({
          borderRadius: 10,
          backgroundColor: t.vars.palette.background.paper,
        }),
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: ({ theme: t }) => ({
          borderRadius: 8,
          minHeight: 44,
          "&.Mui-selected": {
            backgroundColor: t.alpha(t.vars.palette.primary.main, 0.1),
            color: t.vars.palette.primary.main,
            "& .MuiListItemIcon-root": { color: t.vars.palette.primary.main },
          },
          "&.Mui-selected:hover": {
            backgroundColor: t.alpha(t.vars.palette.primary.main, 0.16),
          },
        }),
      },
    },
  },
});

export default theme;
