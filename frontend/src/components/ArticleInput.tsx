import React, { useEffect, useRef, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  FormHelperText,
  FormLabel,
  InputLabel,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material";
import { Clear, ExpandMore, PlayArrow, Upload } from "@mui/icons-material";
import type { AnalyzeRequest, ModelsResponse } from "../types";
import { getModelDescription, getModelLabel } from "../utils/modelLabels";

// Fields that ArticleInput owns (text, metadata — no pipeline/model)
type ArticleFields = Omit<AnalyzeRequest, "pipeline" | "model">;

interface ArticleInputProps {
  onSubmit?: (request: AnalyzeRequest) => void;
  isLoading: boolean;
  showPipelineSelector?: boolean;
  availableModels?: ModelsResponse;
  // When true, hide the submit button (CompareTab renders its own button)
  hideSubmitButton?: boolean;
  // Fires on every text/metadata change so parent can track current content
  onRequestChange?: (request: ArticleFields) => void;
}

function ArticleInput({
  onSubmit,
  isLoading,
  showPipelineSelector = true,
  availableModels,
  hideSubmitButton = false,
  onRequestChange,
}: ArticleInputProps): React.ReactElement {
  const [inputMode, setInputMode] = useState<"text" | "file" | "url">("text");
  const [textValue, setTextValue] = useState<string>("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [title, setTitle] = useState<string>("");
  const [publicationDate, setPublicationDate] = useState<string>("");
  const [source, setSource] = useState<string>("");
  const [pipeline, setPipeline] = useState<"spacy" | "llm">("spacy");
  const [model, setModel] = useState<string>("");

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync model default when pipeline changes or availableModels first loads
  useEffect(() => {
    if (availableModels) {
      setModel(availableModels[pipeline].default);
    }
  }, [availableModels, pipeline]);

  // Notify parent whenever article content changes (used by CompareTab)
  const onRequestChangeRef = useRef(onRequestChange);
  onRequestChangeRef.current = onRequestChange;

  useEffect(() => {
    onRequestChangeRef.current?.({
      text: textValue,
      title: title || undefined,
      publication_date: publicationDate || null,
      source: source || undefined,
    });
  }, [textValue, title, publicationDate, source]);

  const handleModeChange = (
    _: React.MouseEvent<HTMLElement>,
    newMode: string | null,
  ): void => {
    if (newMode !== null) {
      setInputMode(newMode as "text" | "file" | "url");
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event): void => {
      const content = event.target?.result as string;
      if (file.name.endsWith(".json")) {
        try {
          const parsed = JSON.parse(content) as Record<string, unknown>;
          if (typeof parsed.text === "string") setTextValue(parsed.text);
          if (typeof parsed.title === "string") setTitle(parsed.title);
          if (typeof parsed.source === "string") setSource(parsed.source);
          if (typeof parsed.publication_date === "string")
            setPublicationDate(parsed.publication_date);
        } catch {
          setTextValue(content);
        }
      } else {
        setTextValue(content);
      }
    };
    reader.readAsText(file);
  };

  const handleClearFile = (): void => {
    setFileName(null);
    setTextValue("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSubmit = (): void => {
    if (!onSubmit) return;
    const request: AnalyzeRequest = {
      text: textValue,
      title: title || undefined,
      publication_date: publicationDate || null,
      source: source || undefined,
      pipeline: showPipelineSelector ? pipeline : undefined,
      model: showPipelineSelector && model ? model : undefined,
    };
    onSubmit(request);
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <ToggleButtonGroup
        value={inputMode}
        exclusive
        onChange={handleModeChange}
        size="small"
      >
        <ToggleButton value="text">Paste Text</ToggleButton>
        <ToggleButton value="file">Upload File</ToggleButton>
        <ToggleButton value="url">URL</ToggleButton>
      </ToggleButtonGroup>

      {inputMode === "text" && (
        <Box>
          <TextField
            multiline
            minRows={8}
            fullWidth
            placeholder="Paste article text here..."
            value={textValue}
            onChange={(e) => setTextValue(e.target.value)}
            sx={{ "& .MuiInputBase-input": { fontFamily: "IBM Plex Mono, monospace" } }}
          />
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ mt: 0.5, display: "block" }}
          >
            {textValue.length} characters
          </Typography>
        </Box>
      )}

      {inputMode === "file" && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <input
            type="file"
            accept=".txt,.json"
            ref={fileInputRef}
            onChange={handleFileChange}
            style={{ display: "none" }}
          />
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Button
              variant="outlined"
              startIcon={<Upload />}
              onClick={() => fileInputRef.current?.click()}
            >
              Choose File
            </Button>
            {fileName && (
              <>
                <Typography variant="body2" sx={{ flex: 1 }}>
                  {fileName}
                </Typography>
                <Button
                  size="small"
                  color="inherit"
                  startIcon={<Clear />}
                  onClick={handleClearFile}
                >
                  Clear
                </Button>
              </>
            )}
          </Box>
          {textValue && (
            <Typography variant="caption" color="text.secondary">
              {textValue.length} characters loaded
            </Typography>
          )}
        </Box>
      )}

      {inputMode === "url" && (
        <TextField
          fullWidth
          disabled
          placeholder="https://..."
          helperText="Coming soon — requires RSS/API integration"
        />
      )}

      <Accordion
        disableGutters
        elevation={0}
        sx={{
          "&:before": { display: "none" },
          border: "1px solid rgba(148,163,184,0.15)",
          borderRadius: 1,
        }}
      >
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="body2">Article Metadata</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <TextField
              label="Title"
              fullWidth
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              size="small"
            />
            <TextField
              label="Publication Date"
              type="date"
              fullWidth
              value={publicationDate}
              onChange={(e) => setPublicationDate(e.target.value)}
              size="small"
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Source"
              fullWidth
              value={source}
              onChange={(e) => setSource(e.target.value)}
              size="small"
            />
          </Box>
        </AccordionDetails>
      </Accordion>

      {showPipelineSelector && (
        <>
          <FormControl>
            <FormLabel>Pipeline</FormLabel>
            <RadioGroup
              value={pipeline}
              onChange={(e) => setPipeline(e.target.value as "spacy" | "llm")}
              row
            >
              <FormControlLabel
                value="spacy"
                control={<Radio size="small" />}
                label="Pipeline A — spaCy"
              />
              <FormControlLabel
                value="llm"
                control={<Radio size="small" />}
                label="Pipeline B — LLM"
              />
            </RadioGroup>
          </FormControl>

          {availableModels && (
            <FormControl size="small" sx={{ maxWidth: 360 }}>
              <InputLabel>Model</InputLabel>
              <Select
                value={model}
                label="Model"
                onChange={(e: SelectChangeEvent<string>) => setModel(e.target.value)}
              >
                {availableModels[pipeline].models.map((m) => (
                  <MenuItem key={m} value={m}>
                    {getModelLabel(m)}
                  </MenuItem>
                ))}
              </Select>
              {model && (
                <FormHelperText>{getModelDescription(model)}</FormHelperText>
              )}
            </FormControl>
          )}
        </>
      )}

      {!hideSubmitButton && (
        <Box>
          <Button
            variant="contained"
            color="primary"
            startIcon={
              isLoading ? (
                <CircularProgress size={20} color="inherit" />
              ) : (
                <PlayArrow />
              )
            }
            disabled={textValue.length < 20 || isLoading}
            onClick={handleSubmit}
          >
            {isLoading ? "Analyzing..." : "Analyze"}
          </Button>
        </Box>
      )}
    </Box>
  );
}

export default ArticleInput;
