import React from "react";
import {
  Box,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
} from "@mui/material";
import {
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FactAnnotationResponse, TimelineEvent } from "../types";

interface TimelineProps {
  timeline: TimelineEvent[];
  annotations: FactAnnotationResponse[];
}

interface PlotPoint {
  x: number;
  y: number;
  year: number;
  label: string;
  hasInconsistency: boolean;
  color: string;
}

function getEventColor(event: TimelineEvent, ann?: FactAnnotationResponse): string {
  if (ann) {
    return ann.status === "consistent" ? "#22c55e" : "#ef4444";
  }
  return event.has_inconsistency ? "#ef4444" : "#94a3b8";
}

// Typed loosely so recharts can inject active/payload via cloneElement
function ScatterTooltip(props: object): React.ReactElement | null {
  const { active, payload } = props as {
    active?: boolean;
    payload?: Array<{ payload: PlotPoint }>;
  };
  if (!active || !payload?.length) return null;
  const pt = payload[0].payload;
  return (
    <Paper sx={{ p: 1.5, bgcolor: "background.paper" }}>
      <Typography variant="body2" sx={{ fontWeight: "bold", mb: 0.25 }}>
        {pt.label}
      </Typography>
      <Typography variant="caption" sx={{ display: "block" }}>
        Year: {pt.year}
      </Typography>
      {pt.hasInconsistency && (
        <Typography variant="caption" sx={{ display: "block", color: "#ef4444", mt: 0.25 }}>
          Inconsistency detected
        </Typography>
      )}
    </Paper>
  );
}

function Timeline({ timeline, annotations }: TimelineProps): React.ReactElement {
  if (timeline.length === 0) {
    return (
      <Paper elevation={2} sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Temporal Timeline
        </Typography>
        <Typography color="text.secondary">No temporal events to display.</Typography>
      </Paper>
    );
  }

  const annotationMap = new Map<number, FactAnnotationResponse>();
  annotations.forEach((ann) => {
    if (!annotationMap.has(ann.sentence_idx)) {
      annotationMap.set(ann.sentence_idx, ann);
    }
  });

  const validEvents = timeline.filter((e) => e.year !== null);

  // Fallback list when not enough parseable years for a chart
  if (validEvents.length < 2) {
    return (
      <Paper elevation={2} sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1.5 }}>
          Temporal Timeline
        </Typography>
        <List dense disablePadding>
          {timeline.map((event, idx) => {
            const ann = annotationMap.get(event.sentence_idx);
            const color = getEventColor(event, ann);
            return (
              <ListItem key={idx} sx={{ pl: 0 }}>
                <ListItemIcon sx={{ minWidth: 28 }}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      bgcolor: color,
                    }}
                  />
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Typography variant="body2">{event.label}</Typography>
                  }
                  secondary={
                    <Typography variant="caption">
                      {event.year !== null ? `Year: ${event.year}` : "Unknown year"}
                    </Typography>
                  }
                />
              </ListItem>
            );
          })}
        </List>
      </Paper>
    );
  }

  const plotData: PlotPoint[] = validEvents.map((event, idx) => {
    const ann = annotationMap.get(event.sentence_idx);
    return {
      x: event.year as number,
      y: idx,
      year: event.year as number,
      label: event.label,
      hasInconsistency: event.has_inconsistency,
      color: getEventColor(event, ann),
    };
  });

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" sx={{ mb: 1.5 }}>
        Temporal Timeline
      </Typography>
      <ResponsiveContainer width="100%" height={250}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(148,163,184,0.1)"
          />
          <XAxis
            type="number"
            dataKey="x"
            name="Year"
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => String(v)}
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            axisLine={{ stroke: "rgba(148,163,184,0.3)" }}
            tickLine={{ stroke: "rgba(148,163,184,0.3)" }}
          />
          <YAxis type="number" dataKey="y" hide />
          <RechartsTooltip content={<ScatterTooltip />} cursor={false} />
          <Scatter data={plotData}>
            {plotData.map((entry, index) => (
              <Cell key={index} fill={entry.color} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>

      <Box sx={{ display: "flex", gap: 2, mt: 1.5, flexWrap: "wrap" }}>
        {[
          { color: "#22c55e", label: "Consistent" },
          { color: "#ef4444", label: "Inconsistent" },
          { color: "#94a3b8", label: "Unverified" },
        ].map(({ color, label }) => (
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
    </Paper>
  );
}

export default Timeline;
