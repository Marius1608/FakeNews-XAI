import React, { useEffect, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, CircularProgress, FormControlLabel, Stack, Switch, Tooltip, Typography } from "@mui/material";
import { CompareArrows, Psychology } from "@mui/icons-material";
import axios from "axios";
import type { AnalyzeRequest, AnalyzeResponse, CrossArticleResponse, ModelsResponse } from "../types";
import { analyzeArticle, crossCheckArticle, getModels, verifyArticle } from "../api/client";
import ArticleInput from "./ArticleInput";
import TCSScoreDisplay from "./TCSScoreDisplay";
import TextHighlight from "./TextHighlight";
import InconsistencyList from "./InconsistencyList";
import RSSVerificationPanel from "./RSSVerificationPanel";
import Timeline from "./Timeline";
import TemporalGraph from "./TemporalGraph";

function AnalyzeTab(): React.ReactElement {
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResponse | null>(null);
  const [articleText, setArticleText] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelsResponse | undefined>(undefined);
  const [persist, setPersist] = useState<boolean>(false);
  const [resultWasPersisted, setResultWasPersisted] = useState<boolean>(false);
  const [useRss, setUseRss] = useState<boolean>(false);
  const [crossArticleResult, setCrossArticleResult] = useState<CrossArticleResponse | null>(null);
  const [crossArticleLoading, setCrossArticleLoading] = useState<boolean>(false);
  const [verdict, setVerdict] = useState<string | null>(null);

  useEffect(() => {
    getModels()
      .then(setAvailableModels)
      .catch(() => undefined);
  }, []);

  const handleSubmit = async (request: AnalyzeRequest): Promise<void> => {
    setIsLoading(true);
    setError(null);
    setAnalyzeResult(null);
    setArticleText(request.text);
    setCrossArticleResult(null);
    setVerdict(null);
    setResultWasPersisted(false);
    try {
      const result = await analyzeArticle({ ...request, persist, use_rss: useRss });
      setAnalyzeResult(result);
      setResultWasPersisted(persist);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail as string | undefined;
        setError(detail ?? err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const crossArticleConflicts = analyzeResult?.cross_article_inconsistencies ?? [];

  const handleCrossArticleCheck = async (): Promise<void> => {
    if (!analyzeResult?.article_id) return;
    setCrossArticleLoading(true);
    setCrossArticleResult(null);
    try {
      const result = await crossCheckArticle(analyzeResult.article_id);
      setCrossArticleResult(result);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail as string | undefined;
        setError(detail ?? err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setCrossArticleLoading(false);
    }
  };

  const handleVerdict = async (v: string): Promise<void> => {
    if (!analyzeResult?.article_id) return;
    try {
      await verifyArticle(analyzeResult.article_id, { verdict: v as "true" | "fake" });
      setVerdict(v);
    } catch {
      setError("Failed to save verdict.");
    }
  };

  return (
    <Stack spacing={3}>
      <ArticleInput
        onSubmit={handleSubmit}
        isLoading={isLoading}
        showPipelineSelector={true}
        availableModels={availableModels}
      />

      <Stack direction="row" spacing={2} sx={{ mt: -1, alignItems: "center" }}>
        <FormControlLabel
          control={
            <Checkbox
              size="small"
              checked={persist}
              onChange={(e) => setPersist(e.target.checked)}
            />
          }
          label={<Typography variant="body2">Save</Typography>}
        />
        <Tooltip title="Fallback for recent facts not yet in Wikidata — searches live RSS news feeds">
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={useRss}
                onChange={(e) => setUseRss(e.target.checked)}
              />
            }
            label={<Typography variant="body2">RSS Stream</Typography>}
          />
        </Tooltip>
      </Stack>

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {analyzeResult && (
        <>
          <TCSScoreDisplay
            score={analyzeResult.score}
            label={analyzeResult.label}
            summary={analyzeResult.summary}
            nClaims={analyzeResult.n_claims}
            nInconsistencies={analyzeResult.n_inconsistencies}
            coherenceFactor={analyzeResult.coherence_factor}
            pipeline={analyzeResult.pipeline}
            model={analyzeResult.model}
            processingTimeMs={analyzeResult.processing_time_ms}
          />

          {/* Human validation — only shown when article was saved to Neo4j */}
          {analyzeResult.article_id && resultWasPersisted && (
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Typography variant="body2" color="text.secondary">
                Mark as:
              </Typography>
              <Button
                variant="outlined"
                color="success"
                size="small"
                onClick={() => handleVerdict("true")}
                disabled={verdict !== null}
              >
                ✓ TRUE
              </Button>
              <Button
                variant="outlined"
                color="error"
                size="small"
                onClick={() => handleVerdict("fake")}
                disabled={verdict !== null}
              >
                ✗ FAKE
              </Button>
              {verdict && (
                <Chip
                  label={`Marked as ${verdict.toUpperCase()}`}
                  color={verdict === "true" ? "success" : "error"}
                  size="small"
                />
              )}
            </Box>
          )}

          {/* Cross-article check button — only shown when article was saved to Neo4j */}
          {analyzeResult.article_id && resultWasPersisted && (
            <Box>
              <Button
                variant="outlined"
                size="small"
                startIcon={crossArticleLoading ? <CircularProgress size={16} /> : <CompareArrows />}
                disabled={crossArticleLoading || !analyzeResult}
                onClick={handleCrossArticleCheck}
              >
                Check against saved articles
              </Button>

              {crossArticleResult && (
                <Box sx={{ mt: 1.5 }}>
                  {crossArticleResult.conflicts.length === 0 ? (
                    <Alert severity="success">
                      No conflicts with saved articles ({crossArticleResult.checked_against} checked).
                    </Alert>
                  ) : (
                    <Alert severity="warning">
                      <Typography variant="body2" sx={{ fontWeight: "medium", mb: 0.5 }}>
                        {crossArticleResult.conflicts.length} conflict{crossArticleResult.conflicts.length !== 1 ? "s" : ""} found
                        ({crossArticleResult.checked_against} articles checked)
                      </Typography>
                      <Stack spacing={0.5}>
                        {crossArticleResult.conflicts.map((c, i) => (
                          <Box key={i}>
                            <Typography variant="caption" sx={{ display: "block", fontWeight: "medium" }}>
                              • {c.entity}: {c.description}
                            </Typography>
                            {c.conflicting_article_title && (
                              <Typography variant="caption" color="text.secondary" sx={{ display: "block", pl: 1.5 }}>
                                Source: {c.conflicting_article_title}
                              </Typography>
                            )}
                          </Box>
                        ))}
                      </Stack>
                    </Alert>
                  )}
                </Box>
              )}
            </Box>
          )}

          {/* AI Explanation */}
          {analyzeResult.llm_explanation && analyzeResult.llm_explanation.length > 50 && (
            <Alert severity="info" icon={<Psychology fontSize="inherit" />}>
              <Typography variant="body2" sx={{ fontWeight: "medium", mb: 0.5 }}>
                AI Explanation
              </Typography>
              <Typography variant="body2">
                {analyzeResult.llm_explanation}
              </Typography>
            </Alert>
          )}

          {/* Cross-article conflicts banner */}
          {crossArticleConflicts.length > 0 && (
            <Alert
              severity="warning"
              action={
                <Chip
                  label={`${crossArticleConflicts.length} conflict${crossArticleConflicts.length !== 1 ? "s" : ""}`}
                  size="small"
                  color="warning"
                />
              }
            >
              <Box>
                <Typography variant="body2" sx={{ fontWeight: "medium", mb: 0.5 }}>
                  Cross-article conflicts detected
                </Typography>
                {crossArticleConflicts.map((c, i) => (
                  <Typography key={i} variant="caption" sx={{ display: "block" }}>
                    • {c.description}
                  </Typography>
                ))}
                {analyzeResult.article_id && resultWasPersisted && (
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                    Saved as {analyzeResult.article_id}
                  </Typography>
                )}
              </Box>
            </Alert>
          )}

          {/* Saved without conflicts */}
          {analyzeResult.article_id && resultWasPersisted && crossArticleConflicts.length === 0 && (
            <Alert severity="success" sx={{ py: 0.5 }}>
              Saved to Neo4j — no cross-article conflicts found.
            </Alert>
          )}

          <TextHighlight
            text={articleText}
            annotations={analyzeResult.fact_annotations}
          />
          <InconsistencyList inconsistencies={analyzeResult.inconsistency_details} />
          <RSSVerificationPanel verifications={analyzeResult.rss_verifications ?? []} />
          <Timeline
            timeline={analyzeResult.timeline}
            annotations={analyzeResult.fact_annotations}
          />
          <TemporalGraph annotations={analyzeResult.fact_annotations} />
        </>
      )}
    </Stack>
  );
}

export default AnalyzeTab;
