# gakumas-SRTSubtitle

Auto-updated SRTSubtitle lyric source files for Gakumas Localify.

## Folders

- `SRTSubtitle/`: auto-generated untranslated source files from game resources.
- `translated/SRTSubtitle/`: translated files maintained manually.
- `revision`: latest processed Octo database revision.

`SRTSubtitle/` files use the Localify map format:

```json
{
  "name": "srt_live_all-005",
  "bundle": "tln_live_all-005",
  "pathId": 8938,
  "subtitles": {
    "あれよという間に飲み込まれる\r\n": ""
  }
}
```

Put translated files with the same format under `translated/SRTSubtitle/`.
`GakumasTranslationData` should only copy `translated/SRTSubtitle/` into
`local-files/SRTSubtitle`.
