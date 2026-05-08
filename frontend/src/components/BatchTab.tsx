import React, { useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Collapse,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material";
import { Add, Delete, PlayArrow } from "@mui/icons-material";
import axios from "axios";
import type { BatchArticleResult, BatchResponse, ModelsResponse } from "../types";
import { analyzeBatch } from "../api/client";
import { getModelLabel } from "../utils/modelLabels";

interface BatchTabProps {
  availableModels?: ModelsResponse;
}

interface BatchRow {
  id: number;
  text: string;
  title: string;
}

type SortField = "score" | "n_claims" | "n_inconsistencies" | "n_cross_article_inconsistencies" | "processing_time_ms";

function scoreColor(score: number): "success" | "warning" | "default" | "error" {
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  if (score >= 0.2) return "default";
  return "error";
}

const MAX_ROWS = 20;
let _rowIdCounter = 0;
function nextId(): number {
  return ++_rowIdCounter;
}

function BatchTab({ availableModels }: BatchTabProps): React.ReactElement {
  const [rows, setRows] = useState<BatchRow[]>([
    { id: nextId(), text: "", title: "" },
    { id: nextId(), text: "", title: "" },
  ]);
  const [pipeline, setPipeline] = useState<"spacy" | "llm">("spacy");
  const [model, setModel] = useState<string>("");
  const [persist, setPersist] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [result, setResult] = useState<BatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const pipelineMeta = availableModels
    ? pipeline === "llm"
      ? availableModels.llm
      : availableModels.spacy
    : null;

  const addRow = (): void => {
    if (rows.length >= MAX_ROWS) return;
    setRows((prev) => [...prev, { id: nextId(), text: "", title: "" }]);
  };

  const removeRow = (id: number): void => {
    if (rows.length <= 1) return;
    setRows((prev) => prev.filter((r) => r.id !== id));
  };

  const updateRow = (id: number, field: "text" | "title", value: string): void => {
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: value } : r))
    );
  };

  const handlePipelineChange = (e: SelectChangeEvent<string>): void => {
    const p = e.target.value as "spacy" | "llm";
    setPipeline(p);
    if (availableModels) {
      setModel(p === "llm" ? availableModels.llm.default : availableModels.spacy.default);
    }
  };

  const handleSort = (field: SortField): void => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  const validRows = rows.filter((r) => r.text.trim().length >= 20);

  const handleSubmit = async (): Promise<void> => {
    if (validRows.length === 0) return;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setExpandedId(null);

    try {
      const response = await analyzeBatch({
        articles: validRows.map((r) => ({
          text: r.text.trim(),
          title: r.title.trim() || undefined,
        })),
        pipeline,
        model: model || undefined,
        persist,
      });
      setResult(response);
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

  const sortedResults: BatchArticleResult[] = result
    ? [...result.results].sort((a, b) => {
        const aVal = a[sortField] as number;
        const bVal = b[sortField] as number;
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      })
    : [];

  return (
    <Stack spacing={3}>
      {/* Input section */}
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="subtitle2" sx={{ mb: 2 }}>
          Articles
        </Typography>

        <Stack spacing={2}>
          {rows.map((row, idx) => (
            <Box key={row.id} sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ pt: 1.5, minWidth: 20, textAlign: "right" }}
              >
                {idx + 1}
              </Typography>
              <Box sx={{ flex: 1, display: "flex", flexDirection: "column", gap: 1 }}>
                <TextField
                  size="small"
                  placeholder="Article title (optional)"
                  value={row.title}
                  onChange={(e) => updateRow(row.id, "title", e.target.value)}
                  fullWidth
                />
                <TextField
                  multiline
                  minRows={4}
                  fullWidth
                  placeholder="Paste article text here... (min 20 characters)"
                  value={row.text}
                  onChange={(e) => updateRow(row.id, "text", e.target.value)}
                  error={row.text.length > 0 && row.text.trim().length < 20}
                  helperText={row.text.length > 0 ? `${row.text.length} characters` : undefined}
                  sx={{ "& .MuiInputBase-input": { fontFamily: "IBM Plex Mono, monospace", fontSize: 13 } }}
                />
              </Box>
              <IconButton
                size="small"
                onClick={() => removeRow(row.id)}
                disabled={rows.length <= 1}
                sx={{ mt: 0.5 }}
              >
                <Delete fontSize="small" />
              </IconButton>
            </Box>
          ))}

          <Box>
            <Button
              size="small"
              startIcon={<Add />}
              onClick={addRow}
              disabled={rows.length >= MAX_ROWS}
            >
              Add Article {rows.length >= MAX_ROWS ? `(max ${MAX_ROWS})` : ""}
            </Button>
          </Box>
        </Stack>

        <Box
          sx={{
            mt: 2.5,
            pt: 2,
            borderTop: "1px solid",
            borderColor: "divider",
            display: "flex",
            gap: 2,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <FormControl size="small" sx={{ minWidth: 130 }}>
            <InputLabel>Pipeline</InputLabel>
            <Select value={pipeline} label="Pipeline" onChange={handlePipelineChange}>
              <MenuItem value="spacy">spaCy</MenuItem>
              <MenuItem value="llm">LLM</MenuItem>
            </Select>
          </FormControl>

          {pipelineMeta && (
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel>Model</InputLabel>
              <Select
                value={model || pipelineMeta.default}
                label="Model"
                onChange={(e: SelectChangeEvent<string>) => setModel(e.target.value)}
              >
                {pipelineMeta.models.map((m) => (
                  <MenuItem key={m} value={m}>
                    {getModelLabel(m)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={persist}
                onChange={(e) => setPersist(e.target.checked)}
              />
            }
            label={
              <Typography variant="body2">Save to Neo4j for cross-article analysis</Typography>
            }
          />

          <Box sx={{ ml: "auto" }}>
            <Button
              variant="contained"
              startIcon={
                isLoading ? (
                  <CircularProgress size={18} color="inherit" />
                ) : (
                  <PlayArrow />
                )
              }
              disabled={validRows.length === 0 || isLoading}
              onClick={handleSubmit}
            >
              {isLoading ? `Analyzing ${validRows.length} articles…` : "Analyze Batch"}
            </Button>
          </Box>
        </Box>
      </Paper>

      {/* Loading indicator */}
      {isLoading && (
        <Box>
          <LinearProgress />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }} component="p">
            Analyzing {validRows.length} article{validRows.length !== 1 ? "s" : ""}…
          </Typography>
        </Box>
      )}

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Results section */}
      {result && (
        <Paper variant="outlined" sx={{ p: 2.5 }}>
          {/* Aggregate stats */}
          <Box sx={{ display: "flex", gap: 3, flexWrap: "wrap", mb: 2.5 }}>
            <StatBox label="Articles" value={result.total_articles} />
            <StatBox
              label="Mean TCS"
              value={result.avg_score.toFixed(3)}
              color={
                result.avg_score >= 0.8
                  ? "success.main"
                  : result.avg_score >= 0.5
                    ? "warning.main"
                    : "error.main"
              }
            />
            <StatBox
              label="Total claims"
              value={result.results.reduce((s, r) => s + r.n_claims, 0)}
            />
            <StatBox
              label="Inconsistencies"
              value={result.results.reduce((s, r) => s + r.n_inconsistencies, 0)}
            />
            <StatBox label="Cross-article conflicts" value={result.total_cross_article_conflicts} />
            {result.persisted && (
              <Chip label="Saved to Neo4j" size="small" color="success" variant="outlined" />
            )}
          </Box>

          {/* Results table */}
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 36 }}>#</TableCell>
                <TableCell>Title</TableCell>
                <SortHeaderCell field="score" active={sortField} dir={sortDir} onSort={handleSort}>
                  TCS Score
                </SortHeaderCell>
                <SortHeaderCell field="n_claims" active={sortField} dir={sortDir} onSort={handleSort}>
                  Claims
                </SortHeaderCell>
                <SortHeaderCell field="n_inconsistencies" active={sortField} dir={sortDir} onSort={handleSort}>
                  Inconsistencies
                </SortHeaderCell>
                <SortHeaderCell
                  field="n_cross_article_inconsistencies"
                  active={sortField}
                  dir={sortDir}
                  onSort={handleSort}
                >
                  Cross-Article
                </SortHeaderCell>
                <SortHeaderCell
                  field="processing_time_ms"
                  active={sortField}
                  dir={sortDir}
                  onSort={handleSort}
                >
                  Time
                </SortHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedResults.map((row, idx) => (
                <React.Fragment key={row.article_id}>
                  <TableRow
                    hover
                    sx={{ cursor: "pointer" }}
                    onClick={() =>
                      setExpandedId((prev) =>
                        prev === row.article_id ? null : row.article_id
                      )
                    }
                  >
                    <TableCell sx={{ color: "text.secondary" }}>{idx + 1}</TableCell>
                    <TableCell sx={{ maxWidth: 220 }}>
                      <Typography variant="body2" noWrap title={row.title || row.article_id}>
                        {row.title || <em style={{ opacity: 0.6 }}>Untitled</em>}
                      </Typography>
                      {row.error && (
                        <Typography variant="caption" color="error">
                          Error
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={row.score.toFixed(3)}
                        size="small"
                        color={scoreColor(row.score)}
                      />
                    </TableCell>
                    <TableCell>{row.n_claims}</TableCell>
                    <TableCell>{row.n_inconsistencies}</TableCell>
                    <TableCell>
                      {row.n_cross_article_inconsistencies > 0 ? (
                        <Chip
                          label={row.n_cross_article_inconsistencies}
                          size="small"
                          color="warning"
                        />
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          0
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {Math.round(row.processing_time_ms)}ms
                      </Typography>
                    </TableCell>
                  </TableRow>

                  {/* Expandable detail row */}
                  <TableRow>
                    <TableCell colSpan={7} sx={{ p: 0, border: 0 }}>
                      <Collapse in={expandedId === row.article_id} unmountOnExit>
                        <Box sx={{ px: 3, py: 1.5, bgcolor: "action.hover" }}>
                          <Typography variant="body2" sx={{ mb: 1 }}>
                            {row.summary}
                          </Typography>
                          {row.cross_article_conflicts.length > 0 && (
                            <Stack spacing={0.5}>
                              <Typography variant="caption" color="text.secondary">
                                Cross-article conflicts:
                              </Typography>
                              {row.cross_article_conflicts.map((c, i) => (
                                <Typography key={i} variant="caption" color="warning.main">
                                  • {c.description}
                                </Typography>
                              ))}
                            </Stack>
                          )}
                          {row.error && (
                            <Typography variant="caption" color="error">
                              {row.error}
                            </Typography>
                          )}
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Stack>
  );
}

// Stat summary box used in aggregate row
function StatBox({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color?: string;
}): React.ReactElement {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        {label}
      </Typography>
      <Typography variant="h6" sx={{ color: color ?? "text.primary", lineHeight: 1.2 }}>
        {value}
      </Typography>
    </Box>
  );
}

// Sortable table header cell
function SortHeaderCell({
  field,
  active,
  dir,
  onSort,
  children,
}: {
  field: SortField;
  active: SortField;
  dir: "asc" | "desc";
  onSort: (f: SortField) => void;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <TableCell>
      <TableSortLabel
        active={active === field}
        direction={active === field ? dir : "asc"}
        onClick={() => onSort(field)}
      >
        {children}
      </TableSortLabel>
    </TableCell>
  );
}

export default BatchTab;
