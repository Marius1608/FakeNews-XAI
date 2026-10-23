import React from "react";
import { Box, Paper, Typography } from "@mui/material";
import type { SxProps, Theme } from "@mui/material";

interface SectionCardProps {
  title?: React.ReactNode;
  // Right side of the header: counters, chips, small actions
  meta?: React.ReactNode;
  children: React.ReactNode;
  sx?: SxProps<Theme>;
}

/** The standard card of the app: 24px padding, optional title row. */
function SectionCard({ title, meta, children, sx }: SectionCardProps): React.ReactElement {
  return (
    <Paper sx={[{ p: { xs: 2, sm: 3 }, display: "flex", flexDirection: "column", gap: 2 }, ...(Array.isArray(sx) ? sx : [sx])]}>
      {(title || meta) && (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1.5, flexWrap: "wrap" }}>
          {title && (
            <Typography variant="h6" component="h2">
              {title}
            </Typography>
          )}
          {meta && <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>{meta}</Box>}
        </Box>
      )}
      {children}
    </Paper>
  );
}

export default SectionCard;
