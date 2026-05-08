import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemSecondaryAction,
  ListItemText,
  Tooltip,
  Typography,
} from "@mui/material";
import { Close, Delete } from "@mui/icons-material";
import type { StoredArticle } from "../types";
import { deleteArticle, getArticles } from "../api/client";

interface ArticleHistoryProps {
  open: boolean;
  onClose: () => void;
}

function ArticleHistory({ open, onClose }: ArticleHistoryProps): React.ReactElement {
  const [articles, setArticles] = useState<StoredArticle[]>([]);
  const [neo4jEnabled, setNeo4jEnabled] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchArticles = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getArticles();
      setNeo4jEnabled(response.neo4j_enabled);
      setArticles(response.articles);
    } catch {
      setError("Failed to load article history.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void fetchArticles();
    }
  }, [open, fetchArticles]);

  const handleDelete = async (articleId: string): Promise<void> => {
    setDeletingId(articleId);
    setError(null);
    try {
      await deleteArticle(articleId);
      setArticles((prev) => prev.filter((a) => a.article_id !== articleId));
    } catch {
      setError(`Failed to delete article ${articleId}.`);
    } finally {
      setDeletingId(null);
    }
  };

  const formatDate = (raw: string | null): string => {
    if (!raw) return "Unknown date";
    try {
      return new Date(raw).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return raw;
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{ paper: { sx: { width: 350, display: "flex", flexDirection: "column" } } }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 2,
          py: 1.5,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid",
          borderColor: "divider",
          flexShrink: 0,
        }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: "medium" }}>
          Article History
        </Typography>
        <IconButton size="small" onClick={onClose} aria-label="Close history">
          <Close fontSize="small" />
        </IconButton>
      </Box>

      {/* Body */}
      <Box sx={{ flex: 1, overflowY: "auto", px: 0 }}>
        {!neo4jEnabled && (
          <Box sx={{ p: 2 }}>
            <Alert severity="info">
              Neo4j not configured. Enable in <code>.env</code> to save articles.
            </Alert>
          </Box>
        )}

        {neo4jEnabled && isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", pt: 4 }}>
            <CircularProgress size={28} />
          </Box>
        )}

        {neo4jEnabled && error && (
          <Box sx={{ p: 2 }}>
            <Alert severity="error" onClose={() => setError(null)}>
              {error}
            </Alert>
          </Box>
        )}

        {neo4jEnabled && !isLoading && articles.length === 0 && !error && (
          <Box sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">
              No articles saved yet. Use{" "}
              <strong>Save to Neo4j</strong> when analyzing to store results.
            </Typography>
          </Box>
        )}

        {neo4jEnabled && !isLoading && articles.length > 0 && (
          <List dense disablePadding>
            {articles.map((article, idx) => (
              <React.Fragment key={article.article_id}>
                <ListItem
                  alignItems="flex-start"
                  sx={{ pr: 6 }}
                >
                  <ListItemText
                    primary={
                      <Typography variant="body2" noWrap sx={{ fontWeight: "medium" }}>
                        {article.title ?? <em>Untitled</em>}
                      </Typography>
                    }
                    secondary={
                      <Box component="span" sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
                        {article.source && (
                          <Typography variant="caption" color="text.secondary" noWrap>
                            {article.source}
                          </Typography>
                        )}
                        <Typography variant="caption" color="text.secondary">
                          {formatDate(article.analyzed_at)} · {article.fact_count} facts
                        </Typography>
                      </Box>
                    }
                  />
                  <ListItemSecondaryAction>
                    <Tooltip title="Delete article">
                      <span>
                        <IconButton
                          size="small"
                          edge="end"
                          onClick={() => void handleDelete(article.article_id)}
                          disabled={deletingId === article.article_id}
                          aria-label="Delete article"
                        >
                          {deletingId === article.article_id ? (
                            <CircularProgress size={16} />
                          ) : (
                            <Delete fontSize="small" />
                          )}
                        </IconButton>
                      </span>
                    </Tooltip>
                  </ListItemSecondaryAction>
                </ListItem>
                {idx < articles.length - 1 && <Divider component="li" />}
              </React.Fragment>
            ))}
          </List>
        )}
      </Box>

      {/* Footer */}
      {neo4jEnabled && articles.length > 0 && (
        <Box
          sx={{
            px: 2,
            py: 1,
            borderTop: "1px solid",
            borderColor: "divider",
            flexShrink: 0,
          }}
        >
          <Typography variant="caption" color="text.secondary">
            {articles.length} article{articles.length !== 1 ? "s" : ""} stored
          </Typography>
        </Box>
      )}
    </Drawer>
  );
}

export default ArticleHistory;
