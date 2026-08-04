# Committed manifests

A campaign arm belongs here, not in a dispatch box.

Inline JSON cannot carry one. A strict manifest names all ~191 keys, and since
#994 the localized ones are `{locale: text}` maps, so a single-locale baseline
runs to ~167 KB — past the dispatch input limit, which surfaces as
`Argument list too long` from the researcher's own shell before GitHub sees it.

A committed manifest also gets what a pasted one cannot: review, history, and a
digest anyone can recompute.

## Running one

```bash
python3 -m ciris_engine.logic.utils.research_overrides validate \
  tools/research/manifests/<arm>.json

python3 -m ciris_engine.logic.utils.research_overrides manifest-digest \
  tools/research/manifests/<arm>.json
```

Dispatch **Research Trace Capture** with `overrides_manifest_path` set to the
path and `overrides_manifest_digest` set to that value. The run refuses on
mismatch.

## Why the digest is not optional in practice

Named by path, two arms that differ are indistinguishable after the fact, and an
arm edited in place between dispatch and run leaves no trace (FSD §15.3). The
digest is over canonical content — independent of filename and key order — so a
one-byte edit changes it and the run stops. Omitting it is permitted and costs
the provenance claim; the run says so in its own summary.

Manifests are pinned to a commit: the file is read from the ref being run, so
`<path> @ <sha>` identifies it and the digest proves it.
