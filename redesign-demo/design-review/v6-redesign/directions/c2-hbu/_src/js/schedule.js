/* =============================================================================
 * 日历与课表 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页的交互只做一件事：**换一周，看同一个 8 小时里三类占用怎么互相挤**。
 *
 * 轴是**算出来的**，不是画上去的：任务只能往 gap（空档）里放，课永远压在
 * gap 之外 —— 所以"课多 → 事少"不是文案，是同一段 48 格里的减法。
 * 一格 10 分钟；一天 = 8:00–16:00 = 48 格。数字一律由这里现算，模板里不留第二份。
 *
 * 第 7 周周三：课 [24,48) 占满下午，只有 [0,24) 这一段空档，5 分钟也只占 1 格。
 * ========================================================================== */
(function () {
  'use strict';

  var STEP = 10;          /* 一格 10 分钟 */
  var SLOTS = 48;         /* 8:00–16:00 */
  var H0 = 8;
  var WD = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

  /* ---- 三周的占用 ---------------------------------------------------------
     cls / gaps / tasks 的单位都是"格"。课程逐字取自 DEMO-DATA §6；
     任务是第五节大三那一套 t1–t8（已完成的 t6/t7/t8 不再进日历）。
     有重叠的两条，时间段按并集算（人不可能同时上两门课）—— 并在 state 里写出来。 */
  var WEEKS = [
    {
      short: '第 5 周', label: '第 5 周 · 9 月 28 日–10 月 4 日', range: '9 月 28 日–10 月 4 日',
      note: '这一周还没有计划：课上完，时间整块空着',
      lenses: {
        weight: '按这一天的轻重看：这周周一、周二、周四各 4 小时课，周三 4 小时，周五 2 小时 —— 但没课的那些天也没排事，说明这一周计划还没开始跑。',
        kind: '按占用类型看：这周「必须交的」和「可以挪的」两组都是空的，全部落在「课占住的」—— 这是"计划开始之前"的样子。',
        from: '按谁安排看：这周 7 天全部来自教务系统，规划师还没写进任何节点 —— 两本账里只有一本在动。',
        time: '按时间位置看：周初到周末都没有事，空白是完整的；到第 6 周开始，周初就被塞进了 15 分钟。'
      },
      days: [
        { ab: '一', dd: 28, md: '9 月 28 日', cls: [[0, 12], [26, 38]], note: '材料分析方法 周一 1–2 节 · 工程数学 周一 5–6 节', state: '课 4 小时', gaps: [[12, 26], [38, 48]] },
        { ab: '二', dd: 29, md: '9 月 29 日', cls: [[12, 14], [34, 38]], note: '材料物理 周二 3–4 节 · 专业英语 周二 7–8 节（1–12 周）', state: '课 4 小时', gaps: [[0, 12], [14, 34], [38, 48]] },
        { ab: '三', dd: 30, md: '9 月 30 日', cls: [[24, 48]], note: '材料实验 周三 5–8 节 · 创新项目讨论第 3–10 周，本周停课', state: '课 4 小时 · 12:00–16:00', gaps: [[0, 24]] },
        { ab: '四', dd: 1, md: '10 月 1 日', cls: [[0, 12], [34, 38]], note: '半导体工艺概论 周四 1–2 节 · 材料性能测试 周四 5–6 节', state: '课 4 小时', gaps: [[12, 34], [38, 48]] },
        { ab: '五', dd: 2, md: '10 月 2 日', cls: [[24, 36]], note: '工程实践 周五 1–2 节（13:00–15:00）', state: '课 2 小时', gaps: [[0, 24], [36, 48]] },
        { ab: '六', dd: 3, md: '10 月 3 日', cls: [], note: '职业发展工作坊只在第 5、9、13 周 —— 第 5 周在 9 月 26 日那次已经上过', state: '课 0 小时', gaps: [[0, 48]] },
        { ab: '日', dd: 4, md: '10 月 4 日', cls: [], note: '实验室安全培训只在第 7 周 —— 本周没有', state: '课 0 小时', gaps: [[0, 48]] }
      ]
    },
    {
      short: '第 6 周', label: '第 6 周 · 10 月 5–11 日', range: '10 月 5–11 日',
      note: '这一周课 14 小时，任务只做进去 1.25 小时',
      lenses: {
        weight: '按这一天的轻重看：周一、周二、周三、周四被 4 小时课占住，周三还多一门重叠；「课最多的一天」这一组没有 —— 但没有一天轻到能把 25 分钟的活放进去。',
        kind: '按占用类型看：「可以挪的」这一组是空的 —— 课满 4 小时的那几天，可挪的事一件都没放进去。这就是"任务太大"落地的地方。',
        from: '按谁安排看：课 7 天来自教务系统，规划师只写进 1 天的节点（改简历），而它两次各只做了一半。',
        time: '按时间位置看：周一塞进 15 分钟，周四又 15 分钟，周末整块空着却没用来做事 —— 空档不等于可用时间。'
      },
      days: [
        { ab: '一', dd: 5, cls: [[0, 12], [26, 38]], note: '材料分析方法 1–2 节 · 工程数学 5–6 节', state: '课 4 小时',
          gaps: [[12, 26], [38, 48]],
          tasks: [{ label: '把简历第一页的封面表述改成"工艺方向"（15 分钟）', min: 15, gap: 1, at: 38, partial: true }] },
        { ab: '二', dd: 6, cls: [[12, 14], [34, 38]], note: '材料物理 3–4 节 · 专业英语 7–8 节（1–12 周）', state: '课 4 小时', gaps: [[0, 12], [14, 34], [38, 48]] },
        { ab: '三', dd: 7, cls: [[24, 48]], overlap: '材料实验 与 创新项目讨论 7–8 节重叠',
          note: '材料实验 5–8 节 · 创新项目讨论 7–8 节（第 3–10 周）', state: '课 4 小时 · 重叠', gaps: [[0, 24]],
          tasks: [{ label: '联系学长，了解半导体岗位日常（15 分钟）', min: 15, gap: 0, at: 1, missed: true }] },
        { ab: '四', dd: 8, cls: [[0, 12], [34, 38]], note: '半导体工艺概论 1–2 节 · 材料性能测试 5–6 节', state: '课 4 小时',
          gaps: [[12, 34], [38, 48]],
          tasks: [{ label: '把简历第一页的封面表述改成"工艺方向"（又 15 分钟）', min: 15, gap: 0, at: 27, partial: true }] },
        { ab: '五', dd: 9, cls: [[24, 36]], note: '工程实践 周五 1–2 节', state: '课 2 小时', gaps: [[0, 24], [36, 48]] },
        { ab: '六', dd: 10, cls: [], note: '职业发展工作坊第 5、9、13 周上课 —— 第 6 周没有', state: '课 0 小时', gaps: [[0, 48]] },
        { ab: '日', dd: 11, cls: [], note: '实验室安全培训只在第 7 周 —— 本周没有', state: '课 0 小时', gaps: [[0, 48]] }
      ],
      left: { label: '投 3 家半导体方向（25 分钟）', why: '课 14 小时，30 分钟的整块只有周三一处，被"改简历"占了；这一件原样没动，第二天滑出这一周。' }
    },
    {
      short: '第 7 周', label: '第 7 周 · 10 月 12–18 日', range: '10 月 12–18 日',
      note: '课更多（16 小时），但拆小之后反而排得进去了',
      lenses: {
        weight: '按这一天的轻重看：「课最多的一天」只有周二 —— 4 小时课还加一次 14:00–16:00 的重叠，一整天只剩上午 3.83 小时空档；「课不少的一天」三天各 4 小时课；「没课的一天」这一组是空的：这周七天全有课。',
        kind: '按占用类型看：「课占住的」4 天（周一、周二、周六、周日）、「必须交的」1 天（周四 10 月 15 日改简历）、「可以挪的」2 天（周三、周五）。硬的那一件在周四，其余都能再商量。',
        from: '按谁安排看：课 7 天来自教务系统，节点 1 天来自规划师，任务 4 天来自计划 —— 三类里只有第三类今天还能改。',
        time: '按时间位置看：周初（周一、周二）压着 0.67+0.33 小时的事，周中三天课最多，周末两天课少 —— 周六 0 小时、周日 2 小时，但那 2 小时是这周才有的实验室安全培训。'
      },
      days: [
        { ab: '一', dd: 12, cls: [[0, 12], [26, 38]], note: '材料分析方法 1–2 节 · 工程数学 5–6 节', state: '课 4 小时',
          gaps: [[12, 26], [38, 48]],
          tasks: [
            { label: '把简历第一页的封面表述改成"工艺方向"（15 分钟）', min: 15, gap: 0, at: 13 },
            { label: '找出 2 段能写进简历的课程项目（20 分钟）', min: 20, gap: 0, at: 15 },
            { label: '先投 1 家新能源方向的工艺岗（5 分钟）', min: 5, gap: 0, at: 17, moved: true }
          ] },
        { ab: '二', dd: 13, cls: [[12, 14], [34, 38]], overlap: '材料物理 3–4 节与专业英语 7–8 节之间只有 1 小时，这一天没有整块',
          note: '材料物理 周二 3–4 节 · 专业英语 周二 7–8 节（1–12 周）', state: '课 4 小时',
          gaps: [[0, 12], [14, 34], [38, 48]],
          tasks: [{ label: '找出 2 段能写进简历的课程项目（20 分钟）', min: 20, gap: 1, at: 14 }] },
        { ab: '三', dd: 14, cls: [[24, 48]], today: true, now: 14, overlap: '材料实验 与 创新项目讨论 7–8 节重叠',
          note: '材料实验 5–8 节 · 创新项目讨论 7–8 节（第 3–10 周）', state: '课 4 小时 · 今天', gaps: [[0, 24]],
          tasks: [{ label: '先投 1 家新能源方向的工艺岗（5 分钟）', min: 5, gap: 0, at: 2, moved: true }] },
        { ab: '四', dd: 15, cls: [[0, 12], [34, 38]], note: '半导体工艺概论 1–2 节 · 材料性能测试 5–6 节', state: '课 4 小时',
          gaps: [[12, 34], [38, 48]], ev: [{ at: 13, label: '完成简历修订（10 月 15 日的节点就是排给它的）' }] },
        { ab: '五', dd: 16, cls: [[24, 36]], note: '工程实践 周五 1–2 节', state: '课 2 小时',
          gaps: [[0, 24], [36, 48]],
          tasks: [{ label: '等中建某院结构岗的笔试结果（0 分钟，不占格）', min: 0, gap: 1, at: 36, wait: true }] },
        { ab: '六', dd: 17, cls: [], note: '职业发展工作坊第 5、9、13 周上课 —— 第 7 周没有', state: '课 0 小时', gaps: [[0, 48]] },
        { ab: '日', dd: 18, cls: [[0, 12]], note: '实验室安全培训 周日 1–2 节 · 只在第 7 周', state: '课 2 小时', gaps: [[12, 48]] }
      ]
    }
  ];

  function pad(n) { return n < 10 ? '0' + n : String(n); }
  function hhmm(slot) { var m = H0 * 60 + slot * STEP; return pad(Math.floor(m / 60)) + ':' + pad(m % 60); }
  function hOf(min) { return Math.round(min / 60 * 100) / 100; }
  function hh(min) { return (Math.round(min / 60 * 100) / 100) + 'h'; }
  function pct(v) { return (v / SLOTS * 100).toFixed(4) + '%'; }
  function blank() { var a = []; for (var k = 0; k < SLOTS; k++) a.push(''); return a; }

  /* 相邻同类格合成一个块：48 个格子最后只落成几个 div */
  function paint(slots) {
    var out = '', i = 0;
    while (i < slots.length) {
      var c = slots[i], j = i;
      while (j < slots.length && slots[j] === c) j++;
      if (c) out += '<i class="' + c + '" style="left:' + pct(i) + ';width:' + pct(j - i) + '"></i>';
      i = j;
    }
    return out;
  }

  function calc(d) {
    var cls = blank(), task = blank(), gap = blank(), i, k;
    d.cls.forEach(function (r) { for (k = r[0]; k < r[1]; k++) cls[k] = 'c'; });
    d.gaps.forEach(function (r) { for (k = r[0]; k < r[1]; k++) gap[k] = 'g'; });
    (d.tasks || []).forEach(function (t, ti) {
      if (!t.min) return;
      var from = t.at, to = t.at + Math.round(t.min / STEP);
      for (k = from; k < to && k < SLOTS; k++) task[k] = 't' + (t.moved ? ' moved' : '') + (t.paused ? ' paused' : '') + (t.missed ? ' missed' : '');
      t._i = ti;
    });
    var g = d.gaps.reduce(function (a, r) { return a + (r[1] - r[0]); }, 0);
    var busy = (d.tasks || []).reduce(function (a, t) { return a + (t.paused ? 0 : t.min); }, 0);
    /* 一天占住的小时 = 课 ∪ 任务（并集，不重复计） */
    var occ = blank();
    d.cls.forEach(function (r) { for (k = r[0]; k < r[1]; k++) occ[k] = 1; });
    (d.tasks || []).forEach(function (t) { if (!t.min) return; for (k = t.at; k < t.at + Math.round(t.min / STEP) && k < SLOTS; k++) occ[k] = 1; });
    d.ev && d.ev.forEach(function (e) { occ[e.at] = 1; });
    var occN = occ.reduce(function (a, v) { return a + (v ? 1 : 0); }, 0);
    return {
      cls: cls, task: task, gap: gap,
      clsMin: d.cls.reduce(function (a, r) { return a + (r[1] - r[0]) * STEP; }, 0),
      taskMin: (d.tasks || []).reduce(function (a, t) { return a + t.min; }, 0),
      busy: busy,
      gapSlots: g,
      free: g * STEP - busy,
      occH: occN * STEP / 60,
      paused: (d.tasks || []).some(function (t) { return t.paused; })
    };
  }

  C2.onView('schedule', function () {
    var root = document.querySelector('[data-view="schedule"]');
    if (!root) return;

    var weekEl = document.getElementById('scWeek');
    var dayHost = document.getElementById('scDayList');
    var lensBox = root.querySelector('.lens');
    var lensItems = lensBox ? lensBox.querySelector('.lens__items') : null;
    var weekLabel = document.getElementById('scWeekLabel');
    var trackN = document.getElementById('scFillN');
    var stateEl = document.getElementById('scState');
    var cur = 2;

    /* ---- 一条轴：空档斜纹 → 课实心 → 硬截止红线 → 任务虚线条 --------------
       四层叠在同一条 8 小时上，顺序就是"谁压着谁"。 */
    function track(d) {
      var m = calc(d);
      return '<div class="sc-track" data-sc-track="' + d.dd + '">' +
        '<div class="sc-fill sc-fill--g" aria-hidden="true">' + paint(m.gap) + '</div>' +
        '<div class="sc-fill sc-fill--c" aria-hidden="true">' + paint(m.cls) + '</div>' +
        (d.ev || []).map(function (e) {
          return '<div class="sc-fill sc-fill--d" aria-hidden="true"><i style="left:' + pct(e.at) + '"></i></div>';
        }).join('') +
        '<div class="sc-fill sc-fill--t' + (m.paused ? ' paused' : '') + '" data-sc-zone>' + paint(m.task) + '</div>' +
        (d.now === undefined ? '' : '<span class="sc-now" style="left:' + pct(d.now) + '" aria-hidden="true"></span>') +
        '</div>';
    }

    function taskLines(d, m) {
      if (!(d.tasks || []).length) return d.note2 || '没有排任务 —— 不是空着，是这类没占';
      return d.tasks.map(function (t) {
        return t.label +
          (t.paused ? ' <span class="conf conf--stale"><i aria-hidden="true"></i>暂停了</span>' : '') +
          (t.moved ? ' <span class="src src--chat"><span class="src__ic" aria-hidden="true"></span><span class="src__k">顾问刚拆的</span><span class="src__w">25 分钟 → 5 分钟</span></span>' : '') +
          (t.wait ? ' <span class="conf conf--reported"><i aria-hidden="true"></i>等结果</span>' : '') +
          (t.partial ? ' <span class="conf conf--inferred"><i aria-hidden="true"></i>只做了一部分</span>' : '') +
          (t.missed ? ' <span class="conf conf--conflict"><i aria-hidden="true"></i>没做</span>' : '');
      }).join('<br>');
    }

    function card(d, w, i) {
      var m = calc(d);
      var weight = m.clsMin === 0 ? '没课的一天'
        : m.clsMin <= 120 ? '课少的一天'
        : m.clsMin < 240 ? '课不少的一天' : '课最多的一天';
      var kind = (d.ev || []).length ? '必须交的'
        : ((d.tasks || []).length && m.clsMin < 240) ? '可以挪的' : '课占住的';
      var from = (d.ev || []).length ? '规划师写的节点'
        : ((d.tasks || []).length && m.clsMin < 240) ? '计划拆下来的' : '学校课表';
      var slot = d.dd <= 13 ? '周初' : (d.dd <= 16 ? '周中' : '周末');
      var evTxt = (d.ev || []).length
        ? d.ev.map(function (e) { return e.label + ' —— ' + hhmm(e.at) + ' 这一刻'; }).join('<br>')
        : '无 —— 这一天没有硬点，卡住它的是课';
      var full = m.gapSlots * STEP - m.busy <= 0;
      return '<article class="lens__item sc-daycard"' +
        ' data-weight="' + weight + '" data-kind="' + kind + '" data-from="' + from + '" data-time="' + slot + '"' +
        (d.today ? ' data-today="true"' : '') + '>' +
        '<div class="sc-daycard__h">' +
          '<span class="sc-daycard__d">' + WD[i] + ' · 10 月 ' + d.dd + ' 日' + (d.today ? ' · 今天' : '') + '</span>' +
          '<span class="sc-daycard__n">课 ' + hh(m.clsMin) + ' · 事 ' + hh(m.taskMin) + ' · 空档 ' + hh(m.free) + '</span>' +
        '</div>' +
        track(d) +
        '<div class="sc-daycard__b">' +
          '<div class="sc-daycard__g"><p class="sc-daycard__k">课（固定）</p><p class="sc-daycard__v">' + d.note +
            (d.overlap ? '<br><span class="conf conf--conflict"><i aria-hidden="true"></i>' + d.overlap + '</span>' : '') + '</p></div>' +
          '<div class="sc-daycard__g"><p class="sc-daycard__k">截止（硬）</p><p class="sc-daycard__v">' + evTxt + '</p></div>' +
          '<div class="sc-daycard__g"><p class="sc-daycard__k">任务（可挪）</p><p class="sc-daycard__v">' + taskLines(d, m) + '</p></div>' +
        '</div>' +
        (full ? '<p class="sc-daycard__f">这一天整块被占满：空档 ' + hh(m.free) + '，排不进新东西</p>' : '') +
        '</article>';
    }

    function render() {
      var w = WEEKS[cur];
      if (weekLabel) weekLabel.textContent = w.label;
      if (lensBox) {
        lensBox.setAttribute('data-selected-week', String(cur));
        Object.keys(w.lenses).forEach(function (k) { lensBox.setAttribute('data-hint-' + k, w.lenses[k]); });
      }

      /* 7 个格子：课量条与任务条同一刻度 —— 课长的那些天，事那条就短 */
      var maxCls = 0, maxTask = 0;
      w.days.forEach(function (d) { var m = calc(d); if (m.clsMin > maxCls) maxCls = m.clsMin; if (m.taskMin > maxTask) maxTask = m.taskMin; });
      if (weekEl) {
        weekEl.innerHTML = w.days.map(function (d, i) {
          var m = calc(d);
          var full = m.gapSlots * STEP - m.busy <= 0;
          return '<div class="sc-dc"' + (d.today ? ' data-today="true"' : '') + '>' +
            '<p class="sc-dc__d">' + (d.today ? '今天 · ' : '') + d.ab + ' ' + d.dd + ' 日</p>' +
            '<p class="sc-dc__h">' + d.state + '</p>' +
            '<div class="sc-dc__bars" aria-hidden="true">' +
              '<span class="sc-bar sc-bar--c"><i style="width:' + (maxCls ? (m.clsMin / maxCls * 100).toFixed(1) : 0) + '%"></i></span>' +
              '<span class="sc-bar sc-bar--t"><i style="width:' + (maxTask ? (m.taskMin / maxTask * 100).toFixed(1) : 0) + '%"></i></span>' +
            '</div>' +
            '<p class="sc-dc__m">' + (full ? '满' : '空档 ' + hh(m.free)) + '</p>' +
            '</div>';
        }).join('');
      }

      if (dayHost) dayHost.innerHTML = w.days.map(function (d, i) { return card(d, w, i); }).join('');
      if (lensItems) {
        C2.lens(root);
      }

      /* 页头那行账由 DOM 现算：数字不对就是数据不对，不是文案不对 */
      var clsSum = 0, taskSum = 0, fullDays = 0, pausedDays = 0;
      w.days.forEach(function (d) {
        var m = calc(d);
        clsSum += m.clsMin; taskSum += m.taskMin;
        if (m.gapSlots * STEP - m.busy <= 0) fullDays++;
        if (m.paused) pausedDays++;
      });
      if (trackN) trackN.textContent = '课 ' + (clsSum / 60) + ' 小时 · 事 ' + hOf(taskSum) + ' 小时';
      if (stateEl) {
        stateEl.textContent = w.short + '：课 ' + (clsSum / 60) + ' 小时、任务 ' + hOf(taskSum) + ' 小时；' +
          (fullDays ? fullDays + ' 天整块被占满' : '没有一天被占满') +
          (pausedDays ? '，' + pausedDays + ' 天里的任务被你暂停了' : '') + '。' + w.note + '。';
      }
      if (w.left && w.left.length) {
        var leftTxt = w.left[0];
        var box = root.querySelector('[data-sc-post="leftovers"]');
        if (box) {
          box.setAttribute('data-sc-post', 'left');
          var t = box.querySelector('.sc-post__t');
          if (t) t.textContent = leftTxt.label;
          var dd = box.querySelector('.sc-post__d');
          if (dd) dd.textContent = leftTxt.why;
        }
      }
      Array.prototype.forEach.call(root.querySelectorAll('.sc-weekbtn'), function (b) {
        b.setAttribute('aria-selected', String(Number(b.getAttribute('data-sc-week')) === cur - 2));
      });
    }

    function setWeek(i, quiet) {
      var n = Math.max(0, Math.min(WEEKS.length - 1, i));
      var changed = n !== cur;
      cur = n;
      render();
      if (!quiet && changed) {
        var cls = WEEKS[cur].days.reduce(function (a, d) { return a + calc(d).clsMin; }, 0) / 60;
        C2.toast('已切到' + WEEKS[cur].short + '：课 ' + cls + ' 小时，比上一周' + (cur === 1 ? '多 10 小时' : cur === 2 ? '多 2 小时' : '少 12 小时'));
      }
    }

    /* ---- 换周 --------------------------------------------------------------- */
    Array.prototype.forEach.call(root.querySelectorAll('[data-sc-week]'), function (b) {
      b.addEventListener('click', function () { setWeek(cur + Number(b.getAttribute('data-sc-week'))); });
    });
    Array.prototype.forEach.call(root.querySelectorAll('[data-sc-jump]'), function (b) {
      b.addEventListener('click', function () {
        setWeek(2, true);
        Array.prototype.forEach.call(root.querySelectorAll('[data-sc-today]'), function (el) { el.classList.add('sc-month__d--hit'); });
        C2.toast('回到今天：10 月 14 日，第 7 周 · 周三');
      });
    });

    /* ---- 点任务块：暂停 / 恢复。
       反馈是即时且连锁的：空出来的那一段立刻回到空档（斜纹），上面的账重算，
       卡片脚下那句"排不进新东西"也跟着出现或消失。 */
    if (lensBox) lensBox.addEventListener('click', function (e) {
      var zone = e.target.closest ? e.target.closest('.sc-fill--t') : null;
      if (!zone || !zone.querySelector('i')) return;
      var trackEl = zone.closest('[data-sc-track]');
      var dd = trackEl ? Number(trackEl.getAttribute('data-sc-track')) : 0;
      var d = null;
      WEEKS[cur].days.forEach(function (x) { if (x.dd === dd) d = x; });
      if (!d || !(d.tasks || []).length) return;
      var paused = d.tasks.some(function (t) { return t.paused; });
      if (paused) d.tasks.forEach(function (t) { t.paused = false; });
      else d.tasks[0].paused = true;
      render();
      C2.toast(paused ? '已恢复：这一天的任务重新占住那一段' : '已暂停：空出来的那一段回到空档，空档与账都重算了一遍');
    });

    /* ---- 报一个占用：写进对话页的输入框（和画像页同一个落点） -------------- */
    Array.prototype.forEach.call(root.querySelectorAll('[data-sc-ask]'), function (b) {
      b.addEventListener('click', function () {
        var text = '周三 7–8 节材料实验和创新项目讨论重叠了，我该按哪边排？';
        var msg = document.getElementById('msg');
        if (msg) { msg.value = text; msg.dispatchEvent(new Event('input')); }
        C2.toast('已写进对话输入框：' + text);
      });
    });

    /* ---- 冲突 / 待定：处理后卡上的角标与侧栏的去向同时变 ------------------- */
    Array.prototype.forEach.call(root.querySelectorAll('[data-sc-resolve]'), function (b) {
      b.addEventListener('click', function () {
        var k = b.getAttribute('data-sc-resolve');
        var cardEl = root.querySelector('[data-sc-fix="' + k + '"]');
        if (cardEl) {
          cardEl.setAttribute('data-resolved', 'true');
          var out = cardEl.querySelector('[data-sc-fixout]');
          if (out) out.textContent = k === 'conflict'
            ? '已按"材料实验优先"暂定；创新项目讨论这 8 周按缺勤记 —— 仍然建议去问一次能不能换时段'
            : '已记下"等我确认周次"：参访那天整块要让出来，任务会再挪一次';
          var badge = cardEl.querySelector('.sc-fix__badge');
          if (badge) badge.textContent = '已处理 · 明天生效';
        }
        C2.toast(k === 'conflict' ? '已暂定为材料实验优先，冲突少了一处' : '已记下待确认：企业参访周次');
      });
    });

    setWeek(2, true);
  });
})();
