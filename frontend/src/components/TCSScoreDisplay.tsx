import React from "react";
import { Box, Chip, Paper, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { tint, toneColor } from "../theme/tint";
import { getModelLabel } from "../utils/modelLabels";
import { FONT_MONO } from "../theme/theme";

interface TCSScoreDisplayProps {
  score: number;
  label: string;
  summary: string;
  nClaims: number;
  nInconsistencies: number;
  coherenceFactor: number;
  pipeline: string;
  model?: string;
  processingTimeMs: number;
}

type Tone = "error" | "warning" | "info" | "success";

// Same thresholds as the backend defaults (tcs_suspicious / tcs_moderate / tcs_very_consistent)
function getTone(score: number): Tone {
  if (score < 0.2) return "error";
  if (score < 0.5) return "warning";
  if (score < 0.8) return "info";
  return "success";
}

function formatPipeline(pipeline: string, model?: string): string {
  if (model) return getModelLabel(model);
  if (pipeline === "spacy") return "spaCy";
  if (pipeline === "llm") return "LLM";
  return pipeline;
}

function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

// Semicircle gauge: arc length of r=80 half circle ≈ 251.3
const ARC = "M 20 100 A 80 80 0 0 1 180 100";
const ARC_LEN = Math.PI * 80;

function Metric({ label, value, tone }: { label: string; value: string; tone?: Tone }): React.ReactElement {
  return (
    <Box sx={{ p: 1.5, borderRadius: "10px", bgcolor: "action.hover", display: "flex", flexDirection: "column", gap: 0.25, minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography sx={{ fontFamily: FONT_MONO, fontWeight: 600, fontSize: 20, color: tone ? `${tone}.main` : "text.primary" }} noWrap>
        {value}
      </Typography>
    </Box>
  );
}

function TCSScoreDisplay({
  score,
  label,
  summary,
  nClaims,
  nInconsistencies,
  coherenceFactor,
  pipeline,
  model,
  processingTimeMs,
}: TCSScoreDisplayProps): React.ReactElement {
  const theme = useTheme();
  const tone = getTone(score);
  const clamped = Math.max(0, Math.min(1, score));

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 }, display: "flex", flexDirection: "column", alignItems: "center", gap: 1.5 }}>
      <Box sx={{ alignSelf: "stretch", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 1 }}>
        <Typography variant="h6" component="h2">
          Verdict
        </Typography>
        <Chip size="small" label={formatPipeline(pipeline, model)} color="primary" variant="outlined" />
      </Box>

      <Box sx={{ position: "relative", width: 220, height: 128 }}>
        <svg width="220" height="128" viewBox="0 0 200 116" role="img" aria-label={`TCS score ${score.toFixed(3)} out of 1`}>
          <path d={ARC} fill="none" strokeWidth="14" strokeLinecap="round" style={{ stroke: (theme.vars ?? theme).palette.divider }} />
          <path
            d={ARC}
            fill="none"
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={`${clamped * ARC_LEN} ${ARC_LEN}`}
            style={{ stroke: toneColor(theme, tone), transition: "stroke-dasharray 600ms ease" }}
          />
        </svg>
        <Typography
          sx={{ position: "absolute", left: 0, right: 0, bottom: 4, textAlign: "center", fontFamily: FONT_MONO, fontWeight: 600, fontSize: 36, letterSpacing: "-0.03em" }}
        >
          {score.toFixed(3)}
        </Typography>
      </Box>

      <Box
        sx={{
          px: 1.5,
          py: 0.5,
          borderRadius: "999px",
          fontWeight: 600,
          fontSize: 13,
          color: `${tone}.main`,
          bgcolor: tint(theme, tone, 0.12),
        }}
      >
        {label}
      </Box>

      {summary && (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", lineHeight: 1.6 }}>
          {summary}
        </Typography>
      )}

      <Box sx={{ alignSelf: "stretch", display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 1.25, mt: 0.5 }}>
        <Metric label="Claims" value={String(nClaims)} />
        <Metric label="Inconsistencies" value={String(nInconsistencies)} tone={nInconsistencies > 0 ? "error" : undefined} />
        <Metric label="Coherence factor" value={coherenceFactor.toFixed(2)} />
        <Metric label="Processing" value={formatDuration(processingTimeMs)} />
      </Box>
    </Paper>
  );
}

export default TCSScoreDisplay;
