import React from "react";
import { Alert, Box, Chip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { tint, toneColor } from "../theme/tint";
import type { InconsistencyResponse } from "../types";
import SectionCard from "./ui/SectionCard";

interface InconsistencyListProps {
  inconsistencies: InconsistencyResponse[];
}

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

const TYPE_LABELS: Record<string, string> = {
  temporal_cycle: "Temporal Cycle",
  causal_violation: "Causal Violation",
  ordering_error: "Ordering Error",
  date_mismatch: "Date Mismatch",
  anachronism: "Anachronism",
  duration_implausible: "Implausible Duration",
  factual_contradiction: "Factual Contradiction",
  implicit_contradiction: "Implicit Contradiction",
  future_as_past: "Future as Past",
  entity_inconsistency: "Entity Inconsistency",
};

type Tone = "error" | "warning" | "info";

function getTone(severity: string): Tone {
  if (severity === "critical" || severity === "high") return "error";
  if (severity === "medium") return "warning";
  return "info";
}

function InconsistencyList({ inconsistencies }: InconsistencyListProps): React.ReactElement {
  const theme = useTheme();

  if (inconsistencies.length === 0) {
    return <Alert severity="success">No temporal inconsistencies detected.</Alert>;
  }

  const sorted = [...inconsistencies].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99),
  );

  return (
    <SectionCard
      title="Inconsistencies"
      meta={
        <Typography variant="caption" color="text.secondary">
          {inconsistencies.length} found
        </Typography>
      }
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
        {sorted.map((item, idx) => {
          const tone = getTone(item.severity);
          const main = toneColor(theme, tone);
          return (
            <Box
              component="article"
              key={idx}
              sx={{
                border: 1,
                borderColor: tint(theme, tone, 0.35),
                bgcolor: tint(theme, tone, 0.06),
                borderRadius: "10px",
                p: 2,
                display: "flex",
                flexDirection: "column",
                gap: 1.25,
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                <Chip
                  label={item.severity_label}
                  size="small"
                  sx={{ bgcolor: main, color: (theme.vars ?? theme).palette.background.paper, borderRadius: "6px", height: 22, fontWeight: 600 }}
                />
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {TYPE_LABELS[item.type] ?? item.type}
                </Typography>
              </Box>

              <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                {item.description}
              </Typography>

              {item.evidence && (
                <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic", lineHeight: 1.6 }}>
                  Evidence: {item.evidence}
                </Typography>
              )}

              <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                {item.sentence_indices.length > 0 && (
                  <Chip
                    size="small"
                    variant="outlined"
                    sx={{ borderRadius: "6px" }}
                    label={`Sentence${item.sentence_indices.length > 1 ? "s" : ""} ${item.sentence_indices.map((i) => i + 1).join(", ")}`}
                  />
                )}
                {item.verified_by && (
                  <Chip size="small" variant="outlined" sx={{ borderRadius: "6px" }} label={`Verified by ${item.verified_by}`} />
                )}
              </Box>
            </Box>
          );
        })}
      </Box>
    </SectionCard>
  );
}

export default InconsistencyList;
