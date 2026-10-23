import React from "react";
import { Box, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import type { FactAnnotationResponse, SentenceSpan } from "../types";
import { tint, toneColor } from "../theme/tint";
import { FONT_MONO } from "../theme/theme";
import SectionCard from "./ui/SectionCard";

interface TextHighlightProps {
  text: string;
  annotations: FactAnnotationResponse[];
  // Backend sentence spans — the same segmentation as sentence_idx. Optional for older backends.
  sentences?: SentenceSpan[];
}

interface Segment {
  text: string;
  idx: number | null; // sentence index, or null for whitespace between sentences
}

/** Cut the text exactly where the backend did. Spans are in code points (Python str), so slice code points, not UTF-16 units. */
function segmentText(text: string, spans?: SentenceSpan[]): Segment[] {
  if (spans && spans.length > 0) {
    const chars = Array.from(text);
    const out: Segment[] = [];
    let pos = 0;
    spans.forEach((sp, idx) => {
      if (sp.start > pos) out.push({ text: chars.slice(pos, sp.start).join(""), idx: null });
      out.push({ text: chars.slice(sp.start, sp.end).join(""), idx });
      pos = sp.end;
    });
    if (pos < chars.length) out.push({ text: chars.slice(pos).join(""), idx: null });
    return out;
  }
  // Fallback: approximate split (may disagree with spaCy on abbreviations like "U.S.")
  const parts = text.split(/(?<=[.!?])\s+(?=[A-Z])/).filter((s) => s.trim().length > 0);
  return parts.flatMap((p, idx) => (idx < parts.length - 1 ? [{ text: p, idx }, { text: " ", idx: null }] : [{ text: p, idx }]));
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

function TextHighlight({ text, annotations, sentences }: TextHighlightProps): React.ReactElement {
  const theme = useTheme();
  const segments = segmentText(text, sentences);

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
          {segments.map((seg, k) => {
            if (seg.idx === null) return <React.Fragment key={k}>{seg.text}</React.Fragment>;
            const ann = annotationMap.get(seg.idx);
            const sentence = seg.text;
            if (!ann) {
              return (
                <Box component="span" key={k} sx={{ color: "text.secondary" }}>
                  {sentence}
                </Box>
              );
            }
            const c = markColor(theme, ann.color);
            return (
              <React.Fragment key={k}>
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
