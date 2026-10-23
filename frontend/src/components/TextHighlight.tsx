import React from "react";
import { Box, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import type { FactAnnotationResponse } from "../types";
import { tint, toneColor } from "../theme/tint";
import { FONT_MONO } from "../theme/theme";
import SectionCard from "./ui/SectionCard";

interface TextHighlightProps {
  text: string;
  annotations: FactAnnotationResponse[];
}

// "yellow" has no palette slot — a fixed amber that reads on both schemes
const MINOR = "#EAAA08";

function markColor(theme: Theme, color: string): string {
  switch (color.toLowerCase()) {
    case "green":
      return toneColor(theme, "success");
    case "yellow":
      return MINOR;
    case "orange":
      return toneColor(theme, "warning");
    case "red":
      return toneColor(theme, "error");
    default:
      return (theme.vars ?? theme).palette.text.secondary;
  }
}

function TooltipContent({ ann }: { ann: FactAnnotationResponse }): React.ReactElement {
  return (
    <Box sx={{ p: 0.5, display: "flex", flexDirection: "column", gap: 0.25 }}>
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.25 }}>
        {ann.subject} → {ann.predicate} → {ann.object}
      </Typography>
      <Typography variant="caption" sx={{ fontFamily: FONT_MONO }}>
        time {ann.time} · confidence {Math.round(ann.confidence * 100)}%
      </Typography>
      <Typography variant="caption">Status: {ann.status}</Typography>
      {ann.status === "inconsistent" &&
        ann.inconsistencies.map((desc, i) => (
          <Typography key={i} variant="caption">
            • {desc}
          </Typography>
        ))}
    </Box>
  );
}

function TextHighlight({ text, annotations }: TextHighlightProps): React.ReactElement {
  const theme = useTheme();
  const sentences = text.split(/(?<=[.!?])\s+(?=[A-Z])/).filter((s) => s.trim().length > 0);

  const annotationMap = new Map<number, FactAnnotationResponse>();
  annotations.forEach((ann) => {
    if (!annotationMap.has(ann.sentence_idx)) {
      annotationMap.set(ann.sentence_idx, ann);
    }
  });

  const legend = [
    { color: toneColor(theme, "success"), label: "Consistent" },
    { color: MINOR, label: "Minor" },
    { color: toneColor(theme, "warning"), label: "Moderate" },
    { color: toneColor(theme, "error"), label: "Severe" },
  ];

  return (
    <SectionCard title="Article">
      <Box sx={{ maxHeight: 520, overflowY: "auto", pr: 0.5 }}>
        <Typography component="div" sx={{ fontSize: 15, lineHeight: 1.85, color: "text.primary", whiteSpace: "pre-wrap" }}>
          {sentences.map((sentence, idx) => {
            const ann = annotationMap.get(idx);
            const sep = idx < sentences.length - 1 ? " " : "";
            if (!ann) {
              return (
                <React.Fragment key={idx}>
                  <Box component="span" sx={{ color: "text.secondary" }}>
                    {sentence}
                  </Box>
                  {sep}
                </React.Fragment>
              );
            }
            const c = markColor(theme, ann.color);
            return (
              <React.Fragment key={idx}>
                <Tooltip title={<TooltipContent ann={ann} />} arrow placement="top">
                  <Box
                    component="mark"
                    tabIndex={0}
                    sx={{
                      color: "inherit",
                      bgcolor: theme.alpha(c, 0.14),
                      borderBottom: `2px solid ${c}`,
                      borderRadius: "3px",
                      px: 0.25,
                      cursor: "help",
                      "&:focus-visible": { outline: `2px solid ${tint(theme, "primary", 0.6)}`, outlineOffset: 2 },
                    }}
                  >
                    {sentence}
                  </Box>
                </Tooltip>
                {sep}
              </React.Fragment>
            );
          })}
        </Typography>
      </Box>

      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
        {legend.map(({ color, label }) => (
          <Box key={label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box sx={{ width: 10, height: 10, borderRadius: "3px", bgcolor: color, flexShrink: 0 }} />
            <Typography variant="caption" color="text.secondary">
              {label}
            </Typography>
          </Box>
        ))}
      </Box>
    </SectionCard>
  );
}

export default TextHighlight;
