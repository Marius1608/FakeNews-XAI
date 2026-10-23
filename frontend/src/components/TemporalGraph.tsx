import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, ButtonBase, Collapse, Paper, Typography } from "@mui/material";
import { ExpandLess, ExpandMore } from "@mui/icons-material";
import ForceGraph2D from "react-force-graph-2d";
import type { ForceGraphMethods, LinkObject, NodeObject } from "react-force-graph-2d";
import type { FactAnnotationResponse } from "../types";
import { useResolvedPalette } from "../theme/tint";

interface TemporalGraphProps {
  annotations: FactAnnotationResponse[];
}

// Extend the library base types with our own fields
type GraphNode = NodeObject<{ label: string }>;
type GraphLink = LinkObject<GraphNode, { label: string; color: string }>;

function TemporalGraph({ annotations }: TemporalGraphProps): React.ReactElement {
  const [expanded, setExpanded] = useState<boolean>(false);
  const [width, setWidth] = useState<number>(700);
  const graphRef = useRef<ForceGraphMethods<GraphNode, GraphLink> | undefined>(undefined);
  const boxRef = useRef<HTMLDivElement>(null);
  const pal = useResolvedPalette(); // canvas needs concrete colors, not CSS variables

  // Canvas has a fixed pixel width — follow the card's width
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.floor(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [expanded]);

  const edgeColor = useCallback(
    (color: string): string => {
      switch (color.toLowerCase()) {
        case "green":
          return pal.success.main;
        case "red":
          return pal.error.main;
        case "orange":
          return pal.warning.main;
        case "yellow":
          return "#EAAA08";
        default:
          return pal.text.disabled;
      }
    },
    [pal],
  );

  const graphData = useMemo(() => {
    const nodeSet = new Set<string>();
    annotations.forEach((ann) => {
      nodeSet.add(ann.subject);
      nodeSet.add(ann.object);
    });

    const nodes: GraphNode[] = Array.from(nodeSet).map((name) => ({ id: name, label: name }));
    const links: GraphLink[] = annotations.map((ann) => ({
      source: ann.subject,
      target: ann.object,
      label: `${ann.predicate} (${ann.time})`,
      color: edgeColor(ann.color),
    }));

    return { nodes, links };
  }, [annotations, edgeColor]);

  const handleEngineStop = useCallback((): void => {
    graphRef.current?.zoomToFit(400, 24);
  }, []);

  return (
    <Paper sx={{ overflow: "hidden" }}>
      <ButtonBase
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        sx={{ width: "100%", justifyContent: "space-between", px: { xs: 2, sm: 3 }, py: 2.25, textAlign: "left" }}
      >
        <Box>
          <Typography variant="h6" component="h2">
            Temporal knowledge graph
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {graphData.nodes.length} entities · {graphData.links.length} relations
          </Typography>
        </Box>
        {expanded ? <ExpandLess /> : <ExpandMore />}
      </ButtonBase>

      <Collapse in={expanded} unmountOnExit>
        <Box ref={boxRef} sx={{ px: { xs: 2, sm: 3 }, pb: 3 }}>
          <Box sx={{ border: 1, borderColor: "divider", borderRadius: "10px", overflow: "hidden", bgcolor: "background.default" }}>
            <ForceGraph2D<GraphNode, GraphLink>
              ref={graphRef}
              graphData={graphData}
              width={Math.max(240, width - 2)}
              height={360}
              backgroundColor="rgba(0,0,0,0)"
              nodeLabel={(node) => node.label}
              nodeColor={() => pal.primary.main}
              nodeRelSize={6}
              linkColor={(link) => link.color}
              linkDirectionalArrowLength={6}
              linkDirectionalArrowRelPos={1}
              linkLabel={(link) => link.label}
              linkWidth={2}
              cooldownTicks={100}
              onEngineStop={handleEngineStop}
            />
          </Box>

          <Box sx={{ display: "flex", gap: 2, mt: 1.5, flexWrap: "wrap" }}>
            {[
              { color: pal.success.main, label: "Consistent" },
              { color: pal.error.main, label: "Inconsistent" },
            ].map(({ color, label }) => (
              <Box key={label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                <Box sx={{ width: 20, height: 2, bgcolor: color, borderRadius: 1, flexShrink: 0 }} />
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
