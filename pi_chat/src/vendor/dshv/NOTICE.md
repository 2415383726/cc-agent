# dsh-visualize vendored assets

本目录的文件源自 [Nagi-ovo/dsh-visualize](https://github.com/Nagi-ovo/dsh-visualize)
（BSD-3-Clause，Copyright (c) 2026 Jesse Zhang），见本目录 LICENSE 与
`frame-css.ts`（逐字拷贝）。

## 拷贝清单与改动说明

| 文件 | 来源 | 改动 |
| --- | --- | --- |
| `frame-css.ts` | `src/frame-css.ts` | 逐字拷贝 |
| `shell.ts` | `src/shell.ts` | **适配**：FRAME_CSP 收紧为零网络（本部署为纯内网，去掉上游 7 个 CDN 白名单；`data:`/`blob:` 为自包含内联内容、无网络请求，予以保留）；移除 card style 包、viz-helper（dshViz.state/prompt 桥）与流式预览（v1 范围外）；保留 buildFrameDoc 骨架、高度上报器与 sanitizeCssValue |

上游的工具端（lint、存储、图片嵌入）没有 vendor：本项目的对应实现
（`pi_dify/pi_agent/visualize.py`）按同一安全模型重写并按 intranet 策略收紧。
