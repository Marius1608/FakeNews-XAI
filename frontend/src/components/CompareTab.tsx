import React, { useState } from "react";
import { Alert, Box, Chip, Grid, Paper, Stack, Typography } from "@mui/material";
import axios from "axios";
import type { AnalyzeRequest, CompareRequest, CompareResponse } from "../types";
import { comparePipelines } from "../api/client";
import ArticleInput from "./ArticleInput";
import TCSScoreDisplay from "./TCSScoreDisplay";
import TextHighlight from "./TextHighlight";
import InconsistencyList from "./InconsistencyList";
import Timeline from "./Timeline";

function CompareTab(): React.ReactElement {
  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);
  const [articleText, setArticleText] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // ArticleInput always calls onSubmit with AnalyzeRequest; extract CompareRequest fields here
  const handleSubmit = async (request: AnalyzeRequest): Promise<void> => {
    setIsLoading(true);
    setError(null);
    setArticleText(request.text);
    const compareReq: CompareRequest = {
      text: request.text,
      title: request.title,
      publication_date: request.publication_date,
      source: request.source,
    };
    try {
      const result = await comparePipelines(compareReq);
      setCompareResult(result);
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

  const deltaAbs = compareResult ? Math.abs(compareResult.score_delta) : 0;

  return (
    <Stack spacing={3}>
      <ArticleInput onSubmit={handleSubmit} isLoading={isLoading} showPipelineSelector={false} />

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {compareResult && (
        <>
          <Paper sx={{ p: 2 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1, flexWrap: "wrap" }}>
              <Typography variant="body1">Score Delta:</Typography>
              <Chip
                label={deltaAbs.toFixed(3)}
                color={deltaAbs < 0.05 ? "success" : deltaAbs < 0.15 ? "warning" : "error"}
                size="small"
              />
            </Box>
            <Typography variant="body2" sx={{ mb: 0.75 }}>
              Agreement: {compareResult.agreement}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              spaCy: {Math.round(compareResult.pipeline_a.processing_time_ms)}ms | LLM:{" "}
              {Math.round(compareResult.pipeline_b.processing_time_ms)}ms
            </Typography>
          </Paper>

          <Grid container spacing={3}>
            <Grid size={{ xs: 12, md: 6 }}>
              <Stack spacing={3}>
                <Typography variant="h6">Pipeline A — spaCy</Typography>
                <TCSScoreDisplay
                  score={compareResult.pipeline_a.score}
                  label={compareResult.pipeline_a.label}
                  summary={compareResult.pipeline_a.summary}
                  nClaims={compareResult.pipeline_a.n_claims}
                  nInconsistencies={compareResult.pipeline_a.n_inconsistencies}
                  coherenceFactor={compareResult.pipeline_a.coherence_factor}
                  pipeline={compareResult.pipeline_a.pipeline}
                  processingTimeMs={compareResult.pipeline_a.processing_time_ms}
                />
                <TextHighlight
                  text={articleText}
                  annotations={compareResult.pipeline_a.fact_annotations}
                />
                <InconsistencyList
                  inconsistencies={compareResult.pipeline_a.inconsistency_details}
                />
                <Timeline
                  timeline={compareResult.pipeline_a.timeline}
                  annotations={compareResult.pipeline_a.fact_annotations}
                />
              </Stack>
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <Stack spacing={3}>
                <Typography variant="h6">Pipeline B — LLM</Typography>
                <TCSScoreDisplay
                  score={compareResult.pipeline_b.score}
                  label={compareResult.pipeline_b.label}
                  summary={compareResult.pipeline_b.summary}
                  nClaims={compareResult.pipeline_b.n_claims}
                  nInconsistencies={compareResult.pipeline_b.n_inconsistencies}
                  coherenceFactor={compareResult.pipeline_b.coherence_factor}
                  pipeline={compareResult.pipeline_b.pipeline}
                  processingTimeMs={compareResult.pipeline_b.processing_time_ms}
                />
                <TextHighlight
                  text={articleText}
                  annotations={compareResult.pipeline_b.fact_annotations}
                />
                <InconsistencyList
                  inconsistencies={compareResult.pipeline_b.inconsistency_details}
                />
                <Timeline
                  timeline={compareResult.pipeline_b.timeline}
                  annotations={compareResult.pipeline_b.fact_annotations}
                />
              </Stack>
            </Grid>
          </Grid>
        </>
      )}
    </Stack>
  );
}

export default CompareTab;
