import React, { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Divider,
  FormControlLabel,
  IconButton,
  Paper,
  Slider,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { Delete, RestartAlt } from "@mui/icons-material";
import axios from "axios";
import type { ParameterInfo, RSSFeedsResponse } from "../types";
import {
  addCustomFeed,
  deleteCustomFeed,
  getParameters,
  getRssFeeds,
  resetParameters,
  resetRssFeeds,
  updateParameters,
  updatePredefinedFeeds,
} from "../api/client";

const GROUP_LABELS: Record<string, string> = {
  classification: "Classification Thresholds",
  internal: "Internal Verifier Tolerances",
  external: "External Verification Tolerances",
};

const GROUP_ORDER = ["classification", "internal", "external"];

function formatValue(param: ParameterInfo): string {
  return param.unit === "score" ? param.value.toFixed(2) : String(Math.round(param.value));
}

function extractError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail as string | undefined;
    return detail ?? err.message;
  }
  if (err instanceof Error) return err.message;
  return "An unexpected error occurred";
}

function SettingsTab(): React.ReactElement {
  const [rssFeeds, setRssFeeds] = useState<RSSFeedsResponse | null>(null);
  const [parameters, setParameters] = useState<ParameterInfo[]>([]);
  const [newFeedUrl, setNewFeedUrl] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadAll = async (): Promise<void> => {
    try {
      const [feeds, params] = await Promise.all([getRssFeeds(), getParameters()]);
      setRssFeeds(feeds);
      setParameters(params.parameters);
    } catch (err: unknown) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleTogglePredefined = async (url: string, enabled: boolean): Promise<void> => {
    if (!rssFeeds) return;
    const flags: Record<string, boolean> = {};
    rssFeeds.predefined.forEach((f) => {
      flags[f.url] = f.url === url ? enabled : f.enabled;
    });
    try {
      setError(null);
      const updated = await updatePredefinedFeeds(flags);
      setRssFeeds(updated);
    } catch (err: unknown) {
      setError(extractError(err));
    }
  };

  const handleAddCustomFeed = async (): Promise<void> => {
    const url = newFeedUrl.trim();
    if (!url) return;
    try {
      setError(null);
      const updated = await addCustomFeed(url);
      setRssFeeds(updated);
      setNewFeedUrl("");
    } catch (err: unknown) {
      setError(extractError(err));
    }
  };

  const handleDeleteCustomFeed = async (index: number): Promise<void> => {
    try {
      setError(null);
      const updated = await deleteCustomFeed(index);
      setRssFeeds(updated);
    } catch (err: unknown) {
      setError(extractError(err));
    }
  };

  const handleResetFeeds = async (): Promise<void> => {
    try {
      setError(null);
      const updated = await resetRssFeeds();
      setRssFeeds(updated);
    } catch (err: unknown) {
      setError(extractError(err));
    }
  };

  const handleParamChange = (key: string, value: number): void => {
    setParameters((prev) => prev.map((p) => (p.key === key ? { ...p, value } : p)));
  };

  const handleParamCommit = async (key: string, value: number): Promise<void> => {
    try {
      setError(null);
      const updated = await updateParameters({ [key]: value });
      setParameters(updated.parameters);
    } catch (err: unknown) {
      setError(extractError(err));
      // Revert to backend-confirmed state on rejection
      try {
        const fresh = await getParameters();
        setParameters(fresh.parameters);
      } catch {
        // ignore secondary failure
      }
    }
  };

  const handleResetParameters = async (): Promise<void> => {
    try {
      setError(null);
      const updated = await resetParameters();
      setParameters(updated.parameters);
    } catch (err: unknown) {
      setError(extractError(err));
    }
  };

  if (loading) {
    return <Typography color="text.secondary">Loading settings...</Typography>;
  }

  return (
    <Stack spacing={3}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* RSS feeds */}
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ mb: 1.5, justifyContent: "space-between", alignItems: "center" }}>
          <Typography variant="h6">RSS Feeds</Typography>
          <Button
            size="small"
            startIcon={<RestartAlt fontSize="small" />}
            onClick={handleResetFeeds}
          >
            Reset to Default
          </Button>
        </Stack>

        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          Predefined Feeds
        </Typography>
        <Stack spacing={0.5} sx={{ mb: 2 }}>
          {rssFeeds?.predefined.map((feed) => (
            <FormControlLabel
              key={feed.url}
              control={
                <Checkbox
                  size="small"
                  checked={feed.enabled}
                  onChange={(e) => handleTogglePredefined(feed.url, e.target.checked)}
                />
              }
              label={
                <Box>
                  <Typography variant="body2">{feed.name}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {feed.url}
                  </Typography>
                </Box>
              }
            />
          ))}
        </Stack>

        <Divider sx={{ mb: 2 }} />

        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          My Feeds
        </Typography>
        <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
          <TextField
            size="small"
            fullWidth
            placeholder="https://example.com/rss.xml"
            value={newFeedUrl}
            onChange={(e) => setNewFeedUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAddCustomFeed();
            }}
          />
          <Button variant="outlined" onClick={handleAddCustomFeed}>
            Add
          </Button>
        </Stack>
        <Stack spacing={0.5}>
          {(rssFeeds?.custom ?? []).map((url, index) => (
            <Stack key={`${url}-${index}`} direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Typography variant="body2" sx={{ flex: 1, wordBreak: "break-all" }}>
                {url}
              </Typography>
              <IconButton size="small" onClick={() => handleDeleteCustomFeed(index)} aria-label="Remove feed">
                <Delete fontSize="small" />
              </IconButton>
            </Stack>
          ))}
          {(rssFeeds?.custom ?? []).length === 0 && (
            <Typography variant="caption" color="text.secondary">
              No custom feeds added.
            </Typography>
          )}
        </Stack>
      </Paper>

      {/* Operational parameters */}
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ mb: 1.5, justifyContent: "space-between", alignItems: "center" }}>
          <Typography variant="h6">Temporal Parameters</Typography>
          <Button
            size="small"
            startIcon={<RestartAlt fontSize="small" />}
            onClick={handleResetParameters}
          >
            Reset to Default
          </Button>
        </Stack>

        {GROUP_ORDER.map((group) => {
          const groupParams = parameters.filter((p) => p.group === group);
          if (groupParams.length === 0) return null;
          return (
            <Box key={group} sx={{ mb: 3 }}>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5 }}>
                {GROUP_LABELS[group] ?? group}
              </Typography>
              <Stack spacing={2.5}>
                {groupParams.map((param) => (
                  <Box key={param.key}>
                    <Stack direction="row" sx={{ mb: 0.5, justifyContent: "space-between" }}>
                      <Typography variant="body2">{param.label}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {formatValue(param)} {param.unit !== "score" ? param.unit : ""}
                      </Typography>
                    </Stack>
                    <Slider
                      size="small"
                      value={param.value}
                      min={param.min}
                      max={param.max}
                      step={param.step}
                      onChange={(_, value) => handleParamChange(param.key, value as number)}
                      onChangeCommitted={(_, value) => handleParamCommit(param.key, value as number)}
                    />
                  </Box>
                ))}
              </Stack>
            </Box>
          );
        })}
      </Paper>
    </Stack>
  );
}

export default SettingsTab;
