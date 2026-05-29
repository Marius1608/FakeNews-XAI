import React from "react";
import { Box, Chip, Paper, Typography } from "@mui/material";
import { getModelLabel } from "../utils/modelLabels";

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

function getScoreColor(score: number): string {
  if (score < 0.2) return "#ef4444";
  if (score < 0.5) return "#f97316";
  if (score < 0.8) return "#eab308";
  return "#22c55e";
}

function formatPipeline(pipeline: string, model?: string): string {
  if (model) return getModelLabel(model);
  if (pipeline === "spacy") return "SpaCy";
  if (pipeline === "llm") return "LLM";
  return pipeline;
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
  const color = getScoreColor(score);

  return (
    <Paper elevation={2} sx={{ p: 3, textAlign: "center" }}>
      <Typography
        variant="h2"
        sx={{ fontFamily: "IBM Plex Mono, monospace", fontWeight: "bold", mt: 1 }}
      >
        {score.toFixed(3)}
      </Typography>

      <Box sx={{
        width: 80,
        height: 6,
        borderRadius: 3,
        backgroundColor: color,
        mx: "auto",
        mt: 1,
        opacity: 0.85,
      }} />

      <Typography variant="h6" sx={{ color, mb: 2 }}>
        {label}
      </Typography>

      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 1,
          justifyContent: "center",
          mb: 2,
        }}
      >
        <Chip label={`${nClaims} claims`} size="small" />
        <Chip label={`${nInconsistencies} inconsistencies`} size="small" />
        <Chip label={`Coh. ${coherenceFactor.toFixed(2)}`} size="small" />
        <Chip label={formatPipeline(pipeline, model)} size="small" />
        <Chip label={`${Math.round(processingTimeMs)}ms`} size="small" />
      </Box>

      <Typography variant="body2" sx={{ fontStyle: "italic", mt: 2 }}>
        {summary}
      </Typography>
    </Paper>
  );
}

export default TCSScoreDisplay;
