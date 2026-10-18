# Uncertainty report

The challenge asks us to make it visible when a page has no clear modern counterpart.
This report gives a cause for every page and every entry that is still `no_clear_counterpart`.

- Data: `artifacts/match/uncertainty.jsonl` (one line per item: cause, evidence, best candidate, scores).
- Summary: `artifacts/match/uncertainty_summary.json`.
- Site field: `uncertainty_cause` and `uncertainty_note` on unmatched rows of `artifacts/match/page_matches.jsonl`. Entry-level causes are in `uncertainty.jsonl` (key `id` = `B:<row>:<n>`, field `cause`).
- Source of causes: `src/nemotron_challenge/uncertainty_causes.tsv`.

One reader (the match worker, Claude Opus 5.5) assigned each cause.
The reader used saved evidence only: entry text, the saved candidates and scores, the Super VL reply, and the plate results.
This is our judgment, not a verified label. "Right article" names are our best guess. We did not check every one against Wikipedia.

## Counts

| Cause | Entries | Pages |
| --- | --- | --- |
| No usable text | 20 | 6 |
| Parse/OCR failure | 37 | 1 |
| Obsolete or minor subject | 24 | 1 |
| Candidate pool miss | 47 | 16 |
| Threshold miss | 43 | 19 |
| Other | 18 | 5 |
| Total | 189 | 48 |

We name a likely right article for 169 of the 237 items.

The largest groups are pool misses and threshold misses.
Inference: most unmatched items do have a modern counterpart. The pipeline fails to find it or to accept it.
Only 25 items (24 entries and 1 page) look like subjects with no modern article.

## Causes, examples, and fixes

Citation IDs: `[B:<row>:<n>]` for entries, `[W:<page_id>:<revision_id>]` for articles.

### No usable text

The scan is blank, the page holds only a plate with a bare caption, or the entry is a cross-reference ("See X").
Signals: fewer than 40 characters, or a Picture block with no text.

- Page 2077: a blank scan. Super VL also reports a blank page (plate worker).
- [B:2473:7] "REBMIT. See HEMIT." is an 18-character cross-reference.

Fix: follow the cross-reference to its target entry. Use neighbor pages for plates (the site worker's neighbor-page tool).

### Parse/OCR failure

The headword or text is garbled, or Parse invented text.
Signals: the headword is not in the word list; the right article title differs from the headword by a few letters; Super VL disagrees with the Parse text.

- [B:546:0] Parse returned modern prose ("the number of users are available"). Super VL reads the scan as a blank page. Inference: Parse invented the text.
- [B:713:4] OUNDLE was read as OUNDELE. BM25 never found Oundle. The top candidate is Nen River in China [W:4751894:1331088292].

Fix: correct headwords against a gazetteer or a title list with fuzzy matching. Ask Super VL to read the headword from a crop of the scan. Flag pages where Super VL and Parse disagree.

### Obsolete or minor subject

The term is no longer in use, or the place, office, or genus is too minor for its own Wikipedia article.

- [B:2001:2] SILICERNIUM, a Roman funeral feast. The best candidate is a broad article [W:36109793:1352506241] (logit -9.17).
- [B:563:0] ACROTELEUTIC, a liturgical term. The best candidate is Amputation [W:2992:1352550286] (logit -8.72).

Fix: none needed. These are real "no counterpart" results. Link them to Wiktionary or a broader article and say so.

### Candidate pool miss

The right article exists, but BM25 and vision expansion never returned it. The reranker cannot recover it.

- Page 1032, HEAT: the Heat article was never retrieved. The best candidate is Heart [W:36808:1342842251].
- [B:1268:4] NAZARETH (OCR NAZARRUH): Nazareth was never retrieved.

Fix: add a title lookup (an exact-title index next to BM25). Search with cleaned headwords. Add main-article queries for broad treatise topics. Vision expansion already helped here (Laurus and Islay entered the pool).

### Threshold miss

The right article is ranked first, but the logit or margin is below the accept rules.

- Page 247, Etna: vision expansion puts Mount Etna [W:169351:1348791979] first (logit -4.75, margin 0.18). Flat margin.
- [B:1017:1] HELLEBORUS: Hellebore [W:874539:1347046406] is first (logit -5.70, margin 0.57).

Fix: use agreement between independent signals, for example Super VL subject = rerank top 1, or headword alias = title. Calibrate the rules on more labels. Report these to readers as "likely match, low confidence" rather than hiding them.

### Other

Ranking misses (the right article is in the pool but not first), segmentation errors, tables, figure keys, and pages whose subject is unclear.

- [B:681:1] A magic lantern description: Magic lantern is at rank 4. Lens [W:18320:1346821962] is first.
- [B:2131:0] A weather table for Bombay: no single article fits.

Fix: better segmentation (split merged entries), detect tables and figure keys and skip them, and rerank with an image of the page region.

## Limits

- One reader, no second check.
- Some causes overlap. An OCR failure often also causes a pool miss. We record the first cause in the chain.
- Entries on pages that are matched still appear here if the entry itself is unmatched.
