/* App.tsx — root application shell */

import React from "react";
import { Box, Typography } from "@mui/material";

// root shell (components will be wired here in Sprint 4)

function App(): React.ReactElement {
  return (
    <Box
      sx={{
        minHeight: "100vh",
        bgcolor: "background.default",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Typography variant="h5" color="primary">
        FakeNews-XAI
      </Typography>
    </Box>
  );
}

export default App;
