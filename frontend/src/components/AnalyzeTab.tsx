import React, { useEffect, useState } from "react";
import { Alert, Box, Checkbox, Chip, FormControlLabel, Stack, Typography } from "@mui/material";
import axios from "axios";
import type { AnalyzeRequest, AnalyzeResponse, ModelsResponse } from "../types";
import { analyzeArticle, getModels } from "../api/client";
import ArticleInput from "./ArticleInput";
import TCSScoreDisplay from "./TCSScoreDisplay";
import TextHighlight from "./TextHighlight";
import InconsistencyList from "./InconsistencyList";
import Timeline from "./Timeline";
import TemporalGraph from "./TemporalGraph";

function AnalyzeTab(): React.ReactElement {
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResponse | null>(null);
  const [articleText, setArticleText] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelsResponse | undefined>(undefined);
  const [persist, setPersist] = useState<boolean>(false);

  useEffect(() => {
    getModels()
      .then(setAvailableModels)
      .catch(() => undefined);
  }, []);

  const handleSubmit = async (request: AnalyzeRequest): Promise<void> => {
    setIsLoading(true);
    setError(null);
    setArticleText(request.text);
    try {
      const result = await analyzeArticle({ ...request, persist });
      setAnalyzeResult(result);
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

  return (
    <Stack spacing={3}>
      <ArticleInput
        onSubmit={handleSubmit}
        isLoading={isLoading}
        showPipelineSelector={true}
        availableModels={availableModels}
      />

      <FormControlLabel
        sx={{ mt: -1 }}
        control={
          <Checkbox
            size="small"
            checked={persist}
            onChange={(e) => setPersist(e.target.checked)}
          />
        }
        label={
          <Typography variant="body2">
            Save to Neo4j for cross-article analysis
          </Typography>
        }
      />

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
                {analyzeResult.article_id && (
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                    Saved as {analyzeResult.article_id}
                  </Typography>
                )}
              </Box>
            </Alert>
          )}

          {/* Saved without conflicts */}
          {analyzeResult.article_id && crossArticleConflicts.length === 0 && (
            <Alert severity="success" sx={{ py: 0.5 }}>
              Saved to Neo4j — no cross-article conflicts found.
            </Alert>
          )}

          <TextHighlight
            text={articleText}
            annotations={analyzeResult.fact_annotations}
          />
          <InconsistencyList inconsistencies={analyzeResult.inconsistency_details} />
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
