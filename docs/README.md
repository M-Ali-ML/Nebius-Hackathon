# Docs

The app is the Hugging Face Space: https://huggingface.co/spaces/nebius-build-week/britannica-across-time

Each file below is one part of the project.

| Part | File |
| --- | --- |
| Results of the saved run | [results.md](results.md) |
| Install and run the pipeline | [setup.md](setup.md) |
| Atlas method | [atlas.md](atlas.md) |
| Agent debate | [debate.md](debate.md) |
| Six agent cases | [cases/README.md](cases/README.md) |
| Retrieval ablation | [retrieval-ablation.md](retrieval-ablation.md) |
| Topic clusters | [topics.md](topics.md) |
| Why a page has no match | [uncertainty.md](uncertainty.md) |
| Hermes agent | [hermes.md](hermes.md) |
| APIs, models, packages | [technical.md](technical.md) |
| Embed and rerank service | [model-service.md](model-service.md) |
| Wikipedia API | [wikipedia-api.md](wikipedia-api.md) |
| Limits | [limits.md](limits.md) |
| Demo commands | [demo-commands.md](demo-commands.md) |
| Video script | [video-script.md](video-script.md) |
| Challenge | [challenge.md](challenge.md) |
| Milestones | [milestones.md](milestones.md) |
| Hugging Face Space card | [hf/space_card.md](hf/space_card.md) |
| Hugging Face dataset card | [hf/dataset_card.md](hf/dataset_card.md) |

## Who runs what

![Who runs what](diagrams/who-runs-what.svg)

The step map and the Hermes map are on [site/how.html](../site/how.html).

The saved run is already in this checkout: `site/`, `artifacts/`, `docs/cases/`, and `runs/agent/`. You can read it before you call a model. A full rerun is in [setup.md](setup.md).

## Repository

| Path | Content |
| --- | --- |
| `src/nemotron_challenge/` | Pipeline |
| `integrations/hermes/` | Plugin and skill |
| `artifacts/` | Raw Parse output, entries, scores, matches, comparisons, LaTeX |
| `site/` | Static archive, including `atlas.html` and `debate.html` |
| `docs/diagrams/` | The three maps |
| `docs/cases/` | Six case studies |
| `artifacts/atlas/` | Atlas vectors, points, and summary |
| `artifacts/debate/` | Debate transcripts |
| `runs/` | Transcripts, smoke receipt, evaluation record |
