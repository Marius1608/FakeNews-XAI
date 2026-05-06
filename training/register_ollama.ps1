# Register the fine-tuned fakenews-ner model in Ollama using the local Modelfile.
# Run from the repo root or the training/ directory.

Set-Location $PSScriptRoot

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: 'ollama' not found. Install Ollama from https://ollama.com and try again."
    exit 1
}

if (-not (Test-Path "output\fakenews-ner.gguf")) {
    Write-Error "ERROR: output\fakenews-ner.gguf not found."
    Write-Host "Run export_gguf.py first to generate the GGUF file."
    exit 1
}

Write-Host "Registering model 'fakenews-ner' in Ollama..."
ollama create fakenews-ner -f Modelfile

Write-Host ""
Write-Host "Done. Test the model with:"
Write-Host "  ollama run fakenews-ner 'Extract temporal facts from: Obama was president from 2009 to 2017.'"
