import React, { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material";
import { CompareArrows } from "@mui/icons-material";
import axios from "axios";
import type { AnalyzeRequest, CompareRequest, CompareResponse, ModelsResponse } from "../types";
import { comparePipelines, getModels } from "../api/client";
import ArticleInput from "./ArticleInput";
import TCSScoreDisplay from "./TCSScoreDisplay";
import TextHighlight from "./TextHighlight";
import InconsistencyList from "./InconsistencyList";
import Timeline from "./Timeline";
import { getModelLabel } from "../utils/modelLabels";

type ArticleContent = Omit<AnalyzeRequest, "pipeline" | "model">;

function getPipelineMeta(
  m: ModelsResponse,
  pipeline: string,
): { default: string; models: string[] } {
  return pipeline === "llm" ? m.llm : m.spacy;
}

const PIPELINE_OPTIONS = [
  { value: "spacy", label: "spaCy (deterministic)" },
  { value: "llm", label: "LLM (Ollama)" },
];

function CompareTab(): React.ReactElement {
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [pipelineA, setPipelineA] = useState<string>("spacy");
  const [modelA, setModelA] = useState<string>("");
  const [pipelineB, setPipelineB] = useState<string>("llm");
  const [modelB, setModelB] = useState<string>("");
  const [articleContent, setArticleContent] = useState<ArticleContent>({ text: "" });
  const [articleText, setArticleText] = useState<string>("");
  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getModels()
      .then((m) => {
        setModels(m);
        setModelA(m.spacy.default);
        setModelB(m.llm.default);
      })
      .catch(() => undefined);
  }, []);

  const handlePipelineAChange = (e: SelectChangeEvent<string>): void => {
    const p = e.target.value;
    setPipelineA(p);
    if (models) setModelA(getPipelineMeta(models, p).default);
  };

  const handlePipelineBChange = (e: SelectChangeEvent<string>): void => {
    const p = e.target.value;
    setPipelineB(p);
    if (models) setModelB(getPipelineMeta(models, p).default);
  };

  const handleCompare = async (): Promise<void> => {
    if (!articleContent.text) return;
    setIsLoading(true);
    setError(null);
    setArticleText(articleContent.text);
    const req: CompareRequest = {
      text: articleContent.text,
      title: articleContent.title,
      publication_date: articleContent.publication_date,
      source: articleContent.source,
      pipeline_a: pipelineA,
      model_a: modelA || undefined,
      pipeline_b: pipelineB,
      model_b: modelB || undefined,
    };
    try {
      const result = await comparePipelines(req);
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
      <ArticleInput
        isLoading={isLoading}
        showPipelineSelector={false}
        hideSubmitButton={true}
        onRequestChange={(content) => setArticleContent(content)}
      />

      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="subtitle2" sx={{ mb: 2 }}>
          Model Selection
        </Typography>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Stack spacing={2}>
              <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500 }}>
                Model A
              </Typography>
              <FormControl size="small" fullWidth>
                <InputLabel>Pipeline</InputLabel>
                <Select value={pipelineA} label="Pipeline" onChange={handlePipelineAChange}>
                  {PIPELINE_OPTIONS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              {models && (
                <FormControl size="small" fullWidth>
                  <InputLabel>Model</InputLabel>
                  <Select
                    value={modelA}
                    label="Model"
                    onChange={(e: SelectChangeEvent<string>) => setModelA(e.target.value)}
                  >
                    {getPipelineMeta(models, pipelineA).models.map((m) => (
                      <MenuItem key={m} value={m}>
                        {getModelLabel(m)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              )}
              {modelA && (
                <Typography variant="caption" color="text.secondary">
                  {pipelineA}:{modelA}
                </Typography>
              )}
            </Stack>
          </Grid>

          <Grid size={{ xs: 12, md: 6 }}>
            <Stack spacing={2}>
              <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500 }}>
                Model B
              </Typography>
              <FormControl size="small" fullWidth>
                <InputLabel>Pipeline</InputLabel>
                <Select value={pipelineB} label="Pipeline" onChange={handlePipelineBChange}>
                  {PIPELINE_OPTIONS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              {models && (
                <FormControl size="small" fullWidth>
                  <InputLabel>Model</InputLabel>
                  <Select
                    value={modelB}
                    label="Model"
                    onChange={(e: SelectChangeEvent<string>) => setModelB(e.target.value)}
                  >
                    {getPipelineMeta(models, pipelineB).models.map((m) => (
                      <MenuItem key={m} value={m}>
                        {getModelLabel(m)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              )}
              {modelB && (
                <Typography variant="caption" color="text.secondary">
                  {pipelineB}:{modelB}
                </Typography>
              )}
            </Stack>
          </Grid>
        </Grid>
      </Paper>

      <Box>
        <Button
          variant="contained"
          color="primary"
          startIcon={
            isLoading ? (
              <CircularProgress size={20} color="inherit" />
            ) : (
              <CompareArrows />
            )
          }
          disabled={articleContent.text.length < 20 || isLoading}
          onClick={handleCompare}
        >
          {isLoading ? "Comparing..." : "Compare"}
        </Button>
      </Box>

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {compareResult && (
        <>
          <Paper sx={{ p: 2 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5, flexWrap: "wrap" }}>
              <Typography variant="body2">
                Model A: <strong>{compareResult.pipeline_a.pipeline}:{compareResult.model_a}</strong>
              </Typography>
              <Typography variant="body2" color="text.secondary">
                vs
              </Typography>
              <Typography variant="body2">
                Model B: <strong>{compareResult.pipeline_b.pipeline}:{compareResult.model_b}</strong>
              </Typography>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1 }}>
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
              Model A: {Math.round(compareResult.pipeline_a.processing_time_ms)}ms | Model B:{" "}
              {Math.round(compareResult.pipeline_b.processing_time_ms)}ms
            </Typography>
          </Paper>

          <Grid container spacing={3}>
            <Grid size={{ xs: 12, md: 6 }}>
              <Stack spacing={3}>
                <Typography variant="h6">
                  Model A — {compareResult.pipeline_a.pipeline}:{compareResult.model_a}
                </Typography>
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
                <Typography variant="h6">
                  Model B — {compareResult.pipeline_b.pipeline}:{compareResult.model_b}
                </Typography>
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
