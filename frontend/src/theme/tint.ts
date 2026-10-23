import type { CssVarsTheme, Theme } from "@mui/material/styles";
import { useColorScheme, useTheme } from "@mui/material/styles";

export type Tone = "primary" | "secondary" | "error" | "warning" | "info" | "success";

/** Scheme-aware palette color (CSS variable), so light/dark switch without re-render. */
export function toneColor(theme: Theme, tone: Tone): string {
  return (theme.vars ?? theme).palette[tone].main;
}

/** Translucent version of a palette color — resolves per color scheme via color-mix(). */
export function tint(theme: Theme, tone: Tone, amount: number): string {
  return theme.alpha(toneColor(theme, tone), amount);
}

/**
 * Concrete (hex) palette of the active scheme. Needed where CSS variables can't be used:
 * <canvas> (force-graph) and chart libraries that write colors as SVG attributes.
 */
export function useResolvedPalette(): Theme["palette"] {
  const theme = useTheme();
  const { mode, systemMode } = useColorScheme();
  const resolved = (mode === "system" ? systemMode : mode) ?? "light";
  const schemes = (theme as unknown as Partial<CssVarsTheme>).colorSchemes;
  return (schemes?.[resolved]?.palette ?? theme.palette) as Theme["palette"];
}
