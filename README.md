# gakumas-SRTSubtitle

本仓库用于维护《学园偶像大师》Live 歌词字幕资源，供 Gakumas Localify 使用。

仓库分为两部分：

- `SRTSubtitle/`：由 GitHub Actions 自动从游戏资源中提取的未翻译歌词源文件。
- `translated/SRTSubtitle/`：手动维护的翻译后歌词文件。

`revision` 文件记录当前已经处理到的 Octo 资源库版本号。

## 文件格式

歌词文件使用 Gakumas Localify 当前读取的 map 格式：

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

翻译时请在 `translated/SRTSubtitle/` 下放置同名 JSON，并将 `subtitles` 中的 value 改为翻译后的文本。例如：

```json
{
  "name": "srt_live_all-005",
  "bundle": "tln_live_all-005",
  "pathId": 8938,
  "subtitles": {
    "あれよという間に飲み込まれる\r\n": "あれよという間に飲み込まれる\n不知何时早已被吞没\r\n"
  }
}
```

后续 `GakumasTranslationData` 应只复制：

```text
translated/SRTSubtitle/
```

到发布包中的：

```text
local-files/SRTSubtitle/
```

## 自动更新

本仓库的 `.github/workflows/auto-update.yml` 会自动检查游戏资源更新。

触发方式：

- 每小时自动运行一次。
- 也可以在 GitHub Actions 页面手动运行 `Auto Update`。

自动更新流程：

1. 读取本仓库的 `revision`。
2. checkout `chihya72/HatsuboshiToolkit` 的 `srt` 分支。
3. 运行 HatsuboshiToolkit，从游戏 Octo API 查询 `revision` 之后的资源差分。
4. 如果差分中包含 `tln_live*` 资源，就下载并解密对应 AssetBundle。
5. 从资源中提取 `SRTSubtitle/*.json`。
6. 将新提取的文件复制到本仓库的 `SRTSubtitle/`。
7. 更新 `revision` 并自动提交。

如果本次 Octo 更新中没有新的 `tln_live*` 歌词资源，Actions 会正常结束，不会修改 `SRTSubtitle/`。

增量更新时不会删除旧的 `SRTSubtitle/` 文件，只会覆盖或新增本次发生变化的歌词文件，方便通过 Git diff 查看未翻译歌词源文件的变化。
