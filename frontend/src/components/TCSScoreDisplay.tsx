import React, { useEffect, useState } from "react";
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

// Returns an SVG arc path for a gauge from fromScore to toScore (both in [0,1]).
// Center (100,100), radius 90. Score 0 = left (10,100), score 1 = right (190,100).
// Arc traces the top semicircle (sweep counterclockwise in SVG y-down = through top).
function describeArc(fromScore: number, toScore: number): string {
  if (Math.abs(toScore - fromScore) < 0.001) return "";
  const cx = 100;
  const cy = 100;
  const r = 90;
  const fromAngle = Math.PI * (1 - fromScore);
  const toAngle = Math.PI * (1 - toScore);
  const x1 = cx + r * Math.cos(fromAngle);
  const y1 = cy - r * Math.sin(fromAngle);
  const x2 = cx + r * Math.cos(toAngle);
  const y2 = cy - r * Math.sin(toAngle);
  const largeArc = toScore - fromScore > 0.5 ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${largeArc} 0 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

function scoreToPoint(score: number): { x: number; y: number } {
  const angle = Math.PI * (1 - score);
  return {
    x: 100 + 90 * Math.cos(angle),
    y: 100 - 90 * Math.sin(angle),
  };
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
  const [animatedScore, setAnimatedScore] = useState<number>(0);

  useEffect(() => {
    let animFrame: number;
    const duration = 900;
    const startTime = performance.now();

    const step = (now: number): void => {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setAnimatedScore(eased * score);
      if (t < 1) {
        animFrame = requestAnimationFrame(step);
      }
    };

    setAnimatedScore(0);
    animFrame = requestAnimationFrame(step);
    return (): void => {
      cancelAnimationFrame(animFrame);
    };
  }, [score]);

  const color = getScoreColor(score);
  const dot = scoreToPoint(animatedScore);
  const bgPath = describeArc(0, 1);
  const fillPath = describeArc(0, animatedScore);

  return (
    <Paper elevation={2} sx={{ p: 3, textAlign: "center" }}>
      <Box sx={{ display: "flex", justifyContent: "center" }}>
        <svg
          viewBox="0 0 200 110"
          style={{ width: "100%", maxWidth: 350 }}
          aria-hidden="true"
        >
          <path
            d={bgPath}
            fill="none"
            stroke="#334155"
            strokeWidth={12}
            strokeLinecap="round"
          />
          {fillPath && (
            <path
              d={fillPath}
              fill="none"
              stroke={color}
              strokeWidth={12}
              strokeLinecap="round"
            />
          )}
          <circle
            cx={dot.x}
            cy={dot.y}
            r={7}
            fill={color}
            stroke="#0f172a"
            strokeWidth={2}
          />
        </svg>
      </Box>

      <Typography
        variant="h2"
        sx={{ fontFamily: "IBM Plex Mono, monospace", fontWeight: "bold", mt: 1 }}
      >
        {score.toFixed(3)}
      </Typography>

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
        <Chip label={`Coherence Factor: ${coherenceFactor.toFixed(2)}`} size="small" />
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
