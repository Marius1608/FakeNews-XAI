import React, { useCallback, useMemo, useRef, useState } from "react";
import { Box, Collapse, IconButton, Paper, Typography } from "@mui/material";
import { ExpandLess, ExpandMore } from "@mui/icons-material";
import ForceGraph2D from "react-force-graph-2d";
import type { ForceGraphMethods, LinkObject, NodeObject } from "react-force-graph-2d";
import type { FactAnnotationResponse } from "../types";

interface TemporalGraphProps {
  annotations: FactAnnotationResponse[];
}

// Extend the library base types with our own fields
type GraphNode = NodeObject<{ label: string }>;
type GraphLink = LinkObject<GraphNode, { label: string; color: string }>;

const COLOR_MAP: Record<string, string> = {
  green: "#22c55e",
  red: "#ef4444",
  orange: "#f97316",
  yellow: "#eab308",
};

function getEdgeColor(color: string): string {
  return COLOR_MAP[color.toLowerCase()] ?? "#94a3b8";
}

const LEGEND_ITEMS = [
  { color: "#22c55e", label: "Consistent" },
  { color: "#ef4444", label: "Inconsistent" },
] as const;

function TemporalGraph({ annotations }: TemporalGraphProps): React.ReactElement {
  const [expanded, setExpanded] = useState<boolean>(false);
  const graphRef = useRef<ForceGraphMethods<GraphNode, GraphLink> | undefined>(undefined);

  const graphData = useMemo(() => {
    const nodeSet = new Set<string>();
    annotations.forEach((ann) => {
      nodeSet.add(ann.subject);
      nodeSet.add(ann.object);
    });

    const nodes: GraphNode[] = Array.from(nodeSet).map((name) => ({
      id: name,
      label: name,
    }));

    const links: GraphLink[] = annotations.map((ann) => ({
      source: ann.subject,
      target: ann.object,
      label: `${ann.predicate} (${ann.time})`,
      color: getEdgeColor(ann.color),
    }));

    return { nodes, links };
  }, [annotations]);

  const handleEngineStop = useCallback((): void => {
    graphRef.current?.zoomToFit(400);
  }, []);

  return (
    <Paper elevation={2}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          p: 2,
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <Typography variant="h6">Temporal Knowledge Graph</Typography>
        <IconButton size="small">
          {expanded ? <ExpandLess /> : <ExpandMore />}
        </IconButton>
      </Box>

      <Collapse in={expanded}>
        <Box sx={{ px: 2, pb: 2 }}>
          <ForceGraph2D<GraphNode, GraphLink>
            ref={graphRef}
            graphData={graphData}
            width={700}
            height={350}
            nodeLabel={(node) => node.label}
            nodeColor={() => "#60a5fa"}
            nodeRelSize={6}
            linkColor={(link) => link.color}
            linkDirectionalArrowLength={6}
            linkLabel={(link) => link.label}
            linkWidth={2}
            cooldownTicks={100}
            onEngineStop={handleEngineStop}
          />

          <Box sx={{ display: "flex", gap: 2, mt: 1.5, flexWrap: "wrap" }}>
            {LEGEND_ITEMS.map(({ color, label }) => (
              <Box key={label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                <Box
                  sx={{
                    width: 20,
                    height: 2,
                    bgcolor: color,
                    borderRadius: 1,
                    flexShrink: 0,
                  }}
                />
                <Typography variant="caption" color="text.secondary">
                  {label}
                </Typography>
              </Box>
            ))}
          </Box>
        </Box>
      </Collapse>
    </Paper>
  );
}

export default TemporalGraph;
