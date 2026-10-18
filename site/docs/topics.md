# Shared Topic Space and Nemotron 3.5 Super VL Refinement

This report describes our BERTopic-style topic modeling pipeline across historical *Encyclopaedia Britannica* entries (1771-1797) and matched modern Wikipedia articles. We implement all six layers of the organizer's *BERTopic with Nemotron* architecture, including the optional `nvidia/Nemotron-3.5-Super-VL` topic-refinement stage via Nebius Token Factory.

## Files

- Module: [`src/nemotron_challenge/topics.py`](file:///Users/aly/repos/Nebius-Hackathon/src/nemotron_challenge/topics.py)
- Structured output: [`artifacts/compare/topics.json`](file:///Users/aly/repos/Nebius-Hackathon/artifacts/compare/topics.json)
- Raw model reply: [`artifacts/compare/raw_topics_super.json`](file:///Users/aly/repos/Nebius-Hackathon/artifacts/compare/raw_topics_super.json)
- Shared-space figure: [`artifacts/compare/shared_space_umap.png`](file:///Users/aly/repos/Nebius-Hackathon/artifacts/compare/shared_space_umap.png)

## Pipeline stages

1. **Nemotron Embeddings (`nvidia/llama-nemotron-embed-vl-1b-v2`)**:
   - We load 259 Britannica entry embeddings (2,048 dimensions) from the `entries` table in `data/team.lancedb`.
   - For the 90 distinct matched Wikipedia articles in `wiki_chunks`, we compute a token-weighted mean over each article's chunk vectors (1,054 chunks total) and L2-normalize the resulting vector (`chunk -> token-weighted mean -> normalize`).
2. **Cosine manifold reduction (`2,048 -> 5D -> 2D`, seed `20261018`)**:
   - We subtract each corpus mean vector before L2 normalization so 18th-century OCR typography and modern Wikipedia syntax share a common origin while preserving directional cosine similarity.
   - We build a locally scaled cosine $k$-NN affinity graph ($k = 12$) reinforced by verified matched pairs, compute the normalized graph Laplacian eigendecomposition (`5D` spectral embedding for clustering), and refine a `2D` neighborhood-preserving layout with attractive and repulsive force-directed steps.
3. **Density-aware clustering and outlier retention**:
   - Documents in the bottom 8% of local 5-neighbor cosine density, bare plate captions, and short cross-references without matches remain in the `Unassigned / outlier` group (`cluster_id = -1`, 53 documents).
   - We group the remaining 296 documents into 14 topic clusters using cosine minimum-variance agglomerative clustering. Across the 91 matched entry-article pairs in the index, 69 pairs (75.8%) land in the exact same topic cluster.
4. **CountVectorizer and class-based TF-IDF (`c-TF-IDF`)**:
   - We extract English content 1-grams and 2-grams (stopwords removed, long `ſ` folded to `s`, up to 20,000 features with minimum document frequency 2).
   - We cap per-document term counts at 12 so multi-section Wikipedia articles do not drown short Britannica definitions, then score each term in cluster $c$ by $\text{TF}_{t,c} \cdot \log(1 + A / \text{TF}_{t,\text{all}})$.
5. **Nemotron 3.5 Super VL topic refinement (`nvidia/Nemotron-3.5-Super-VL`)**:
   - We send each cluster's top 8 `c-TF-IDF` terms, sample Britannica headwords, and sample Wikipedia titles to `nvidia/Nemotron-3.5-Super-VL` through `SuperClient` with thinking disabled (`enable_thinking: False`).
   - The model returns a 3 to 6 word noun-phrase `super_label` and a 1 to 2 sentence `super_summary` explaining what the topic covers across both encyclopaedias. We store the unmodified response in `artifacts/compare/raw_topics_super.json`.

## Topic clusters

| Cluster | Short tag (`c-TF-IDF` top 3) | Super VL label | Britannica | Wikipedia | Matched pairs | Super VL summary |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `00` | `00 · town · local · city` | Local Towns and Districts | 33 | 9 | 13 | This cluster covers geographic locations and settlements in historical and modern sources. It includes towns, cities, districts, and universities built near rivers. |
| `01` | `01 · point · water · air` | Optics and Geometric Measurement | 26 | 12 | 14 | This cluster examines light, angles, and surfaces in physical science. It connects historical studies of optics and trigonometry with modern articles on measurement and carpentry. |
| `02` | `02 · greek · ancient · lyre` | Ancient Greek Mythology and Culture | 20 | 10 | 15 | This cluster explores figures and concepts from ancient Greece. It includes gods, mythological characters, and terms related to Hellenistic history. |
| `03` | `03 · species · genus · museum` | Natural History and Entomology | 19 | 7 | 7 | This cluster focuses on biological classification and natural specimens. It covers species, genera, insects, and plants found in museums and across Europe. |
| `04` | `04 · cable · engine · coin` | Mechanical Engines and Coinage | 14 | 9 | 9 | This cluster discusses mechanical devices and currency systems. It includes engines, cables, anchors, and the process of coining money. |
| `05` | `05 · military · life · literature` | Military History and Literature | 15 | 7 | 8 | This cluster covers warfare, literary traditions, and historical periods. It connects Roman and medieval history with studies of oratory and philology. |
| `06` | `06 · empire · city · egypt` | Ancient Empires and Kingdoms | 12 | 8 | 10 | This cluster examines historical states and civilizations across Asia and Europe. It includes Egypt, India, Thrace, and Byzantium. |
| `07` | `07 · died · london · published` | Historical Figures and Publications | 11 | 8 | 8 | This cluster profiles notable English scholars and their works. It includes biographical details of individuals who lived in London and Oxford. |
| `08` | `08 · body · beautiful · beauty` | Physical Exercise and Beauty | 12 | 4 | 4 | This cluster addresses physical activity and aesthetic qualities. It covers exercise, the human body, and concepts of beauty in objects. |
| `09` | `09 · william · king · england` | English Royalty and History | 14 | 2 | 2 | This cluster focuses on monarchs and historical events in England. It includes figures such as William, Elizabeth, and Mary. |
| `10` | `10 · law · act · person` | Legal Rights and Political Economy | 11 | 5 | 7 | This cluster explores laws, property, and governmental power. It covers legal acts, liberties, and economic theories. |
| `11` | `11 · generate · calculate · size method` | Calculation and Heraldic Achievement | 12 | 1 | 7 | This cluster deals with methods of calculation and symbolic achievement. It includes terms related to cell size and heraldic achievements. |
| `12` | `12 · film · song · buzzard` | Birds and Celestial Terms | 2 | 7 | 8 | This cluster connects birds of prey with astronomical and cultural terms. It includes buzzards, hawks, and references to Eridanus and Amida. |
| `13` | `13 · hedges · trees · feet` | Hedges and Planted Trees | 5 | 1 | 1 | This cluster describes vegetative barriers and wildlife habitats. It covers hedges, trees, and their height in natural settings. |
| `-1` | `Unassigned / outlier` | Unassigned / outlier | 53 | 0 | 0 | Low-density entries, short cross-references, and bare plate captions retained outside the 14 main clusters. |

## OCR flag overlay

In `artifacts/compare/shared_space_umap.png`, Britannica entries are plotted as circles (`o`) and Wikipedia articles as diamonds (`D`). Thin gray lines connect matched pairs across the two corpora.

We draw **burgundy outlines** around the 76 Britannica entries that have confirmed OCR issues (`cause == "ocr_failure"` in `artifacts/match/uncertainty.jsonl` or `norm_edits >= 5` in `artifacts/extract/entries.jsonl`). This makes OCR degradation visible in the shared topic space: heavily repaired treatise pages still cluster near their modern Wikipedia counterparts, whereas garbled short entries without matches fall into the outlier periphery.

## Reproduce

Run the topic pipeline from the repository root:

```bash
uv run python -m nemotron_challenge.topics
```
