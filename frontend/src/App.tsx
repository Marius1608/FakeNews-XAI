import React, { useEffect, useState } from "react";
import {
  AppBar,
  Box,
  Container,
  IconButton,
  Tab,
  Tabs,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";
import { History } from "@mui/icons-material";
import { checkHealth, getModels } from "./api/client";
import type { ModelsResponse } from "./types";
import AnalyzeTab from "./components/AnalyzeTab";
import ArticleHistory from "./components/ArticleHistory";
import BatchTab from "./components/BatchTab";
import CompareTab from "./components/CompareTab";

type HealthStatus = "checking" | "ok" | "error";

function App(): React.ReactElement {
  const [activeTab, setActiveTab] = useState<number>(0);
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("checking");
  const [availableModels, setAvailableModels] = useState<ModelsResponse | undefined>(undefined);
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);

  useEffect(() => {
    checkHealth()
      .then(() => setHealthStatus("ok"))
      .catch(() => setHealthStatus("error"));
  }, []);

  useEffect(() => {
    getModels()
      .then(setAvailableModels)
      .catch(() => undefined);
  }, []);

  const healthColor: string =
    healthStatus === "ok" ? "#22c55e" : healthStatus === "error" ? "#ef4444" : "#94a3b8";

  const healthLabel: string =
    healthStatus === "ok"
      ? "Connected"
      : healthStatus === "error"
        ? "Backend unavailable"
        : "Checking...";

  return (
    <Box
      sx={{
        minHeight: "100vh",
        bgcolor: "background.default",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <AppBar
        position="static"
        elevation={0}
        sx={{
          bgcolor: "background.paper",
          borderBottom: "1px solid rgba(148,163,184,0.1)",
        }}
      >
        <Toolbar sx={{ justifyContent: "space-between", py: 1.5 }}>
          <Box sx={{ display: "flex", flexDirection: "column" }}>
            <Typography variant="h6" sx={{ fontWeight: "bold" }}>
              TCS — Temporal Coherence Score
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Temporal Consistency Analysis
            </Typography>
          </Box>

          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: healthColor,
                  flexShrink: 0,
                }}
              />
              <Typography variant="caption" color="text.secondary">
                {healthLabel}
              </Typography>
            </Box>

            <Tooltip title="Article history (Neo4j)">
              <IconButton
                size="small"
                onClick={() => setHistoryOpen(true)}
                aria-label="Open article history"
              >
                <History fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </Toolbar>
      </AppBar>

      <Box
        sx={{
          bgcolor: "background.paper",
          borderBottom: 1,
          borderColor: "divider",
        }}
      >
        <Container maxWidth="lg">
          <Tabs
            value={activeTab}
            onChange={(_, newValue: number) => setActiveTab(newValue)}
          >
            <Tab label="Analyze" />
            <Tab label="Compare" />
            <Tab label="Batch" />
          </Tabs>
        </Container>
      </Box>

      <Box sx={{ flex: 1 }}>
        <Container maxWidth="lg" sx={{ py: 3 }}>
          {activeTab === 0 && <AnalyzeTab />}
          {activeTab === 1 && <CompareTab />}
          {activeTab === 2 && <BatchTab availableModels={availableModels} />}
        </Container>
      </Box>

      <Box
        component="footer"
        sx={{
          py: 2,
          textAlign: "center",
          borderTop: "1px solid rgba(148,163,184,0.1)",
        }}
      >
        <Typography variant="caption" color="text.secondary">
          Bachelor Thesis — UTCN 2026 — Marius Pantea
        </Typography>
      </Box>

      <ArticleHistory open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </Box>
  );
}

export default App;
