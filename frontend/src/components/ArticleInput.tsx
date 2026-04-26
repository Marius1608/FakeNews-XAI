import React, { useRef, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  FormLabel,
  Radio,
  RadioGroup,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { Clear, ExpandMore, PlayArrow, Upload } from "@mui/icons-material";
import type { AnalyzeRequest } from "../types";

interface ArticleInputProps {
  onSubmit: (request: AnalyzeRequest) => void;
  isLoading: boolean;
  showPipelineSelector?: boolean;
}

function ArticleInput({
  onSubmit,
  isLoading,
  showPipelineSelector = true,
}: ArticleInputProps): React.ReactElement {
  const [inputMode, setInputMode] = useState<"text" | "file" | "url">("text");
  const [textValue, setTextValue] = useState<string>("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [title, setTitle] = useState<string>("");
  const [publicationDate, setPublicationDate] = useState<string>("");
  const [source, setSource] = useState<string>("");
  const [pipeline, setPipeline] = useState<"spacy" | "llm">("spacy");

  const fileInputRef = useRef<HTMLInputElement>(null);

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
    const request: AnalyzeRequest = {
      text: textValue,
      title: title || undefined,
      publication_date: publicationDate || null,
      source: source || undefined,
      pipeline: showPipelineSelector ? pipeline : undefined,
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
              label="Pipeline A — spaCy (deterministic)"
            />
            <FormControlLabel
              value="llm"
              control={<Radio size="small" />}
              label="Pipeline B — LLM (Ollama/Llama 3)"
            />
          </RadioGroup>
        </FormControl>
      )}

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
    </Box>
  );
}

export default ArticleInput;
