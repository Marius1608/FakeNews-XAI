import React from "react";
import { Box, Paper, Tooltip, Typography } from "@mui/material";
import type { FactAnnotationResponse } from "../types";

interface TextHighlightProps {
  text: string;
  annotations: FactAnnotationResponse[];
}

interface AnnotationStyle {
  bgcolor: string;
  borderColor: string;
}

function getAnnotationStyle(color: string): AnnotationStyle {
  switch (color.toLowerCase()) {
    case "green":
      return { bgcolor: "rgba(74, 222, 128, 0.15)", borderColor: "#4ade80" };
    case "yellow":
      return { bgcolor: "rgba(251, 191, 36, 0.15)", borderColor: "#fbbf24" };
    case "orange":
      return { bgcolor: "rgba(249, 115, 22, 0.25)", borderColor: "#f97316" };
    case "red":
      return { bgcolor: "rgba(248, 113, 113, 0.15)", borderColor: "#f87171" };
    default:
      return { bgcolor: "rgba(148, 163, 184, 0.10)", borderColor: "#94a3b8" };
  }
}

function TooltipContent({ ann }: { ann: FactAnnotationResponse }): React.ReactElement {
  return (
    <Box sx={{ p: 0.5 }}>
      <Typography variant="body2" sx={{ fontWeight: "bold", mb: 0.5 }}>
        {ann.subject} → {ann.predicate} → {ann.object}
      </Typography>
      <Typography variant="caption" sx={{ display: "block" }}>
        Time: {ann.time}
      </Typography>
      <Typography
        variant="caption"
        sx={{
          display: "block",
          color: ann.status === "consistent" ? "#4ade80" : "#f87171",
        }}
      >
        Status: {ann.status}
      </Typography>
      <Typography variant="caption" sx={{ display: "block" }}>
        Confidence: {Math.round(ann.confidence * 100)}%
      </Typography>
      {ann.status === "inconsistent" &&
        ann.inconsistencies.map((desc, i) => (
          <Typography key={i} variant="caption" sx={{ display: "block", mt: 0.25 }}>
            • {desc}
          </Typography>
        ))}
    </Box>
  );
}

const LEGEND_ITEMS = [
  { color: "#4ade80", label: "Consistent" },
  { color: "#fbbf24", label: "Minor" },
  { color: "#f97316", label: "Moderate" },
  { color: "#f87171", label: "Severe" },
] as const;

function TextHighlight({ text, annotations }: TextHighlightProps): React.ReactElement {
  const sentences = text.split(/(?<=[.!?])\s+/).filter((s) => s.trim().length > 0);

  const annotationMap = new Map<number, FactAnnotationResponse>();
  annotations.forEach((ann) => {
    if (!annotationMap.has(ann.sentence_idx)) {
      annotationMap.set(ann.sentence_idx, ann);
    }
  });

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" sx={{ mb: 1.5 }}>
        Article Text
      </Typography>

      <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
        {LEGEND_ITEMS.map(({ color, label }) => (
          <Box key={label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                bgcolor: color,
                flexShrink: 0,
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {label}
            </Typography>
          </Box>
        ))}
      </Box>

      <Box sx={{ maxHeight: 500, overflowY: "auto" }}>
        {sentences.map((sentence, idx) => {
          const ann = annotationMap.get(idx);
          if (ann) {
            const { bgcolor, borderColor } = getAnnotationStyle(ann.color);
            return (
              <Tooltip
                key={idx}
                title={<TooltipContent ann={ann} />}
                arrow
                placement="top"
              >
                <Typography
                  variant="body1"
                  sx={{
                    lineHeight: 1.8,
                    whiteSpace: "pre-wrap",
                    bgcolor,
                    borderLeft: `3px solid ${borderColor}`,
                    px: 1,
                    py: 0.5,
                    mb: 0.5,
                    borderRadius: 0.5,
                    cursor: "default",
                    display: "block",
                  }}
                >
                  {sentence}
                </Typography>
              </Tooltip>
            );
          }
          return (
            <Typography
              key={idx}
              variant="body1"
              sx={{ lineHeight: 1.8, whiteSpace: "pre-wrap", mb: 0.5 }}
            >
              {sentence}
            </Typography>
          );
        })}
      </Box>
    </Paper>
  );
}

export default TextHighlight;
