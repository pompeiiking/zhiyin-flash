# c2-hbu 视图作者契约

> 读者：给这份样张补一个界面的人（或 agent）。**只读这一份就能开工**。
> 上位文档：`../../DESIGN-LANGUAGE.md`（"活"的判定口径）、`../../PLAN.md`（施工契约）、
> `../../COLORS.md`（配色来源）。本文件只讲"在这个原型里怎么写一个视图"。

---

## 0. 三十秒版

| | |
|---|---|
| **产物** | `_src/views/<key>.html`（结构）+ `_src/css/<key>.css`（样式）+ 可选 `_src/js/<key>.js`（行为） |
| **组装** | `node _tools/build.mjs` → 写出 `index.html`（**不要手改 index.html，会被覆盖**） |
| **视图清单** | `_src/views.json`。key 已在里面登记，**照用，不要新造 key** |
| **演示数据** | `_src/DEMO-DATA.md`（同一份人物与数字，20 个页面共用一个故事） |
| **样式基线** | `_tools/c2.css`（**已批准，只读**）+ `_src/css/10-data-page.css`（数据页共用组件） |
| **最重要的一条** | 数据页的"活"= **组织可见**。不是加过渡动画（反例表见 DESIGN-LANGUAGE §5） |

---

## 1. 一个视图长什么样

`_src/views/report.html`：

```html
<div class="main__scroll">
  <div class="pg">
    <header class="pgh">…</header>
    <section class="sec">…</section>
  </div>
</div>
```

硬规矩：

1. **根元素必须是 `<div class="main__scroll">`**，且**一个视图只有一个**。
   视图切换靠 `.main > .main__scroll:not([data-active="true"]){display:none}`。
   `data-view` / `data-active` 由 build 自动注入，**你不要写**。
2. 片段里**禁止** `<style>`、`<script>`、`<link>`、`<html>`、`<body>`。
3. `id` 全站必须唯一（build 会拦）。**给自己视图的 id 加前缀**：`id="rp-sec1"`。
4. 自己的类名**加视图前缀**：`.rp-`（report）、`.pf-`、`.dir-`、`.int-`、`.sch-`、`.nt-` …
   共享组件直接用本文件第 3 节的名字，**不要改它们的全局定义**。
5. **禁用类名**（基线与对话脚本已占用，撞了会当场坏）：
   `.tab .panel .ev .card .note .lead .mats .handoff .action .railcard .composer .bubble
   .agent .conv-head .expand .stream .turn-me .turn-host .stage .column .rail`
6. 需要微调共享组件时，用**提高特异度**而不是覆盖全局：
   `[data-view="report"] .sec__t{…}`（先用 `getComputedStyle` 量，再改；见 §7）。

---

## 2. 数据页的"活"：四个落点，每页至少命中三个

> **截屏测试**：截一张静止图，信息一点没丢 = 死的。
> 数据页没有主体、没有时间线，所以它的活**不在"动"，在"组织"**。

| # | 落点 | 用什么 | 在页面上表现成什么 |
|---|---|---|---|
| ① | **结构显形** | `.sec` `.kv` `.tbl` `.tl` `.cmp` `.delta` | 不是一个列表，是信息的形状：谁支撑谁、差多少、连到哪 |
| ② | **组织权交给用户** | `.lens` | 同一批信息按来源/时间/主题/贡献**重新分组**（条目被搬动，不是换列表） |
| ③ | **粒度与溯源** | `.zoom` `.src` `.tl` | 摘要↔细节↔原文连续缩放；每条信息能剥开看到来历（哪次对话、什么时候、谁给的） |
| ④ | **状态与不确定性** | `.conf` `.state` `.stale` `.callout` | 已核实/对话里说的/推断/过期/冲突**有品质差异**，不是一律灰字 |

**自查（DESIGN-LANGUAGE §6，逐条过）**：
1. 静图会丢什么信息？丢了什么就说明这页活了。
2. 有没有"进行时"（正在发生的事可见）？
3. 用户改一下组织方式/勾掉一件事，看到的反馈是**即时且连锁**的吗？
4. 信息之间的**关系**可见吗（不只是并列）？
5. 组织方式能被用户改变吗？
6. 状态与不确定性被看见了吗？
7. 每一处动效，能回答"**这里发生了什么**"吗？答不上来的删掉。
8. `prefers-reduced-motion` 下有可用形态吗？
9. 桌面 1280 与手机 390 都成立吗？

### 2.1 动效纪律（反例表）

**禁止**：页面淡入 / 元素位移进场 / 数字滚动 / 指示线滑动 / 持续背景运动 / 粒子 /
发光边框 / 自动轮播 / marquee / 给静态界面加"过渡感"。

**允许且鼓励**（它回答"发生了什么"，不是进场装饰）：
- `.lens` 的重新分组（引擎已实现 FLIP，你只要给数据打标签）
- 交互导致的状态迁移：勾掉一件事 → 进度推进、下一件浮出、剩余重算（`.pick` + `C2.toast()`）
- 进行时标记：`.tl__i--now`、`.tag--live`、骨架 `.skel`
- 数值/关系**真的变了**之后的过渡（不是"进页面播一遍"）

必须降级：基线的 `prefers-reduced-motion` 已把所有 `transition-duration` 归零到 1ms。
**不要**把信息只放在动画里（动画一停就丢信息 = 这页没做完）。

---

## 3. 可用的组件（先看这里，别重复发明）

### 3.1 基线已有（`_tools/c2.css`，只读）

| 组件 | 说明 |
|---|---|
| `.btn` `.btn--primary` `.btn--ghost` | 按钮 |
| `.chipbtn` | 胶囊小动作（带图标） |
| `.tag` `.tag--demo` `.tag--live` | 标签；`.tag--demo` 用来标"演示数据" |
| `.pill` `.pill--time` | 小徽标 |
| `.meter` + `i.on` | 分段进度条（**勾掉一件事让一段亮起来**） |
| `.avatar .avatar--sm .avatar--xs` | 头像（占位用 `<span class="avatar avatar--sm"><span class="avatar__pebble"></span></span>`） |
| `.sr` | 只给读屏看的文字 |
| `.dot` | 状态点 |

### 3.2 数据页共用（`_src/css/10-data-page.css`）

| 组件 | 用法要点 |
|---|---|
| `.pg` `.pg--wide` `.pg--narrow` | 单列内容容器（1180 / 1360 / 820） |
| `.pg-doc` `.pg-doc__main` `.pg-doc__side` | 主内容 + 侧栏（景深：结论在前，支撑在后；侧栏 sticky） |
| `.pgh` `.pgh__title` `.pgh__lead` `.pgh__meta` `.pgh__acts` | 页头：大标题 + 一行元信息 + 动作 |
| `.crumb` | 面包屑：`分组 › 页面` |
| `.sec` `.sec__h` `.sec__t` `.sec__d` `.sec__n` `.sec__acts` `.sec__body` `.sec__foot` | 分区（白面 + 真阴影）。`.sec--flat` `.sec--quiet` `.sec--flush` |
| `.sub` `.sub__t` `.sub__d` `.hr` | 分区内的小节与分隔 |
| **`.lens`** `.lensbar` `.lensbtn` `.lens__hint` `.lens__items` `.lens__item` | **视角重组**（见 §4） |
| **`.zoom`** `.zoombar` `.zoombtn` `.zoom__body` `.z--sum` `.z--mid` `.z--full` | **粒度缩放**（见 §5） |
| `.srcs` `.src` `.src--chat/--doc/--teacher/--self` `.src__ic` `.src__k` `.src__w` | **来源**：一条信息从哪来 |
| `.conf` `.conf--verified/--reported/--inferred/--stale/--conflict` | **可信度/状态**：有多结实 |
| `.stats` `.stats--pair` `.stats--wide` `.stat` `.stat__n` `.stat__t` `.stat__d` `.stat--key` | 读数瓦片（大号数字）。带说明句的瓦片用 `--pair`/`--wide`，别用默认 148px（说明会折成四行） |
| `.cmp` `.cmp__r` `.cmp__k` `.cmp__track` `.cmp__bar` `.cmp__v` `.delta` | 同刻度对照与差距（`--cmp-x` 可覆盖标签列宽） |
| `.tbl-wrap` `.tbl` `th/td` `[data-num]` `[data-key]` | 表 |
| `.kv` `.kv__r` `.kv__k` `.kv__v` | 键值行 |
| `.tl` `.tl__i` `.tl__i--now/--future` `.tl__when` `.tl__what` `.tl__d` `.tl__meta` | 时间线 |
| `.pick` `.pick__r` `.pick__box` `.pick__title` `.pick__meta` `.pick__tail` | 可勾选的事（`data-done="true"`） |
| `.state` `.state--error` `.state__ic/__t/__d/__acts` | 空态 / 错误态 |
| `.skel` `.skel__l` `.skel--box` | 骨架屏 |
| `.stale` | 过期信息（不删、不装作有效） |
| `.callout` `.callout--warn` `.callout--quiet` | 说明块 |
| `.fold`（用原生 `<details>` + `.fold__sum` `.fold__body` `.fold__n`） | 渐进展开，**只放次要材料** |
| `.chipbar` `.chipf` | 一排筛选 chip（不是三层嵌套折叠） |
| `.toasts` `.toast` | 用 `C2.toast('已加入今日行动')` 触发 |

### 3.3 `C2` 接口（`_src/app.js` 提供，你用这些）

```js
C2.onView('report', function () { /* 这个视图被显示时执行，已显示则立即执行 */ });

// 视角重组：给数据打标签即可，分组头由引擎生成
C2.lens(document);            // 手动初始化（一般在标记里写好就会自动生效）
C2.zoom(document);

C2.toast('已加入今日行动');    // 即时反馈
C2.show('home');              // 跳转
C2.view();                    // 当前视图 key
```

---

## 4. 视角重组（`.lens`）：本样张的主承重件

同一批信息，按**来源 / 时间 / 主题 / 对结论的贡献**重新分组。
切换时条目是**被搬动的**（FLIP），不是"换个列表内容"——这正是 DESIGN-LANGUAGE §4.2 与
反例表"多视角做成 tab 换个列表"的分界。

```html
<div class="lens" data-lens="topic"
     data-order-topic="实践证据|课程与成绩|方向偏好"
     data-hint-topic="同样 8 条，按它回答的问题聚成 3 组：能不能证明你做过，比说喜欢哪个方向更有用"
     data-hint-source="同样 8 条，按谁说的聚成 4 组：你和顾问说的、教务系统给的、你自己填的">
  <div class="lensbar" role="tablist" aria-label="按什么看">
    <button class="lensbtn" type="button" role="tab" data-lens-set="source">按来源</button>
    <button class="lensbtn" type="button" role="tab" data-lens-set="time">按时间</button>
    <button class="lensbtn" type="button" role="tab" data-lens-set="topic">按主题</button>
    <button class="lensbtn" type="button" role="tab" data-lens-set="weight">按对结论的贡献</button>
  </div>
  <p class="lens__hint" data-lens-hint aria-live="polite"></p>
  <div class="lens__items">
    <article class="lens__item"
             data-source="对话里说的" data-time="10-12" data-topic="实践证据" data-weight="直接支撑">
      …内容…
    </article>
    …
  </div>
</div>
```

要点：
- `data-<视角>` 的值是**分组名**（不是数值）：`data-weight="直接支撑"` ✅，`data-weight="3"` ❌。
- 四个视角的**分组名各自成体系**，不要混用。
- `data-order-<视角>` 用 `|` 分隔给定组顺序；不给就按首次出现顺序。
- `data-hint-<视角>` 是切换后**说明"现在按什么看"的那句话**（会读给读屏）。
- 每页**最多一个** `.lens`，条目 6~14 条。它是页面主角，不要塞进侧栏当装饰。

---

## 5. 粒度缩放（`.zoom`）：摘要 ↔ 细节 ↔ 原文

三层**同时写在标记里**，只切可见性。所以它在 `prefers-reduced-motion` 下照样可读，
也**不是**"把来源藏进一个折叠框"（那是反例表明确禁止的）。

```html
<div class="zoom" data-zoom="sum">
  <div class="zoombar" role="group" aria-label="看到多细">
    <button class="zoombtn" type="button" data-zoom-set="sum">摘要</button>
    <button class="zoombtn" type="button" data-zoom-set="mid">细节</button>
    <button class="zoombtn" type="button" data-zoom-set="full">原文</button>
  </div>
  <div class="zoom__body">
    <span class="z--mid">…比摘要多一层的事实…</span>
    <span class="z--sum">…一句话…</span>
    <span class="z--full">…可核对的原始表述…</span>
  </div>
</div>
```

三层必须是**同一件事的三种粒度**（不是三段互不相干的文字）。原文层要能被核对
（保留数字、日期、原话），不许编造具名机构或真实招聘信息。

---

## 6. 内容与口径

1. **演示数据**：所有内容读 `_src/DEMO-DATA.md`。页头 `.pgh__meta` 里**必须有**
   `<span class="tag tag--demo">演示数据</span>`。
2. **同一份事实**：画像"8 / 12 项"、三个方向（半导体工艺 / 新能源材料 / 材料检测）、
   "实践经历"空着 —— 这些数字与结论**跨页面必须一致**，不许各写一套。
3. **禁止**：真实机构名、真实招聘公告、真实链接、外部 CDN、远程图片、webfont 外链。
   样张要能**双击离线打开**，所以图形一律内联 SVG、字体用系统字体栈（tokens 已给）。
4. **禁止"结构自述词"**：不要给自己贴「摘要」「正文」「列表」「结论」这类只说明
   *自己是什么*的标签。**允许**说明*内容状态*的小标：「来自对话」「待你确认」
   「依据不足」「已过期」「与上次冲突」——它们说的是内容，不是版式。
5. **不要自造第二份导航**。视图就是内容区，导航/顶栏/底栏由外壳统一提供。
6. 文案写**人话**：句子短、动词开头、不喊口号、不用"赋能/一键/智能"这类词。
   不做"欢迎使用"式的空话页。

---

## 7. 视觉纪律（都是上一轮被点名的问题，别复发）

| 纪律 | 说明 |
|---|---|
| **只有一层白** | 每个 `.sec` 都要有边界 + 真阴影（`.sec` 已带 `--light-in + --e-1`）。不要出现纯白卡片叠纯白卡片却看不出层次 |
| **强调色配额** | **一个分区里最多一处**主色强调。红色只用于"需要你注意"，完成/成功不给颜色奖励（用 `--c-done` 系） |
| **字号只用 5 档** | `12 / 14 / 16 / 20 / 30`（tokens 的 `--fs-*`）。**禁止 10px 档**，禁止自造字号 |
| **字重只用 4 档** | `400 / 500 / 600 / 700` |
| **可点元素** | 主要动作 ≥44×44；卡片内次要动作 ≥36×36（项目既有裁定 `--btn-h-sm`）。用探针查 |
| **对比度** | 正文 ≥4.5:1；图形/控件边 ≥3:1。**不要把 `--c-text-4` 当文字色**（门禁会红） |
| **不要横向溢出** | 1280 与 390 都不能出现 `scrollWidth > clientWidth` |
| **不要拿触控目标换高度** | 上一轮把「支撑 N 条判断」压成 22px 换来了页高，那是错的 |
| **信息不做成文字罗列** | "平"的根因是所有信息等距等权同形。用 `.sec__t` / `.kv` / `.tbl` / `.cmp` / `.stat` 建立景深 |

---

## 8. 交付前必须自己跑一遍

> ⚠️ **不要跑不带参数的 `node _tools/build.mjs`**：它写的是 `index.html`，
> 多个作者同时在改，会互相踩。用下面这条 `--only`（只装你自己那一个视图，
> 写进 `_shots/preview-<key>.html`）。完整构建与 `--strict` 门禁由 Lead 在所有人停下后跑。

```powershell
# 在 directions/c2-hbu 下（--file 指向自己的预览文件，各量各的）
node _tools/build.mjs --only <key>                                  # → _shots/preview-<key>.html
node _tools/probe.mjs --file _shots/preview-<key>.html --views --width 1280
node _tools/probe.mjs --file _shots/preview-<key>.html --views --width 390
node _tools/probe.mjs --file _shots/preview-<key>.html --tap  --view <key>   # 盘 <44px 的可点元素
node _tools/probe.mjs --file _shots/preview-<key>.html --wrap --view <key>   # 盘溢出/被挤折行
node _tools/probe.mjs --file _shots/preview-<key>.html --lens --view <key>   # 视角重组的组数与搬动条数
node _tools/probe.mjs --file _shots/preview-<key>.html --sel "#<你的某个 id>" # 量某个元素的盒与计算样式
node _tools/shot-views.mjs --file _shots/preview-<key>.html --views <key> --widths 1280,390 --full --out _shots/<key>
```

探针每次运行都会报告**页面 JS 异常**（`[FAIL] 页面 JS 报了 N 条错误`）。
有异常必须修 —— 一个未捕获异常会打断整个 IIFE，后面的路由与引擎都不跑，
页面只是"看起来有点不对"。

**先量再改**：`--sel` 量出实际盒模型与计算样式，别按感觉调 CSS。
本项目上一轮的教训之一就是"拿估感当数据"。

然后在回报里逐条回答（**不许写"已达标"这种话，要贴数字**）：

- [ ] 视图 key / 文件路径 / 行数
- [ ] 四个落点命中了哪三个，分别在文件的哪一段（给行号）
- [ ] `.lens`：4 个视角各自的组名与条数（贴 `--lens` 的输出）
- [ ] `.zoom`：三层是不是同一件事的三种粒度
- [ ] 1280 / 390 的 `overflow` 与 `<44px` 数字（贴 `--views` 输出）
- [ ] 用了哪些共享组件、是否新增了 CSS（新增了哪些类）
- [ ] 有没有编造源数据里没有的**具名机构/真实招聘信息**（有就要删）
- [ ] 已知不足（诚实列，别藏）

---

## 9. 绝对不要做的事

- 不要手改 `index.html`（build 会覆盖它）。
- 不要改 `_tools/c2.css`（已批准的基线）、`_tools/build.mjs`、`_src/app.js`、`_src/shell/*`。
  需要外壳层面的能力，**回报给 Lead**，不要自己动。
- 不要改别人的视图文件（`_src/views/<你的 key>.html` 与 `_src/css/<你的 key>.css` 才是你的写域）。
- 不要用 `:deep()` / 跨文件覆盖去改别的视图（这是本项目"规范被后加载文件覆盖"的成因，已出现 4 次）。
- 不要引入依赖、构建步骤、CDN、字体外链。
- 不要用"加动画"来交差。**一页做完只能靠动效更丰富来证明变化，这页就没做完。**
