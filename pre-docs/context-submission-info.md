# Knowledge Across Time: Britannica Meets Wikipedia

How has the way we describe the world changed? Build an AI pipeline that connects historical Encyclopaedia Britannica pages with their closest Wikipedia counterparts, then explores how their facts, language, and perspectives differ.

Your challenge is to find relevant matches across the two collections and build an agent that answers questions using evidence from both.

## The Challenge

### 1. Match and compare historical and modern knowledge

Select 100 pages from historical Britannica, either randomly or manually, and document your selection method.

For each page:

- Find the most similar Wikipedia article or articles.
- Explain why they are relevant matches.
- Document similarities and differences, such as vocabulary, word frequency, topic coverage, and factual claims.
- Consider how to distinguish changes in language from changes in knowledge. When a page has no clear modern counterpart, make that uncertainty visible.

### 2. Build an agent that compares the sources

Set up Hermes Agent with Nemotron 3.5 Super VL to answer questions comparing the two datasets.

Demonstrate and document:

- Three successful cases where the agent gives a useful, evidence-supported answer.
- Three clear failure cases where it retrieves the wrong material, misinterprets a source, or cannot answer reliably.
- Explain where the agent performs well, where it struggles, and what the failures reveal about your pipeline.

## Datasets

- **Historical Britannica:** National Library of Scotland — Encyclopaedia Britannica Illustrated
- **Wikipedia:** Wikimedia Foundation — Wikipedia Structured Contents

Record the dataset versions or download dates you use so that your comparisons are reproducible.

## Required Technology

Participants will be evaluated on their use of the following Nemotron models.

| Component | Required technology | Access or deployment |
| --- | --- | --- |
| Agent model | Nemotron 3.5 Super VL | Available through Nebius Token Factory |
| Document parsing | Nemotron Parse 3.0 | Organizers will provide a shared, pre-deployed endpoint |
| Embeddings | Nemotron-3-Embed-VL | Deploy on Nebius AI Cloud using the Docker image provided by organizers |
| Reranking | Nemotron 3-Rerank-VL | Deploy on Nebius AI Cloud using the Docker image provided by organizers |
| Vector database | LanceDB | Use to store and retrieve your indexed content |
| Agent framework | Hermes Agent | Configure with Nemotron 3.5 Super VL |

The challenge uses Nebius AI Cloud and Nebius Token Factory. For models unavailable through Token Factory, use the provided Docker image to simplify deployment.

## Deliverables

Submit:

- A five-minute video demonstrating your pipeline, including successful comparisons and clear failures.
- A GitHub repository containing your solution, setup instructions, sample-selection method, comparison results, and the six documented agent cases.

Make it clear how your solution uses each required model and how its answers connect to the underlying sources.

## Getting Started

Nebius AI Cloud and Nebius Token Factory require separate sign-ups. You will need two accounts.

Use the participant setup guide to get started.

## Resources

- [NVIDIA topic modeling workflow](https://build.nvidia.com/station/topic-modeling)
- [NVIDIA Nemotron 3 Embed Ranks #1 Overall on RTEB, Advancing Agentic Retrieval](https://huggingface.co/blog/nvidia/nemotron-3-embed-wins-rteb)
