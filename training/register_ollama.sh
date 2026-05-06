#!/bin/bash
# Register the fine-tuned fakenews-ner model in Ollama using the local Modelfile.
# Run from the repo root or the training/ directory — the script locates itself.

cd "$(dirname "$0")"

if ! command -v ollama &>/dev/null; then
    echo "ERROR: 'ollama' not found. Install Ollama from https://ollama.com and try again."
    exit 1
fi

if [ ! -f "output/fakenews-ner.gguf" ]; then
    echo "ERROR: output/fakenews-ner.gguf not found."
    echo "Run export_gguf.py first to generate the GGUF file."
    exit 1
fi

echo "Registering model 'fakenews-ner' in Ollama..."
ollama create fakenews-ner -f Modelfile

echo ""
echo "Done. Test the model with:"
echo "  ollama run fakenews-ner 'Extract temporal facts from: Obama was president from 2009 to 2017.'"
