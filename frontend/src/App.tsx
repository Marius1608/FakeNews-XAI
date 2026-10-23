import React, { Suspense, lazy, useEffect, useState } from "react";
import {
  Box,
  CircularProgress,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Tooltip,
  Typography,
  useColorScheme,
} from "@mui/material";
import {
  BarChartOutlined,
  CompareArrows,
  DarkModeOutlined,
  History,
  LightModeOutlined,
  ManageSearch,
  TuneOutlined,
  ViewAgendaOutlined,
} from "@mui/icons-material";
import { checkHealth, getModels } from "./api/client";
import type { ModelsResponse } from "./types";
import ArticleHistory from "./components/ArticleHistory";

// Each tab is its own chunk — recharts / force-graph load only when a result needs them
const AnalyzeTab = lazy(() => import("./components/AnalyzeTab"));
const CompareTab = lazy(() => import("./components/CompareTab"));
const BatchTab = lazy(() => import("./components/BatchTab"));
const SettingsTab = lazy(() => import("./components/SettingsTab"));

type HealthStatus = "checking" | "ok" | "error";
type TabKey = "analyze" | "compare" | "batch" | "settings";

const NAV: { key: TabKey; label: string; title: string; icon: React.ReactElement }[] = [
  { key: "analyze", label: "Analyze", title: "Temporal coherence analysis", icon: <ManageSearch /> },
  { key: "compare", label: "Compare pipelines", title: "Compare pipelines", icon: <CompareArrows /> },
  { key: "batch", label: "Batch", title: "Batch analysis", icon: <ViewAgendaOutlined /> },
  { key: "settings", label: "Settings", title: "Settings", icon: <TuneOutlined /> },
];

function StatusDot({ status, label }: { status: HealthStatus; label: string }): React.ReactElement {
  const color = status === "ok" ? "success.main" : status === "error" ? "error.main" : "text.disabled";
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: color, flexShrink: 0 }} />
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
    </Box>
  );
}

function ThemeToggle(): React.ReactElement | null {
  const { mode, systemMode, setMode } = useColorScheme();
  if (!mode) return null; // first render before the stored mode is read
  const resolved = mode === "system" ? systemMode : mode;
  const isDark = resolved === "dark";
  return (
    <Tooltip title={isDark ? "Light mode" : "Dark mode"}>
      <IconButton
        onClick={() => setMode(isDark ? "light" : "dark")}
        aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
        sx={{ border: 1, borderColor: "divider", borderRadius: "8px", width: 40, height: 40, color: isDark ? "warning.main" : "text.secondary" }}
      >
        {isDark ? <LightModeOutlined fontSize="small" /> : <DarkModeOutlined fontSize="small" />}
      </IconButton>
    </Tooltip>
  );
}

function App(): React.ReactElement {
  const [activeTab, setActiveTab] = useState<TabKey>("analyze");
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("checking");
  const [neo4jEnabled, setNeo4jEnabled] = useState<boolean | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelsResponse | undefined>(undefined);
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);

  useEffect(() => {
    checkHealth()
      .then((h) => {
        setHealthStatus("ok");
        setNeo4jEnabled(Boolean(h.components.neo4j?.enabled));
      })
      .catch(() => setHealthStatus("error"));
  }, []);

  useEffect(() => {
    getModels()
      .then(setAvailableModels)
      .catch(() => undefined);
  }, []);

  const current = NAV.find((n) => n.key === activeTab) ?? NAV[0];

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default", display: "flex", flexWrap: "wrap", alignItems: "stretch" }}>
      {/* Sidebar — becomes a top block on narrow screens (flex-wrap) */}
      <Box
        component="nav"
        aria-label="Main"
        sx={{
          flex: "1 1 240px",
          maxWidth: { xs: "100%", md: 260 },
          bgcolor: "background.paper",
          borderRight: { md: 1 },
          borderBottom: { xs: 1, md: 0 },
          borderColor: "divider",
          px: 2,
          py: 3,
          display: "flex",
          flexDirection: "column",
          gap: 3,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 1 }}>
          <Box component="img" src="/favicon.svg" alt="" sx={{ width: 34, height: 34, flexShrink: 0, display: "block" }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontWeight: 600, fontSize: 15, lineHeight: 1.2 }}>FakeNews-XAI</Typography>
            <Typography variant="caption" color="text.secondary">
              Temporal Coherence Score
            </Typography>
          </Box>
        </Box>

        <List disablePadding sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
          {NAV.map((item) => (
            <ListItemButton
              key={item.key}
              selected={activeTab === item.key}
              aria-current={activeTab === item.key ? "page" : undefined}
              onClick={() => setActiveTab(item.key)}
            >
              <ListItemIcon sx={{ minWidth: 34 }}>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} slotProps={{ primary: { sx: { fontSize: 14, fontWeight: activeTab === item.key ? 600 : 400 } } }} />
            </ListItemButton>
          ))}
          <ListItemButton onClick={() => setHistoryOpen(true)}>
            <ListItemIcon sx={{ minWidth: 34 }}>
              <History />
            </ListItemIcon>
            <ListItemText primary="History" slotProps={{ primary: { sx: { fontSize: 14 } } }} />
          </ListItemButton>
        </List>

        <Box sx={{ mt: { md: "auto" }, p: 1.5, border: 1, borderColor: "divider", borderRadius: "10px", display: "flex", flexDirection: "column", gap: 1 }}>
          <StatusDot
            status={healthStatus}
            label={healthStatus === "ok" ? "API online" : healthStatus === "error" ? "API unavailable" : "Checking API…"}
          />
          <StatusDot
            status={neo4jEnabled === null ? "checking" : neo4jEnabled ? "ok" : "error"}
            label={neo4jEnabled === null ? "Neo4j —" : neo4jEnabled ? "Neo4j connected" : "Neo4j disabled"}
          />
        </Box>
      </Box>

      {/* Main area */}
      <Box component="main" sx={{ flex: "999 1 560px", minWidth: 0, px: { xs: 2, sm: 4, lg: 5 }, py: { xs: 3, sm: 4 } }}>
        <Box sx={{ maxWidth: 1240, mx: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
          <Box component="header" sx={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5, display: "flex", alignItems: "center", gap: 0.75 }}>
                <BarChartOutlined sx={{ fontSize: 16 }} /> {current.label}
              </Typography>
              <Typography variant="h4" component="h1" sx={{ fontSize: { xs: 24, sm: 28 } }}>
                {current.title}
              </Typography>
            </Box>
            <ThemeToggle />
          </Box>

          <Suspense
            fallback={
              <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
                <CircularProgress size={28} />
              </Box>
            }
          >
            {activeTab === "analyze" && <AnalyzeTab />}
            {activeTab === "compare" && <CompareTab />}
            {activeTab === "batch" && <BatchTab availableModels={availableModels} />}
            {activeTab === "settings" && <SettingsTab />}
          </Suspense>
        </Box>
      </Box>

      <ArticleHistory open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </Box>
  );
}

export default App;
