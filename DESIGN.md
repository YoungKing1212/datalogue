# Design

## Source of truth

- Status: Active · 已选定「石墨天青」方案
- Last refreshed: 2026-07-15
- Primary product surfaces: 数语 Web 工作台、对话问数、数据资产治理、数据源、系统设置、LLM 模型配置。
- Evidence reviewed:
  - `datalogue-web/src/styles.css`：全局颜色变量、按钮、设置页、LLM 控制台和弹窗样式。
  - `datalogue-web/src/components/settings.jsx`：LLM credential 的新增、编辑、发现模型、启停和删除交互，以及全部字段契约。
  - `datalogue-web/src/App.jsx`：主导航、面包屑和平台默认主题色。
  - `docs/assets/screenshots/user-manual/02-chat.png`、`assets/images/01-homepage.png`：工作台与问数页视觉基线。
  - `docs/assets/screenshots/user-manual/35-settings-llm-models.png`：历史 LLM 配置布局。
  - `~/.codex/generated_images/019f5fcc-3459-7543-a4f5-c46e5690f5aa/exec-e5b85c88-45c7-43af-9596-cf64c84eb961.png`：已确认的「石墨天青」配色参考图。
  - `datalogue-web/src/shared/components/icons.jsx`：当前跨页面共享的图标入口与语义名称。
  - `datalogue-web/src/features/chat/chat-page.jsx`、`MyComposer.jsx`、`MyMessage.jsx`、`datalogue-web/src/assistant-ui/DatalogueThread.jsx`：对话空态、Thread 外壳、上下文选择、会话同步、结果卡与安全推理摘要的现有交互边界。
  - `assets/images/chat-cot-expanded.png`、`assets/images/chat-final-clean.png`：对话完成态与过程摘要的历史视觉参考。
- 本文中的“应当”是开发与评审的设计约束；“推断”来自现有产品证据，未替代产品需求。

## Brand

- Personality: 克制、专业、可信、面向数据工作的效率工具；以石墨中性色建立结构与秩序，以天青蓝建立操作焦点，而非炫技或营销化。
- Trust signals: 清晰的运行状态、可辨识的启用/停用语义、密钥不回显、精确的端点与超时信息、稳定的导航与表单结构。
- Avoid: 仅在单页出现的独立主题色；大面积深色或赛博风背景；紫色渐层；过度玻璃效果；大圆角胶囊按钮；让 API Key 或内部运行细节看起来可被读取。

## Product goals

- Goals:
  - 让业务人员从一个自然语言问题快速获得可行动的结论、关键数字与可追溯的数据依据，而不是阅读执行过程。
  - 让管理员在一分钟内确认哪些模型已可用、哪些配置缺少密钥、当前可以执行什么操作。
  - 降低新增 credential 的填写成本，并让“模板自动填充”成为主路径。
  - 让新增、保存、发现模型的先后条件清晰可见，避免用户把“发现模型”误解为未保存也能连接测试。
- Non-goals:
  - 不把对话问数设计成数据驾驶舱；图表、表格、引用和追问均是同一答案的证据层，不抢占对话主线。
  - 不在用户可见页面展示 SQL、schema、raw rows、query plan 或模型内部推理原文。
  - 不在本次设计中增加模型路由、默认模型策略、用量计费或 API Key 明文查看能力。
  - 不改变 AgentScope credential API、持久化字段或现有新增/编辑/启停/删除行为。
- Success signals:
  - 用户可在一次屏幕扫描内识别“问题是什么、结论是什么、依据来自哪里、下一步可问什么”。
  - 页面不再因深色头部而脱离数语既有蓝灰界面。
  - 用户无需阅读帮助文本即可找到“新增 credential”和保存入口。
  - 必填项、禁用动作和安全边界有一致且可访问的反馈。

## Personas and jobs

- Primary personas:
  - 业务分析人员：用自然语言提出经营问题，并在会议或日常复盘中快速解释结论。
  - 工作区管理员：配置并维护模型供应商凭证。
  - 平台运维/交付人员：排查模型连接、停用异常凭证。
  - 只读业务用户：了解模型状态，但不应拥有修改或读取密钥的能力（权限策略沿用现有系统）。
- User jobs:
  - 提问后先读取结论，再按需展开趋势、明细和数据依据；将结果继续追问为下一轮问题。
  - 新增一个可供问数运行时调用的模型 credential。
  - 快速判断已有凭证是否启用、是否配置密钥、是否已发现可用模型。
  - 在保留密钥的前提下更新端点、模型名、超时和说明。
- Key contexts of use: 桌面端问数分析与系统设置；业务用户常在会议前或异常复盘中进行连续追问，管理员通常同时处理多个供应商。两类页面均优先支持扫描而不是阅读长段文字。

## Information architecture

- Primary navigation: 左侧保持图片中的四层级分组：问数中心、语义治理、数据连接、系统管理；系统管理包含查询审计、LLM 模型和系统设置。系统设置保留个人、工作区和开发者类二级设置。
- Core routes/screens:
  - `/chat`、`/chat/:threadId`：左侧主导航、会话列表与连续对话画布；答案可附带安全的结果卡、图表、表格预览、引用和受控重试状态。
  - `/models`：总览、credential 卡片、创建入口。
  - `/audit`：查询审计记录与筛选、导出操作入口。
  - 新增 credential：在当前设置上下文内打开的 720px 宽居中弹窗；不新增独立路由。
  - 编辑 credential：复用新增弹窗结构，但 API Key 为空时表示不覆盖已保存密钥。
- Content hierarchy:
  - 对话问数：问题 → 一句话结论 → 关键指标/趋势 → 依据与结果详情 → 建议追问；空态仅保留明确的提问入口、数据集/模型上下文和业务模板。
  1. 页面标题与一句安全说明。
  2. 浅色运行概览：已接入、运行中、密钥就绪、供应商数。
  3. “模型连接”标题、说明与新增按钮。
  4. Credential 卡片：名称与状态 → 供应商/模型 → 端点与密钥状态 → 发现状态 → 操作。
  5. 新增/编辑弹窗：接入方式 → 连接信息 → 运行参数 → 操作区。

## Design principles

- 平台优先，而非页面优先：LLM 配置必须复用数语的白底、浅蓝灰、蓝色主操作和细边框语言；不能为“控制台感”引入独立深色主题。
- 结论先行，证据随后：每条完成的问数回答先给可复述的业务结论，再给指标、图表、结果引用与可展开的过程摘要；用户不应先面对“思考中”或技术过程。
- 连续画布，而非拼贴面板：会话、结果卡和后续追问在一个阅读节奏里向下延展；右侧仅承载当前问题的轻量“依据/状态”定位，不建造第二个仪表盘。
- 石墨承载结构，天青承载行动：导航、边框、正文以中性石墨灰维持稳定；仅当前页、主要按钮、焦点与可交互链接使用天青蓝，避免页面出现多个竞争的强调色。
- 把安全状态设计为事实，不设计成戏剧化警告：密钥只显示“已安全托管 / 等待配置”，不显示掩码长度、明文入口或假装可恢复的视觉控件。
- 先模板、后细节：新增模型先选择接入模板，再只补充该模板未能确定的信息。
- 适度圆润，避免玩具感：操作按钮的圆角略大于现有基础按钮，但不使用全圆 pill。
- Tradeoffs: 保留卡片化扫描体验，但控制阴影、渐层和装饰，避免破坏设置页的高信息密度。

## Visual language

- Color:
  - 正式方案：**石墨天青**。中性灰优先于蓝色，天青只用于可操作、已选中和需要用户注意的正向焦点。
  - Token 映射（实施时一次性替换 `:root` 变量，不得让页面局部另起主题）：`--bg: #fbfcfd`、`--bg-2: #f4f6f8`、`--surface: #ffffff`、`--surface-2: #f5f7f9`、`--surface-3: #e8edf2`、`--sidebar-bg: #f4f6f8`、`--hairline: #dce3ea`、`--hairline-strong: #c9d3dd`、`--text: #1c2733`、`--text-2: #526273`、`--text-3: #778797`。
  - 天青操作色：`--accent: #1976c9`、`--accent-soft: #e8f3fd`、`--accent-line: #b9d8f7`；按钮使用实色天青，当前导航/标签/浅提示使用 `--accent-soft`，聚焦态使用 `--accent-line`，不使用紫色、靛蓝或霓虹青。
  - 状态色：`--pos: #19805c`、`--pos-soft: #e7f5ed`、`--warn: #b97616`、`--neg: #c34a36`；状态始终同时有文本或图标，不能只靠颜色传达。
  - LLM 顶部运行区为无渐变的浅天青信息面：`#f4f9fe` 背景、`#c9e0f7` 边框、石墨正文；移除深色网格、光晕和半透明读数卡，仅保留 3px 天青顶部强调线。
  - 侧栏使用 `#f4f6f8`，选中项为 `#e8f3fd`，左侧 3px 天青定位条；不使用大面积蓝色底，避免导航比内容更抢眼。
  - 当前代码已套用本方案；后续任何颜色变更必须继续覆盖全局 token、LLM 面板、卡片、弹窗和侧栏后再验收。
- Typography:
  - 保持 `Geist` / `Geist Sans` 作为界面字体，`Geist Mono` 仅用于端点、模型名、超时等技术值。
  - 页面标题 22–24px / 600；分区标题 17–18px / 600；字段标签 12–13px；技术元数据 11–12px。
- Spacing/layout rhythm:
  - 使用现有 8px 基准：卡片间距 12–16px，分区间距 28–32px，弹窗内区块间距 20–24px。
  - 独立管理页不再额外限制内容最大宽度：桌面横向页边距为 24px，760px 以下为 16px，520px 以下为 12px；使内容与工作台主内容区对齐，避免双重留白。
  - 1200px 以上凭证卡片双列；760px 以下单列；统计卡在窄屏 2×2。
- Shape/radius/elevation:
  - 现有常规圆角保留：内容卡片 10–12px、弹窗 14px、输入框 6px。
  - 本次新增规则：LLM 页面主按钮、次按钮和弹窗操作按钮使用 8px 圆角；高度保持现有 30px，不改为胶囊形。
  - 卡片悬浮仅使用轻微阴影和 1–2px 上移；不增加厚描边或强发光。
- Motion:
  - 仅保留按钮 hover、卡片 hover、弹窗出现的 120–180ms 过渡。
  - “发现模型”加载采用按钮内文字/图标状态，不使用大面积旋转装饰。
  - 遵守 `prefers-reduced-motion`：无必要动画应可关闭。
- Imagery/iconography:
  - **项目自有本地 SVG 图标库是唯一来源**。继续由 `src/shared/components/icons.jsx` 集中维护，所有图标随前端构建交付；不接入 Icons8 或任何第三方图标库、CDN、API、下载包和署名条款。
  - 图标默认使用 `currentColor`：常规为 `--text-2`，悬停/选中/主操作为 `--accent`，危险动作为 `--neg`，状态图标与对应状态文字同色；不自行给图标加渐变、投影、彩色底板或第二强调色。
  - 尺寸只允许四档：侧栏与一级导航 20px；普通按钮、字段、表格动作 16px；紧凑状态/标签 14px；空态和页面级说明 24px。点击热区不小于 32px，图标本身不因热区而放大。
  - 轮廓图标是默认状态；Filled 仅可用于已确认的、14px 以下的单一状态点，且必须同时有中文文本。禁止用不同图标风格来区分页面或功能域。
  - 语义名称由 `src/shared/components/icons.jsx` 集中维护：`home`、`chat`、`database`、`layout`、`cog`、`search`、`plus`、`edit`、`trash` 等名称保持稳定；调用方不得嵌入第三方 URL、内联临时 SVG 或按页面复制图标路径。新增图标时应先补充该共享映射，再在业务组件调用语义名称。
  - 所有纯装饰图标保持 `aria-hidden`；图标按钮必须同时提供中文 `aria-label` 与 `title`。供应商/品牌只允许使用文字或双字母标识，不下载或展示商标 Logo。
  - **交付边界**：不得新增外部图标依赖、运行时图像请求或图标授权/署名文案。现有 JSX SVG 与后续经项目自行创作的本地 SVG 均可直接随源码维护；对图标路径的调整必须保持统一入口，不新增并行图标系统。
  - **当前状态**：现有本地图标库即为正式图标系统，不进行 Icons8 素材迁移。

## Components

- Existing components to reuse:
  - `DatalogueThread`：保持 `ThreadPrimitive.Root / Viewport / Messages / composer` 壳层和自动滚动职责；Thread 不读取后端执行面，也不自行拼接会话状态。
  - `AIMessage`、`UserMessage`、`DatalogueActionBar`、`ArtifactCard`、`DatalogueComposer`：作为 Thread 内的消息、动作、结果引用和继续追问入口。
  - `SettingsScreen`、`SetRow`、`st-input`、`btn`、`icon-btn`、`st-modal`、`st-modal-footer`。
  - `LLM_PRESETS`、`LLM_PROVIDER_OPTIONS`、`buildFormFromPreset` 和现有 credential API 调用逻辑。
- New/changed components:
  - `ChatAnswerCanvas`（由现有 `Thread` / `MyMessage` 组合实现）：每个完成回答按“结论摘要 → 指标带 → 证据块 → 建议追问”呈现；沿用现有安全的 `ArtifactCard`、图表和表格预览，不新增原始执行数据。
  - `AnswerSignalStrip`：置于回答首段下方，最多展示 3 个有单位和同比/环比语义的关键数字；每项可定位到下方结果卡或图表，不能单独伪装成 KPI 大盘。
  - `EvidenceRail`：桌面端在画布右侧显示当前线程的“数据集 / 已生成结果 / 处理状态”三个短锚点；760px 以下并回回答流顶部，避免横向挤压正文。
  - `WelcomeQuestionCanvas`：保留现有数据集、模型、时间范围和分析方式选择，但把空态文案收敛为“直接提问 + 可复制的业务问题模板”，不使用营销式 AI 大标题。
  - `llm-control-panel`：改为浅色“运行概览”信息面，左侧标题与安全说明，右侧为当前启用模型的简洁读数；不再使用深色背景。
  - `llm-add-button`：保留主蓝色，圆角 8px，文本固定为“新增 credential”，带 `plus` 图标。
  - `ModelCredentialCard`（可在 `settings.jsx` 内部实现，不强制拆文件）：展示状态、端点、密钥状态、超时、发现结果与现有操作。
  - `CredentialEditorModal`（可在 `settings.jsx` 内部实现，不强制拆文件）：将既有一列长表单分为三个有标题的字段组。
- Variants and states:
  - 对话答案：提问中、待确认数据集、生成中、已完成、结果为空、受控失败、只读历史回放；状态文本直接说明下一步，不以旋转动效代替说明。
  - 按钮：主操作、次操作、幽灵、危险、加载、禁用；LLM 页统一 8px 圆角。
  - 凭证：运行中、已停用、缺少密钥、发现成功、发现失败、发现中。
  - 编辑器：新增、编辑、保存中、已保存待发现、发现中、字段校验失败。
- Token/component ownership:
  - 全局 token 仍由 `:root` 和现有 `.btn` 管理；不得为 LLM 页定义第二套主色变量。
  - LLM 专属样式使用 `.llm-*` 局部类，避免改变其他设置页按钮的圆角。

## 对话 Thread UI 设计

### 结构与阅读节奏

- Thread 是一条由上至下阅读的业务论证流，不是即时通讯气泡墙：同一轮按“用户问题 → 业务结论 → 指标/图表 → 结果引用 → 可继续追问”完成闭环。
- 桌面端消息画布有效宽度为 680–720px，居于主内容区；`chat-scroll` 底部始终为固定 composer 留出 128px 安全空间，避免最后一条回答被遮挡。
- 相邻轮次的间距为 32px；同一条 AI 回答的模块间距为 12–16px。长回答用清晰标题、短段落和有序列表分层，禁止以连续卡片堆叠取代正文。

### 用户消息

- 用户消息右对齐，最大宽度 66%，使用 `--surface-2` 背景、`--hairline` 边框和 10px 圆角；不显示拟人头像，避免把业务问题误解为社交通讯。
- 仅在当前轮/键盘焦点进入时显示“编辑问题”动作；文本按原问题完整保留，不将输入器的上下文 chip 混入气泡。
- 待确认数据集时，问题下方显示一条独立的浅天青确认条，包含“已识别的数据集”和明确的“确认 / 更换”动作；不能以弹窗打断阅读流。

### AI 回答

- AI 回答左对齐且不使用大面积气泡；顶部是 20px 本地图标、`数语`名称和简短状态。完成态不显示“已生成”徽章，生成中才显示“正在整理结论”。
- 回答首段必须是 1–2 句可直接复述的**结论摘要**；只有后端提供明确业务指标时，才在其下展示 `AnswerSignalStrip`，最多 3 项，采用并列细分隔而非大号 KPI 卡。
- Markdown 正文承载解释；图表、表格预览和 `ArtifactCard` 只作为正文后的“依据与结果”模块。卡片标题使用“结果详情 / 依据”，不使用 SQL、执行计划或其他实现面名称。
- “处理摘要”默认折叠，放在结果模块之后；仅显示安全的业务阶段名称、结果状态和耗时，绝不输出 chain-of-thought、SQL、schema、raw rows、query plan 或调试原文。
- 回答底部 Action Bar 提供复制、重新生成、朗读和编辑；鼠标悬停/键盘聚焦时出现，触屏或窄屏在回答完成后保持可见。尚未接入的反馈操作保留禁用原因，不伪装成可用按钮。

### 状态与错误

- 生成中：用户问题固定，AI 侧显示不超过三行的业务阶段摘要（如“确认问题范围”“整理结果”）；采用天青点和文本，不使用无限旋转加载器。
- 结果为空：先说明已检查的范围，再给一个可执行的缩小/替代问题建议；结果引用模块不显示空表格框。
- 受控失败：以 `--neg-soft` 的紧凑提示条说明用户下一步（调整时间、选择数据集或重试），保留原问题和上下文；不能暴露服务异常堆栈。
- 历史只读：在最上方使用一次性浅灰说明“历史会话，仅供查看”，隐藏重新生成、编辑与重试，保留复制和查看结果详情。

### Thread 响应式

- 980px 以下，AI 与用户消息均占可用宽度，用户消息最大宽度放宽到 78%，结果卡与图表保持单列。
- 760px 以下，用户消息最大宽度 88%，回答首段、指标带和结果详情统一变为单列；Action Bar 不依赖 hover，最小点击热区为 32px。
- 520px 以下，隐藏非必要状态文字，保留“数语 / 整理中”及错误原因；composer 上下文收进“上下文”菜单，Thread 不产生横向滚动。

## 新增 credential 页面设计

### 入口与容器

- 点击“新增 credential”后，在当前页面居中打开 720px 宽、最大高度 86vh 的弹窗；移动端宽度为视口减 24px。
- 弹窗标题：`新增模型连接`；副标题：`凭证将由 AgentScope 安全托管，保存后可发现可用模型。`
- 头部背景为白色，底部仅以 `#edf4ff` 作为极浅色分隔，禁止深色头部。
- 顶部右侧只保留关闭按钮；点击遮罩或关闭按钮时不丢弃已输入内容前应二次确认（仅当字段被修改时实现）。

### 表单分组与字段

1. **接入方式**
   - “接入模板”置顶，占整行，说明“选择后自动填充供应商、Base URL 与默认模型”。
   - 第二行：名称（左）与供应商（右）；窄屏按单列排列。
   - 选择“自定义 OpenAI-compatible”时，在供应商下方展开“供应商标识”。
2. **连接信息**
   - Base URL 占整行，使用等宽字体；下方显示简短格式提示，不展示示例密钥。
   - 模型名与 API Key 并列；模型名选择“自定义模型”时，展开模型名文本输入。
   - API Key 右侧增加非交互的锁图标和文案“仅保存，之后不回显”；不提供显示/隐藏按钮。
3. **运行参数**
   - 状态与超时并列；默认状态为“启用”，默认超时为 60 秒。
   - 描述占整行，标注为可选，辅助运营人员理解使用目的。

### 弹窗底部操作

- 左侧：`取消`（幽灵按钮，8px 圆角）。
- 右侧：`保存 credential`（主按钮，8px 圆角）。
- 新增状态不展示可点击的“发现模型”；在保存按钮旁以浅色说明提示“保存后即可发现模型”。
- 编辑状态可显示 `发现模型` 次按钮；当本次修改尚未保存时禁用，辅助提示“请先保存连接信息”。
- 保存成功：关闭弹窗、刷新卡片列表、在列表上方展示 `role=status` 成功消息；不在弹窗内堆叠 Toast。

## Accessibility

- Target standard: WCAG 2.1 AA，沿用现有中文界面语义。
- Keyboard/focus behavior:
  - Enter 发送、Shift+Enter 换行；发送后焦点保留在输入框，打开结果详情后 Escape 返回原回答的“查看详情”触发点。
  - 弹窗打开后焦点进入标题后的第一个可编辑字段；Tab 在弹窗内循环；Esc 触发与关闭按钮相同的关闭逻辑。
  - 所有图标按钮必须保留中文 `aria-label` 与 `title`。
  - 弹窗关闭后焦点返回“新增 credential”按钮。
- Contrast/readability:
  - 浅蓝运行区中的正文和元信息需达到 AA 对比度；禁止使用浅蓝文字承载关键状态。
  - 不能仅凭颜色区分运行中、停用和密钥缺失，需配合文本和图标。
- Screen-reader semantics:
  - 新结论和受控错误使用 `aria-live=polite`；结果卡和图表必须有明确的中文摘要与“查看详情”可访问名称，不能只以视觉图形表达结论。
  - 运行统计使用有标签的列表或 `aria-label`。
  - 保存、发现和加载结果使用 `role=status` / `aria-live=polite`。
  - API Key 输入使用 `type=password`，提示文字明确说明留空时的编辑语义。
- Reduced motion and sensory considerations: 所有动画为非必要装饰；`prefers-reduced-motion: reduce` 下移除卡片位移和光晕/脉冲效果。

## Responsive behavior

- Supported breakpoints/devices: 1280px 及以上桌面、980px 窄桌面、760px 平板、520px 手机。
- Layout adaptations:
  - 对话问数在 1280px 及以上保留 208px 主导航、240px 会话列、约 720px 对话画布和 260px 依据栏；980px 以下隐藏依据栏，760px 以下隐藏会话列并由可打开的会话抽屉替代；520px 以下输入工具项折叠为“上下文”菜单。
  - 760px 以下：运行概览改为上下结构；credential 单列；统计卡 2 列。
  - 520px 以下：新增按钮全宽；弹窗字段全部单列；底部操作区“取消 / 保存”保持可点击且不换成图标。
  - 设置页侧栏遵循现有响应式规则，LLM 页面不新增横向滚动。
- Touch/hover differences: hover 仅增强边框/阴影；触屏设备所有操作按钮始终可见，不能依赖 hover 才显示。

## Interaction states

- Loading: 首次加载保留与卡片数量匹配的 2–4 个浅色骨架，不显示“暂无模型配置”。
- 对话生成中：用户问题立即固定在画布中，回答区域显示 1–3 条业务语义的进度摘要；不得显示内部 chain-of-thought、SQL 或 schema。
- Empty: 使用蓝灰空态，明确说明“尚未建立模型连接”，提供“创建第一个 credential”按钮。
- Error: 加载、保存、发现失败显示简洁中文原因；保留用户已填写的表单字段。
- Success: 保存成功提示“AgentScope credential 已保存”；发现成功提示可用模型数量。
- 对话完成：结论摘要先出现，再平滑补齐指标带、图表/表格预览与建议追问；没有结果时说明已检查范围和可缩小问题的方式。
- Disabled: 发现模型、保存中、未保存编辑状态应提供禁用原因，不仅降低透明度。
- Offline/slow network, if applicable: 发现模型超过 10 秒时保持加载状态并提供“连接仍在进行中”的文案；不自动关闭弹窗。

## Content voice

- Tone: 清楚、克制、偏运维，不使用拟人化或营销化语言。
- Terminology:
  - 对话问数统一使用“结论”“依据”“结果详情”“继续追问”；不用“AI 正在思考”“生成 SQL”等暴露实现面的术语。
  - 页面术语统一使用“模型连接”与“credential”；首次解释使用“credential（模型凭证）”，后续可直接使用 credential。
  - “Base URL”“API Key”“ModelCard”保留英文技术名，其他文案使用简体中文。
- Microcopy rules:
  - 说明做事实陈述：`保存后不再展示明文`、`留空则不覆盖已保存密钥`。
  - 动作使用动词开头：`新增 credential`、`保存 credential`、`发现模型`、`停用`。
  - 不使用含糊词如“提交”“完成设置”替代实际操作。

## Implementation constraints

- Framework/styling system: React 19 + Vite；CSS 变量与全局 `styles.css`；复用现有 React 组件风格，不引入 Tailwind、额外组件库或新的设计系统。
- Design-token constraints:
  - 优先复用现有 `--accent` 及 `--accent-soft` / `--accent-line`，允许 LLM 局部的浅蓝常量仅用于边框或信息面。
  - 不改全局 `.btn` 的 6px 圆角；仅通过 `.llm-section .btn`、`.llm-add-button`、`.st-modal-footer .btn` 等局部选择器设为 8px。
- Performance constraints: 不新增外部字体、运行时图像/CDN、第三方图标库、动画库或实时图表；图标继续由项目自有 SVG 源码随前端构建交付，现有卡片数据继续从 credential 列表派生。
- Compatibility constraints: 保持现有 API 路径与表单字段；保存后才允许发现模型的边界不能被视觉改动绕过。
- 对话问数兼容约束：保留 `DatalogueComposer` 的数据集/模型选择、`Thread` 的会话同步、`ArtifactCard` 的结果引用、`MyMessage` 的安全过滤与现有受控 retry；视觉改版不得将受控内部字段传入用户可见层。
- Test/screenshot expectations:
  - 保持 `settings.test.jsx` 的新增保存、启停行为通过，并补充新增弹窗字段分组、禁用发现模型、焦点返回的测试。
  - 执行 `npm run lint`、`npm run test -- src/components/settings.test.jsx`、`npm run build`。
  - 截图验收至少覆盖 1440px、760px、390px 三种视口，以及新增弹窗、编辑弹窗、对话空态、已完成结论、生成中与受控失败状态。

## Open questions

- [ ] “当前启用模型”是否有后端确定的默认模型字段，还是仅显示最新启用 credential？Owner：产品/后端；影响：浅色运行概览中的模型读数文案。
- [ ] 编辑已填写的 credential 时，关闭弹窗是否必须二次确认放弃修改？Owner：产品；影响：弹窗离开保护与测试范围。
- [ ] 是否允许非管理员查看模型连接列表与状态？Owner：权限负责人；影响：页面入口与操作按钮的可见性。
- [ ] 对话答案的“依据栏”是否需要固定展示数据集名称和更新时间？Owner：产品/数据治理；影响：EvidenceRail 的内容与结果详情入口。
- [ ] “建议追问”由模型实时生成还是先使用确定性模板？Owner：产品/算法；影响：回答完成态的稳定性和实验指标。
