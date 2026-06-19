import React from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Chip,
  Paper,
  Typography,
} from "@mui/material";
import { ExpandMore } from "@mui/icons-material";
import type { InconsistencyResponse } from "../types";

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

function getSeverityColor(severity: string): "error" | "warning" | "default" {
  if (severity === "critical") return "error";
  if (severity === "high") return "warning";
  return "default";
}

function getVerifiedByColor(verifiedBy: string): "default" | "info" | "secondary" {
  const v = verifiedBy.toLowerCase();
  if (v.includes("wikidata")) return "info";
  if (v.includes("reference") || v.includes("kg")) return "secondary";
  return "default";
}

function InconsistencyList({ inconsistencies }: InconsistencyListProps): React.ReactElement {
  if (inconsistencies.length === 0) {
    return (
      <Alert severity="success">No temporal inconsistencies detected ✓</Alert>
    );
  }

  const sorted = [...inconsistencies].sort(
    (a, b) =>
      (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99),
  );

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
        <Typography variant="h6">Inconsistencies Detected</Typography>
        <Chip label={inconsistencies.length} color="error" size="small" />
      </Box>

      {sorted.map((item, idx) => (
        <Accordion
          key={idx}
          disableGutters
          elevation={0}
          sx={{
            "&:before": { display: "none" },
            border: "1px solid rgba(148,163,184,0.15)",
            borderRadius: 1,
            mb: 1,
            "&:last-child": { mb: 0 },
          }}
        >
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1,
                flexWrap: "wrap",
                width: "100%",
                pr: 1,
              }}
            >
              <Chip
                label={item.severity_label}
                color={getSeverityColor(item.severity)}
                size="small"
              />
              <Typography variant="body2" sx={{ flex: 1, minWidth: 120 }}>
                {TYPE_LABELS[item.type] ?? item.type}
              </Typography>
              <Chip
                label={item.verified_by}
                color={getVerifiedByColor(item.verified_by)}
                size="small"
                variant="outlined"
              />
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="body2" sx={{ mb: 1 }}>
              {item.description}
            </Typography>
            {item.evidence && (
              <Typography
                variant="body2"
                sx={{ fontStyle: "italic", mb: 1, color: "text.secondary" }}
              >
                Evidence: {item.evidence}
              </Typography>
            )}
            <Typography variant="caption" color="text.secondary">
              Affects sentences: {item.sentence_indices.join(", ")}
            </Typography>
          </AccordionDetails>
        </Accordion>
      ))}
    </Paper>
  );
}

export default InconsistencyList;
