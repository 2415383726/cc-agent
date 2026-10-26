# 移除 MinIO 模式

Status: complete

用户反馈：实测 MinIO 模式没有实际用起来，认为属于过度设计，要求去除。用户已确认全部推荐范围，实施和验证已完成。

## 移除前的事实记录

- 两个策略入口（AG-UI / Dify 原生输出）都可选择 `dify_only` / `minio`，协议选择与存储模式独立。
- MinIO 模式同时负责会话状态持久化、工作区、上传文件导入、产物发布、三层技能包管理和脚本执行，并非独立的存储适配器。
- 当前基础内部工具有 12 个；MinIO 额外开放 9 个：`list_files`、`inspect_file`、`read_file`、`write_file`、`delete_file`、`run_python`、`SkillRunScript`、`SkillInstall`、`SkillRemove`。
- `files` 在 Dify 路径仍提供安全附件元数据；`SkillReadResource` 仍需读取随插件打包的技能参考资料。
- `state_ref` 同样由 Dify 状态后端生成；前端使用其 `conversation_id` 恢复会话标识，不能按字段名当作 MinIO 专属内容删除。
- `profiles.py` 还承载两个策略入口的协议和技能组配置；`skill_runtime.py` 混有共享的资源读取逻辑，需要拆除执行部分后保留共享能力。
- 前端附件上传及 Dify 原生 blob 产物展示不依赖 MinIO。

## 已确认目标

1. 仅保留 Dify 会话状态路径，删除公开 `capability_mode` / `storage` 参数及双模式运行分支。
2. 删除 MinIO 状态后端、工作区、9 个专属内部工具、内置脚本执行、远程技能包安装和管理。
3. 保留两个输出策略入口、Dify 外部工具注入、`agent_state` 编解码与压缩、记忆、任务、交互中断、内置技能和 `app_skills_yaml`。
4. 保留附件元数据、技能参考资料读取和 Dify 产物展示；文件分析或执行仍可由 Dify 注入的外部工具提供。
5. 清除相关依赖、打包逻辑、失效测试和文档；共享状态契约依实际使用保留。离线包目前按架构而非依赖清单过滤 wheels，需确保不再夹带 MinIO wheel；`argon2` 等显式依赖先检查剩余用途再决定是否删除。

## 已确认决策

### Q1：功能边界

连同工作区、内置文件工具、代码执行和远程技能安装一起撤除，完全收敛到 Dify 路径。

### Q2：旧配置的升级方式

作为一次明确的破坏性升级：更新旧工作流配置，不提供 MinIO 数据迁移或兼容层；旧参数不再读取。

不访问或清理 MinIO 服务器上的数据。

## 实施后的验收

- 策略 schema 和可见工具不再提供 MinIO 模式或其专属能力。
- 插件启动与核心模块导入不再依赖 MinIO、工作区或子进程执行模块。
- Dify 状态跨轮保存、损坏状态处理、压缩及工具调用配对仍正常。
- 基础技能及参考资料、`app_skills_yaml`、外部工具、附件信息和两个输出协议仍正常。
- 前端会话标识恢复和 Dify 附件 / blob 展示不被误删。
- 更新依赖与文档后运行适当的 Python 测试；若改动前端，再运行相关前端测试和构建。

## 基线与现有改动

- 用户工作区已有业务技能、`skills/minio/create-skill/` 和技能 zip 的删除改动；后续保留这些改动。
- 当前系统 `python3` 为 3.14。仓库根目录运行 `python3 -B -m unittest discover -s cc_agent/tests`，发现 64 个测试项，12 个测试模块因缺少 `ag_ui` / `dify_plugin` 无法导入，尚未得到完整测试基线。

## 事实来源

- `core/profiles.py`、`core/config.py`、`core/run_environment.py`
- `core/state_backend.py`、`core/state_variable.py`
- `core/skill_catalog.py`、`core/skill_runtime.py`、`core/internal_tools.py`
- `core/prompt_builder.py`、`strategies/cc_agent_agui.yaml`、`strategies/cc_agent_dify.yaml`
- `../copilotkit-dify/src/cc-assistant/lib/DifyAgUiAgent.ts`

## Comments

- 2026-10-26：完成只读范围调查，用户回复“都按推荐”，两项边界均已确认。

## 实施结果

- 已删除 MinIO 模式、工作区、9 个专属内部工具、脚本运行和远程技能管理，以及 `/skill` 命令。
- 已保留 Dify 状态、两种输出协议、技能参考资料读取、附件元数据和 Dify 外部工具 / blob 展示；补充了已移除工具边界、旧参数忽略和外部工具授权活动的回归测试。
- 已移除 MinIO、argon2-cffi、argon2-cffi-bindings、pycryptodome 及其 6 个 wheels。刷新 uv.lock 后，原锁文件已有包的版本未变化，补齐了原先遗漏的文档 / 图像依赖锁定。
- README、AGENTS、CONTEXT 和 ADR-0001 已记录最终边界和升级方式。

验证：

- Python 3.12 临时环境卸载上述 4 个包后，191 项 unittest 全部通过。
- 变更 Python 文件的 Pyflakes 静态检查通过；uv lock 离线一致性检查通过。
- 保持原有 CRLF 风格，`git -c core.whitespace=cr-at-eol diff --check` 通过。
- Linux amd64 / arm64 离线依赖解析与打包通过，包内无已删除模块、相关 wheels 或 .scratch 文件，并核对关键源文件与当前工作区一致。
- 未修改前端运行代码，未访问或清理远端 MinIO 数据；用户原有技能删除改动保留。

产物：`dist/cc_agent-0.0.2-offline-linux-amd64-arm64.difypkg`。
