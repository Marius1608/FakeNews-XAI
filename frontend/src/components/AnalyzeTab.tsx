import React, { useEffect, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, CircularProgress, Collapse, FormControlLabel, Paper, Skeleton, Stack, Switch, Tooltip, Typography } from "@mui/material";
import { Add, CheckCircleOutlined, CompareArrows, EditOutlined, HighlightOff, Psychology } from "@mui/icons-material";
import { getModelLabel } from "../utils/modelLabels";
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
import SectionCard from "./ui/SectionCard";

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
  // Input collapses to a summary bar once a result is shown
  const [inputCollapsed, setInputCollapsed] = useState<boolean>(false);
  const [inputKey, setInputKey] = useState<number>(0); // bump → fresh, empty ArticleInput
  const [lastRequest, setLastRequest] = useState<AnalyzeRequest | null>(null);
  // Elapsed time while the pipeline runs (Pipeline B can take a minute on CPU)
  const [elapsed, setElapsed] = useState<number>(0);

  useEffect(() => {
    if (!isLoading) return;
    setElapsed(0);
    const started = Date.now();
    const t = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(t);
  }, [isLoading]);

  const startNewAnalysis = (): void => {
    setInputKey((k) => k + 1);
    setInputCollapsed(false);
    setAnalyzeResult(null);
    setError(null);
  };

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
    setLastRequest(request);
    try {
      const result = await analyzeArticle({ ...request, persist, use_rss: useRss });
      setAnalyzeResult(result);
      setResultWasPersisted(persist);
      setInputCollapsed(true);
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

  const persisted = Boolean(analyzeResult?.article_id && resultWasPersisted);

  return (
    <Stack spacing={3}>
      {/* One Stack child for bar + input, so the hidden input leaves no extra gap */}
      <Box>
        {/* Compact summary of the analyzed article — replaces the input card after a result */}
        {inputCollapsed && lastRequest && (
          <Paper sx={{ px: { xs: 2, sm: 3 }, py: 1.5, display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
            <Box sx={{ flex: "1 1 260px", minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                {lastRequest.title || lastRequest.text.slice(0, 90) + (lastRequest.text.length > 90 ? "…" : "")}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {lastRequest.text.length} characters
                {lastRequest.publication_date ? ` · published ${lastRequest.publication_date}` : ""}
                {" · "}
                {lastRequest.pipeline === "llm" ? "Pipeline B" : "Pipeline A"}
                {lastRequest.model ? ` · ${getModelLabel(lastRequest.model)}` : ""}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button variant="outlined" size="small" startIcon={<EditOutlined />} onClick={() => setInputCollapsed(false)}>
                Edit
              </Button>
              <Button variant="contained" size="small" startIcon={<Add />} onClick={startNewAnalysis}>
                New analysis
              </Button>
            </Box>
          </Paper>
        )}

        {/* Kept mounted while collapsed so "Edit" restores text, metadata and pipeline */}
        <Collapse in={!inputCollapsed} unmountOnExit={false}>
          <SectionCard
            title="Article input"
            meta={
              analyzeResult && (
                <>
                  <Button size="small" onClick={() => setInputCollapsed(true)}>
                    Hide
                  </Button>
                  <Button size="small" variant="outlined" startIcon={<Add />} onClick={startNewAnalysis}>
                    New analysis
                  </Button>
                </>
              )
            }
          >
            <ArticleInput
              key={inputKey}
              onSubmit={handleSubmit}
              isLoading={isLoading}
              showPipelineSelector={true}
              availableModels={availableModels}
              showExamples={true}
            />

            <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", pt: 0.5, borderTop: 1, borderColor: "divider" }}>
              <FormControlLabel
                control={<Checkbox size="small" checked={persist} onChange={(e) => setPersist(e.target.checked)} />}
                label={<Typography variant="body2">Save to Neo4j</Typography>}
              />
              <Tooltip title="Fallback for recent facts not yet in Wikidata — searches live RSS news feeds">
                <FormControlLabel
                  control={<Switch size="small" checked={useRss} onChange={(e) => setUseRss(e.target.checked)} />}
                  label={<Typography variant="body2">RSS stream</Typography>}
                />
              </Tooltip>
            </Stack>
          </SectionCard>
        </Collapse>
      </Box>

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {isLoading && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }} role="status">
          <CircularProgress size={18} />
          <Typography variant="body2">
            Analyzing… <Box component="span" sx={{ fontFamily: "monospace" }}>{elapsed} s</Box>
          </Typography>
          {lastRequest?.pipeline === "llm" && (
            <Typography variant="caption" color="text.secondary">
              Pipeline B runs a local LLM — it can take a minute or more.
            </Typography>
          )}
        </Box>
      )}

      {isLoading && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3 }} aria-busy="true" aria-label="Analyzing">
          <Box sx={{ flex: "3 1 520px", minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
            <Skeleton variant="rounded" height={220} />
            <Skeleton variant="rounded" height={260} />
          </Box>
          <Box sx={{ flex: "2 1 340px", minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
            <Skeleton variant="rounded" height={360} />
            <Skeleton variant="rounded" height={160} />
          </Box>
        </Box>
      )}

      {analyzeResult && !isLoading && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "flex-start" }}>
          {/* Left column — the article and where its claims sit in time */}
          <Box sx={{ flex: "3 1 520px", minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
            <TextHighlight text={articleText} annotations={analyzeResult.fact_annotations} sentences={analyzeResult.sentences} />
            <Timeline timeline={analyzeResult.timeline} annotations={analyzeResult.fact_annotations} />
            <TemporalGraph annotations={analyzeResult.fact_annotations} />
          </Box>

          {/* Right column — verdict, findings, explanation, actions (shown first on phones) */}
          <Box sx={{ flex: "2 1 340px", minWidth: 0, display: "flex", flexDirection: "column", gap: 3, order: { xs: -1, md: 0 } }}>
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

            <InconsistencyList inconsistencies={analyzeResult.inconsistency_details} />

            {analyzeResult.llm_explanation && analyzeResult.llm_explanation.length > 50 && (
              <SectionCard
                title={
                  <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
                    <Psychology fontSize="small" color="primary" /> Explanation
                  </Box>
                }
              >
                <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                  {analyzeResult.llm_explanation}
                </Typography>
              </SectionCard>
            )}

            <RSSVerificationPanel verifications={analyzeResult.rss_verifications ?? []} />

            {crossArticleConflicts.length > 0 && (
              <Alert severity="warning">
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                  {crossArticleConflicts.length} cross-article conflict{crossArticleConflicts.length !== 1 ? "s" : ""}
                </Typography>
                {crossArticleConflicts.map((c, i) => (
                  <Typography key={i} variant="caption" sx={{ display: "block" }}>
                    • {c.description}
                  </Typography>
                ))}
              </Alert>
            )}

            {/* Human-in-the-loop — only when the article was saved to Neo4j */}
            {persisted && analyzeResult.article_id && (
              <SectionCard
                title="Saved article"
                meta={
                  <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                    {analyzeResult.article_id}
                  </Typography>
                }
              >
                {crossArticleConflicts.length === 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Saved to Neo4j — no cross-article conflicts found.
                  </Typography>
                )}

                <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
                  <Typography variant="body2" color="text.secondary">
                    Mark as:
                  </Typography>
                  <Button
                    variant="outlined"
                    color="success"
                    size="small"
                    startIcon={<CheckCircleOutlined />}
                    onClick={() => handleVerdict("true")}
                    disabled={verdict !== null}
                  >
                    True
                  </Button>
                  <Button
                    variant="outlined"
                    color="error"
                    size="small"
                    startIcon={<HighlightOff />}
                    onClick={() => handleVerdict("fake")}
                    disabled={verdict !== null}
                  >
                    Fake
                  </Button>
                  {verdict && (
                    <Chip label={`Marked as ${verdict.toUpperCase()}`} color={verdict === "true" ? "success" : "error"} size="small" />
                  )}
                </Box>

                <Box>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={crossArticleLoading ? <CircularProgress size={16} /> : <CompareArrows />}
                    disabled={crossArticleLoading}
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
                          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                            {crossArticleResult.conflicts.length} conflict{crossArticleResult.conflicts.length !== 1 ? "s" : ""} found (
                            {crossArticleResult.checked_against} articles checked)
                          </Typography>
                          <Stack spacing={0.5}>
                            {crossArticleResult.conflicts.map((c, i) => (
                              <Box key={i}>
                                <Typography variant="caption" sx={{ display: "block", fontWeight: 500 }}>
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
              </SectionCard>
            )}
          </Box>
        </Box>
      )}
    </Stack>
  );
}

export default AnalyzeTab;
