import React from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Card,
  CardContent,
  Chip,
  Stack,
  Typography,
} from "@mui/material";
import { Cancel, CheckCircle, ExpandMore, WifiTethering } from "@mui/icons-material";
import type { RSSVerification } from "../types";

interface Props {
  verifications: RSSVerification[];
}

function formatRelativeTime(timestamp: string): string {
  if (!timestamp) return "unknown time";
  try {
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return timestamp;
    const diffMs = Date.now() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? "s" : ""} ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? "s" : ""} ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
  } catch {
    return timestamp;
  }
}

function RSSVerificationPanel({ verifications }: Props): React.ReactElement | null {
  if (verifications.length === 0) return null;

  const anyVerified = verifications.some((v) => v.verified);
  const anyContradicted = verifications.some((v) => !v.verified);
  const iconColor = anyContradicted ? "warning.main" : anyVerified ? "success.main" : "text.secondary";

  return (
    <Accordion defaultExpanded={false} variant="outlined">
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <WifiTethering sx={{ color: iconColor, fontSize: 20 }} />
          <Typography variant="subtitle2">
            RSS Stream Verification
          </Typography>
          <Chip
            label={`${verifications.length} match${verifications.length !== 1 ? "es" : ""}`}
            size="small"
            variant="outlined"
            sx={{ ml: 0.5 }}
          />
        </Box>
      </AccordionSummary>

      <AccordionDetails>
        <Stack spacing={1.5}>
          {verifications.map((v, i) => (
            <Card key={i} variant="outlined" sx={{ bgcolor: "background.default" }}>
              <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
                <Stack direction="row" spacing={1} sx={{ mb: 0.75, alignItems: "center", flexWrap: "wrap" }}>
                  <Chip label={v.feed_name} size="small" color="primary" variant="outlined" />
                  <Chip
                    icon={v.verified ? <CheckCircle fontSize="small" /> : <Cancel fontSize="small" />}
                    label={v.verified ? "Confirmed" : "Contradicted"}
                    size="small"
                    color={v.verified ? "success" : "error"}
                  />
                  <Typography variant="caption" color="text.secondary">
                    {formatRelativeTime(v.timestamp)}
                  </Typography>
                </Stack>

                <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.25 }}>
                  {v.matched_entity}
                </Typography>
                <Typography variant="body2" sx={{ fontStyle: "italic", color: "text.secondary" }}>
                  "{v.headline}"
                </Typography>
              </CardContent>
            </Card>
          ))}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

export default RSSVerificationPanel;
