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
import { useResolvedPalette } from "../theme/tint";
import { FONT_MONO } from "../theme/theme";
import SectionCard from "./ui/SectionCard";
import {
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { FactAnnotationResponse, TimelineEvent } from "../types";

interface TimelineProps {
  timeline: TimelineEvent[];
  annotations: FactAnnotationResponse[];
}

interface PlotPoint {
  x: number;
  y: number;
  z: number;
  year: number;
  label: string;
  hasInconsistency: boolean;
  color: string;
}

type Palette = ReturnType<typeof useResolvedPalette>;

function getEventColor(pal: Palette, event: TimelineEvent, ann?: FactAnnotationResponse): string {
  const ok = pal.success.main;
  const bad = pal.error.main;
  if (ann) {
    return ann.status === "consistent" ? ok : bad;
  }
  return event.has_inconsistency ? bad : pal.text.disabled;
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
    <Paper sx={{ p: 1.5, bgcolor: "background.paper", borderRadius: "10px" }}>
      <Typography variant="body2" sx={{ fontWeight: "bold", mb: 0.25 }}>
        {pt.label}
      </Typography>
      <Typography variant="caption" sx={{ display: "block", fontFamily: FONT_MONO }}>
        {pt.year}
      </Typography>
      {pt.hasInconsistency && (
        <Typography variant="caption" sx={{ display: "block", color: "error.main", mt: 0.25 }}>
          Inconsistency detected
        </Typography>
      )}
    </Paper>
  );
}

function Timeline({ timeline, annotations }: TimelineProps): React.ReactElement {
  const pal = useResolvedPalette();
  const axisColor = pal.text.secondary;
  const gridColor = pal.divider;

  if (timeline.length === 0) {
    return (
      <SectionCard title="Timeline">
        <Typography variant="body2" color="text.secondary">
          No temporal events to display.
        </Typography>
      </SectionCard>
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
      <SectionCard title="Timeline">
        <List dense disablePadding>
          {timeline.map((event, idx) => {
            const ann = annotationMap.get(event.sentence_idx);
            const color = getEventColor(pal, event, ann);
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
      </SectionCard>
    );
  }

  const plotData: PlotPoint[] = validEvents.map((event, idx) => {
    const ann = annotationMap.get(event.sentence_idx);
    return {
      x: event.year as number,
      y: idx,
      z: 1,
      year: event.year as number,
      label: event.label,
      hasInconsistency: event.has_inconsistency,
      color: getEventColor(pal, event, ann),
    };
  });

  return (
    <SectionCard
      title="Timeline"
      meta={
        <Typography variant="caption" color="text.secondary">
          {plotData.length} dated claims · {Math.min(...plotData.map((p) => p.year))} – {Math.max(...plotData.map((p) => p.year))}
        </Typography>
      }
    >
      <ResponsiveContainer width="100%" height={250}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
          <XAxis
            type="number"
            dataKey="x"
            name="Year"
            domain={["dataMin", "dataMax"]}
            allowDecimals={false}
            padding={{ left: 24, right: 24 }}
            tickFormatter={(v: number) => String(v)}
            tick={{ fill: axisColor, fontSize: 12, fontFamily: FONT_MONO }}
            axisLine={{ stroke: gridColor }}
            tickLine={{ stroke: gridColor }}
          />
          <YAxis type="number" dataKey="y" hide domain={[-0.5, plotData.length - 0.5]} />
          <ZAxis type="number" dataKey="z" range={[140, 140]} />
          <RechartsTooltip content={<ScatterTooltip />} cursor={false} />
          <Scatter data={plotData}>
            {plotData.map((entry, index) => (
              <Cell key={index} fill={entry.color} stroke={pal.background.paper} strokeWidth={2} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>

      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
        {[
          { color: pal.success.main, label: "Consistent" },
          { color: pal.error.main, label: "Inconsistent" },
          { color: pal.text.disabled, label: "Unverified" },
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
    </SectionCard>
  );
}

export default Timeline;
