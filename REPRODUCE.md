# How to reproduce

Python 3.11+ and a running [Ollama](https://ollama.com/) instance. The working environment used Python 3.12. The 12-case evaluation also needs the three pulled models below; the unit tests do not.

## 1. Install

```bash
git clone https://github.com/TheMisterPin/warehouse-investigator.git
cd warehouse-investigator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

`requirements.txt` pins `chromadb` and `pytest`. `pip install -e .` registers the `investigate`, `evaluate`, and `feedback` commands from this tree.

## 2. Pull models and seed the warehouse

Start Ollama if it is not already running (`ollama serve`, or the Ollama app). Then:

```bash
ollama pull nomic-embed-text
ollama pull qwen3:8b
ollama pull qwen3.5:27b
python -m warehouse_investigator.seed
```

Seed rebuilds `warehouse.db` and `chroma/` at the project root from `src/warehouse_investigator/data/warehouse/*.json`. Embeddings go through Ollama (`nomic-embed-text`). Evaluation labels in `src/warehouse_investigator/data/evaluation/` are never written to either store.

If those files are missing, the first SQLite lookup seeds the database and the first `search_records` call builds the Chroma index. Running seed up front avoids that happening mid-investigation.

`qwen3.5:27b` is large. Automatic routing still starts on `qwen3:8b` and only sends uncertain, conflicting, or high-risk cases to 27B. Leave `--workers` at 1 (the default) if one GPU is serving both models.

## 3. Check the offline tests

```bash
pytest
```

These tests stub embeddings and write a temporary warehouse. They do not call Ollama.

## 4. Run one investigation

```bash
investigate INC-001
```

Or without the installed command:

```bash
PYTHONPATH=src python -m warehouse_investigator INC-001
```

By default the CLI prints a short incident note. Pass `--format json` for the full run record, or more than one ticket ID for a queue summary. Each run writes a trajectory under `trajectories/` unless you pass `--no-log`.

```bash
investigate INC-001 INC-002 INC-003
investigate INC-001 --format json
investigate INC-001 --model qwen3:8b
investigate INC-001 --primary-model qwen3:8b --deep-model qwen3.5:27b
investigate INC-001 --host http://localhost:11434
```

## 5. Run the 12-case evaluation

```bash
evaluate --runs 1
```

This writes a JSON report under `reports/` and per-run trajectories under `trajectories/evaluation/`. A run passes only when ticket ID, root-cause code, required and forbidden evidence, recommended-action relevance and safety, confidence, and escalation all match the case definition.

Targeted reruns:

```bash
evaluate --case INC-012
evaluate --model qwen3.5:27b --case INC-012
evaluate --workers 2
evaluate --compare-to reports/<previous-report>.json
```

Chat calls use temperature 0, but live scores can still move with Ollama version, GPU load, and model quantization. Compare against a previous report with `--compare-to` rather than treating any single pass rate as a fixed baseline.

## Environment overrides

| Variable | Default | Role |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://localhost:11434` | Chat and embed endpoint |
| `OLLAMA_MODEL` | `qwen3:8b` | Fixed-model path when routing is off |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Chroma embeddings |
| `WAREHOUSE_PRIMARY_MODEL` | `qwen3:8b` | Automatic-routing primary |
| `WAREHOUSE_DEEP_MODEL` | `qwen3.5:27b` | Automatic-routing review tier |

`--host`, `--model`, `--primary-model`, and `--deep-model` on the CLIs override the matching variables.
