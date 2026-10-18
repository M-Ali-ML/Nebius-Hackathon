# Match threshold check

Run: `artifacts/match/candidates/*.json` (262 entries, all entries, no cap), 2026-10-18.
Scores are raw logits from `nvidia/llama-nemotron-rerank-vl-1b-v2` (revision b8a9987b).
Query: headword + entry `text_norm`, cut to 2,000 chars. Documents: title + 1,000-char BM25 excerpt.

## Logit distribution (top-1 per entry, 259 entries with candidates)

| Quantile | 10% | 25% | 50% | 75% | 90% |
| --- | --- | --- | --- | --- | --- |
| Top-1 logit | -9.70 | -8.09 | -6.26 | -4.86 | -3.91 |

Logits are low and overlap. Correct matches occur down to -8.9 (Esarhaddon).
Wrong matches occur up to -3.7 (Cell counting, Fig (restaurant)).
Inference: long, noisy OCR queries pull every logit down, so a single logit cut loses many clear matches.
The margin (top1 - top2) and the headword vs title relation separate the remaining cases better.

## Rule chosen (match.py)

1. Drop candidates whose title ends in "(disambiguation)".
2. Entries under 40 chars (bare plate captions, fragments): `no_clear_counterpart`.
3. Accept if top logit > TAU = -4.0.
4. Entries with a headword or running-head topic: accept if logit > -8.0 and margin >= 1.2.
5. Entries with a headword: accept if logit > -9.0 and the title equals the headword ("exact").
6. Else `no_clear_counterpart`. The best candidate stays in matches.jsonl for review.

Result: 67 matched (22 by logit, 23 by margin, 22 by exact title), 195 no_clear_counterpart, 0 errors.

## 15 pairs read by hand (entry text vs Wikipedia excerpt)

| Entry | Headword / topic | Top-1 title | Logit | Margin | My verdict | Rule result |
| --- | --- | --- | --- | --- | --- | --- |
| B:1166:0 | LIBERTY OF THE PRESS (running head) | Press laws | -2.38 | 0.95 | correct topic | matched |
| B:452:0 | none | Cell counting | -3.66 | 0.08 | wrong; the Parse text is invented modern prose, not the scan | matched (known error) |
| B:948:0 | caption "Lava. Plate CCLXXIV." | Russian monitor Lava | -3.98 | 3.17 | wrong | rejected (short) |
| B:251:5 | SYDINHAM | Thomas Sydenham | -3.55 | 2.53 | correct | matched |
| B:1473:1 | ESCAMADE (OCR of ESCALADE) | Escalade | -5.60 | 1.63 | correct | matched (margin) |
| B:2464:6 | CABINET | Cabinetry | -7.79 | 0.15 | partial (entry is mostly the room sense) | rejected |
| B:1614:2 | THISTLE | Order of the Thistle | -4.80 | 0.82 | correct for most of the entry | rejected |
| B:2250:11 | BYSUS | Sea silk | -9.46 | 1.44 | wrong (entry is an algae genus) | rejected |
| B:1017:5 | HELMET | Corinthian helmet | -5.51 | 0.02 | partial (subtype, not "Helmet") | rejected |
| B:1214:3 | DANAE | Charon's obol | -5.34 | 0.44 | correct concept; 2nd "Danake" is the exact article | rejected (miss) |
| B:1910:0 | none (continuation) | Lightning | -3.75 | 0.72 | correct | matched |
| B:2473:10 | ERGOT (farriery) | Ergot (horse anatomy) | -7.57 | 2.36 | correct | matched (margin) |
| B:713:4 | OUNDELE | Nen River (China) | -7.18 | 1.00 | wrong | rejected (margin < 1.2) |
| B:1805:5 | EXERCISE | Exercise (disambiguation), 2nd Exercise | -3.41 | 0.34 | Exercise is correct | matched to Exercise after rule 1 |
| B:2001:5 | SILLIUS TALIOLOS | Silius Italicus | -3.98 | 1.22 | correct | matched |

Hand check score: 9 correct, 2 partial, 4 wrong at top-1.
With the rule: 7 of 9 correct pairs accepted (Thistle and Danae missed); 3 of 4 wrong pairs rejected (Cell counting accepted).
MIN_MARGIN went from 1.0 to 1.2 because of B:713:4 (Nen River, margin 1.00).
This is a small check on our own judgment, not a labeled evaluation set.

## Known errors seen in the matched set

- B:452:0 -> Cell counting: Parse produced unrelated text for this page. The match is consistent with the text but not with the scan.
- B:651:0 -> Fig (restaurant): plate page; the caption is only "Fig 1 Fig.2 ...".
- B:851:0 -> Ray (optics): broad optics section matched to a narrow article.

## Page-level pass and short queries (second run, 2026-10-18)

Short query: head (headword or cleaned page topic) + the first 600 chars of text.
Short-query top-1 logits: 10% -9.66, 25% -8.33, 50% -7.11, 75% -5.34, 90% -4.14.
They are not higher than long-query logits (median -6.3). Inference: the low scale comes from the reranker
and old-print vocabulary, not only from query length. So the short pass uses the same accept rules.
Short and long rerank agree on top-1 for 194 of 262 entries.

Page topic cleaning: running head -> word-list correction (same or shorter word, same first letter or vowel swap,
ties broken by frequency in the page text) -> BM25 title check. Examples: UPTICS -> Optics, PHILLOOGY -> Philology,
INDTA -> India, C H E M I S SI T R Y -> Chemistry, BLOW-PIPE -> Blowpipe. Failures: THROXEN -> Throe, THOTHR -> Tother.
BM25 ranks short pages first. "Optics" and "Anatomy" are not in the top 100 for the bare title,
so the page search also adds 24 distinctive page terms.

New rule, guide word: on a continuation page whose running head is a 3-4 letter guide word ("LYR", "LOM"),
accept the best short-rerank candidate (top 10) whose title has a word starting with the guide letters, if logit > -8.0.
The guide word comes from the print layout, so it is evidence independent of the reranker.
Hand check of the 10 guide-word matches: correct 5 (Lyre, Kingdom of the Lombards, Chivalry, Invasion of Algiers,
List of human-based units of measurement), partial 4 (Thebes, Egypt; Execution of Mary, Queen of Scots;
Some Thoughts Concerning Education; Diligence (Scots law)), wrong 1 (Harry Billinge).

Exact-title fix: a bracketed qualifier for a work ("Abyssinia (1906 musical)") no longer counts as exact.
