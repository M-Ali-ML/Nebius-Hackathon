# Limits

- OCR noise is the largest error. It inflates superseded and renamed counts. A similarity filter flags some term pairs. It does not flag all of them.
- The 40 retrieval labels are one reader's judgment. [Retrieval ablation](retrieval-ablation.md).
- If the right Wikipedia article is outside the 30 BM25 hits, embed and rerank cannot find it.
- Page 452 is a blank cover. Parse invented text for it, and that text passed through later stages. [failure-3](cases/failure-3.md)
- A quote check shows that the quote is in the source. It does not show that the quote supports the claim.
- The plate prompt names a date range. The collection covers 1768 to 1860, and a page row has no edition date.
- Atlas positions are a 2D approximation. Image-to-text agreement measures how well Embed VL reads 18th-century print. [Atlas](atlas.md).
- In the four debates the judge gave no point to the Scholar. Some Scholar quotes are not in the OCR. The page marks those sentences unverified. [Debate](debate.md).
