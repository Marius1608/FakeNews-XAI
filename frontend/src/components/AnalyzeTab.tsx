import React, { useEffect, useState } from "react";
import { Alert, Stack } from "@mui/material";
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
      const result = await analyzeArticle(request);
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

  return (
    <Stack spacing={3}>
      <ArticleInput
        onSubmit={handleSubmit}
        isLoading={isLoading}
        showPipelineSelector={true}
        availableModels={availableModels}
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
            processingTimeMs={analyzeResult.processing_time_ms}
          />
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
