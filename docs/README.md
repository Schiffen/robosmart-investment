# docs/

Two kinds of thing live here, and it is worth knowing which is which before you read one.

## Project documentation

Written for anyone reading or extending the code. These are kept current.

| File | What it is |
|---|---|
| [`PRODUCT.md`](PRODUCT.md) | positioning and design principles: who the app is for, what it refuses to do, and why |
| [`INTEGRATION_CONTRACT.md`](INTEGRATION_CONTRACT.md) | the frozen data contracts between the data layer and everything that consumes it. §1 is Contract B; §3 is the single-benchmark rule |
| [`DEPLOY.md`](DEPLOY.md) | how the app is deployed |
| [`screenshots/`](screenshots/) | the images the README and the summary document embed |

See also [`../CLAUDE.md`](../CLAUDE.md) (the standing engineering briefing — invariants,
known traps, and the defects only a live run caught) and [`../logos/LOGOS.md`](../logos/LOGOS.md)
(the placement contract for the marks).

## Coursework deliverables

This is a university project, and these are the artefacts submitted with it. They are
snapshots of a moment, not living documents — read them as a record of what was handed in.

| File | What it is |
|---|---|
| `summary_document.md` → `summary_document.pdf` | the five-page project summary |
| `summary_document_long.md` | the unabridged version the five-page cut was made from |
| `video_script.md` | script for the demo recording |
| `build_pdf.sh`, `print.css` | build the PDF from the markdown (needs `pandoc` and Google Chrome) |

```bash
docs/build_pdf.sh      # rebuilds summary_document.pdf and checks the 5-page limit
```

> ⚠️ **`summary_document.*` and `video_script.md` are known to be stale.** They predate the
> data layer, the sample profiles, deployment to Streamlit Community Cloud, the analyst
> agent, the portfolio builder and the design passes. Treat the README and `CLAUDE.md` as
> the accurate description of the app; these describe an earlier one.
