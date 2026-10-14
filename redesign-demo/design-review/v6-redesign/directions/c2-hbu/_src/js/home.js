/* =============================================================================
 * 今日行动 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页只做一件事：让"勾掉一件"**连锁**起来。
 * 上一轮的病是"勾掉一件事得到零反馈"（HANDOFF §4.2 共性问题 2），
 * 所以这里的反馈不是弹一句话就完了 —— 一次勾选同时改四处，且每一处都能被量出来：
 *
 *   1. .meter 的那一段亮起来（位置 = 那件事在今天的第几件）
 *   2. 剩余时间重算（只算"要动手"的，等结果的不进去）
 *   3. 下一件浮出：下一张卡得到 data-hm-next="true" + 徽标「下一件」，
 *      其余的退到后景。**不隐藏** —— 隐藏了信息就丢了，静图截不出来。
 *   4. 复盘留痕：这条在 10 月 6 日/10 月 5 日的复盘里是什么结果，勾掉之后怎么说
 *
 * 数字全部**从 DOM 里算**，不是写死的：卡片上的 data-hm-min / data-hm-done 是唯一
 * 事实来源。文案里的数字对不上，是数据不对，不是文案不对（样板页 profile.js 的同一套做法）。
 *
 * 不用 C2.onView 绑定：#pmInit 保证只绑一次，重复调用只重算一遍状态 ——
 * 因为预览文件（build.mjs --only home）里没有对话页，来回切视图不该把监听器叠起来。
 * ========================================================================== */
(function () {
  'use strict';

  var MIN = {
    t2: '这条在 10 月 6 日的复盘里是"没做"，归因写在任务太大 —— 现在它标记成完成了，复盘里会多一条"已完成"，归因栏留空（完成不写归因）。',
    t1: '这条 10 月 5 日是"做了一部分"，归因是方法不对。勾掉之后，复盘里那一格会从"做了一部分"翻成"完成"，并解锁里程碑「完成简历修订并满足申请要求」的下一档。',
    t3: '这是顾问加进来的一条，复盘里原本没有它。勾掉之后它会出现在复盘的新记录里，同时给里程碑「完成简历修订并满足申请要求」补上第二条证据。',
    t4: '5 分钟问一次，不做也不影响本周进度。勾掉之后只改"今天动了几件"，不会动任何一个里程碑 —— 顾问把它放进来是为了让你少走一次弯路，不是为了凑数。',
    t7: '这一条 9 月 20 日就做完了。撤销它，今天会多出 5 分钟，而"每周 6 小时"这个上限会退回到未确认状态 —— 计划里所有时长都按它算，所以这里要慎重。'
  };

  function num(el, attr) {
    var v = parseInt(el.getAttribute(attr), 10);
    return isNaN(v) ? 0 : v;
  }

  function boot() {
    var root = document.querySelector('[data-view="home"]');
    if (!root) return false;

    var rows = Array.prototype.slice.call(root.querySelectorAll('[data-hm-id]'));
    var segs = Array.prototype.slice.call(root.querySelectorAll('[data-hm-seg]'));
    var state = document.getElementById('hmState');
    var liveN = document.getElementById('hmLiveN');
    var trace = document.getElementById('hmTrace');
    var meter = document.getElementById('hmMeter');
    var leftBig = document.getElementById('hmLeftBig');
    var leftD = document.getElementById('hmLeftD');
    if (!rows.length) return false;

    function isDone(row) { return row.getAttribute('data-hm-done') === 'true'; }
    function labelOf(row) {
      var t = row.querySelector('.hm-t__t') || row.querySelector('.hm-card__t');
      return t ? t.textContent.replace(/\s+/g, ' ').trim() : '这一件';
    }

    /* 渲染：从 DOM 算出现在这条线走到哪，然后一次性铺到四个落点上。 */
    function paint(changedId) {
      var done = rows.filter(isDone);
      var open = rows.filter(function (r) { return !isDone(r); });
      var leftMin = open.reduce(function (n, r) { return n + num(r, 'data-hm-min'); }, 0);
      var total = rows.reduce(function (n, r) { return n + num(r, 'data-hm-min'); }, 0);
      var next = open[0] || null;

      /* ① 进度条：一段 = 一件，位置就是它今天排第几 */
      segs.forEach(function (s) {
        var row = rows.filter(function (r) { return r.getAttribute('data-hm-id') === s.getAttribute('data-hm-seg'); })[0];
        if (row && isDone(row)) s.classList.add('on');
        else s.classList.remove('on');
      });
      if (meter) {
        meter.setAttribute('aria-label', '今天 ' + rows.length + ' 件里已完成 ' + done.length + ' 件，' + done.length + ' 段亮起');
      }
      if (liveN) liveN.textContent = done.length + ' / ' + rows.length;

      /* ② 剩余时间重算 */
      if (leftBig) leftBig.textContent = String(leftMin);
      if (leftD) {
        leftD.textContent = rows.length + ' 件里 ' + done.length + ' 件做完，' +
          done.length + ' 段已亮。这个数字只有勾掉或撤销的时候才会变 —— 它算的是"还剩多少要动手的时间"，' +
          '等结果的那一条不进去（全做完是 ' + total + ' 分钟）。';
      }

      /* ③ 下一件浮出：一张卡拿到"下一件"，其余的退到后景（不隐藏） */
      rows.forEach(function (r) {
        var isNext = r === next;
        r.setAttribute('data-hm-next', String(isNext));
        r.setAttribute('data-hm-busy', String(!isNext && !isDone(r)));
        var badge = r.querySelector('[data-hm-badge]');
        if (!badge) return;
        if (isNext) badge.textContent = '下一件';
        else if (isDone(r)) badge.textContent = '已完成';
        else badge.textContent = '排在第 ' + (rows.indexOf(r) + 1) + ' 件';
      });

      /* 勾选按钮的字与状态 */
      rows.forEach(function (r) {
        var btn = root.querySelector('[data-hm-toggle="' + r.getAttribute('data-hm-id') + '"]');
        if (!btn) return;
        var d = isDone(r);
        btn.setAttribute('aria-pressed', String(d));
        var lab = btn.querySelector('[data-hm-btnlabel]');
        if (lab) lab.textContent = d ? '撤销' : (r.classList.contains('hm-card') ? '做完了，勾掉' : '勾掉');
      });

      /* 状态句 */
      if (state) {
        if (!open.length) {
          state.innerHTML = '今天排的 ' + rows.length + ' 件都做完了（共 ' + total + ' 分钟）。' +
            '里程碑「申请 15 个岗位」只走到 3 家 —— 要不要从明天的空档里再排一件，去阶段计划里挑。';
        } else if (!done.length) {
          state.textContent = '已经做完 0 件，还有 ' + leftMin + ' 分钟要动。下一件：' + labelOf(next) + '。';
        } else {
          state.innerHTML = '已经做完 <b>' + done.length + ' 件</b>，还有 <b>' + leftMin + ' 分钟</b>要动。下一件：' + labelOf(next) + '。';
        }
      }

      /* ④ 复盘留痕：说清这一勾在别处留下了什么 */
      if (trace && changedId && MIN[changedId]) {
        var row = rows.filter(function (r) { return r.getAttribute('data-hm-id') === changedId; })[0];
        trace.textContent = (row && isDone(row) ? '已勾掉：' : '已撤销：') + MIN[changedId];
      }
    }

    function toggle(id, silent) {
      var row = rows.filter(function (r) { return r.getAttribute('data-hm-id') === id; })[0];
      if (!row) return;
      var willBeDone = !isDone(row);
      row.setAttribute('data-hm-done', String(willBeDone));
      paint(id);

      if (silent) return;
      var open = rows.filter(function (r) { return !isDone(r); });
      var leftMin = open.reduce(function (n, r) { return n + num(r, 'data-hm-min'); }, 0);
      if (willBeDone) {
        var msg = '已完成 ' + labelOf(row) + ' · ' + num(row, 'data-hm-min') + ' 分钟';
        msg += open.length
          ? '｜还剩 ' + open.length + ' 件 · ' + leftMin + ' 分钟｜下一件：' + labelOf(open[0])
          : '｜今天排的 ' + rows.length + ' 件都做完了';
        if (window.C2 && window.C2.toast) window.C2.toast(msg);
      } else if (window.C2 && window.C2.toast) {
        window.C2.toast('已撤销「' + labelOf(row) + '」，它回到今天的队列里');
      }
    }

    /* 勾选：按钮上的点击不冒泡到整卡，避免点了"直接开聊"又顺手改了状态 */
    rows.forEach(function (r) {
      var id = r.getAttribute('data-hm-id');
      var btn = root.querySelector('[data-hm-toggle="' + id + '"]');
      if (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          toggle(id);
        });
      }
    });

    /* 直接开聊：把这条任务的问题写进对话输入框，再切过去。
       文案取自场景数据里大三的 taskCards（data-hm-ask 原样写在标记里）——
       这条入口在源数据里没有对应字段，边界见 DEMO-DATA 第十二节 #12。 */
    Array.prototype.forEach.call(root.querySelectorAll('[data-hm-ask]'), function (b) {
      b.addEventListener('click', function (e) {
        e.preventDefault();
        var text = b.getAttribute('data-hm-ask');
        var msg = document.getElementById('msg');
        if (msg) {
          msg.value = text;
          msg.dispatchEvent(new Event('input'));
        }
        if (window.C2) {
          window.C2.show('chat');
          window.C2.toast('已写进对话输入框：' + text);
        }
        if (msg) setTimeout(function () { msg.focus(); }, 60);
      });
    });

    paint(null);
    return true;
  }

  if (!window.__hmInit) {
    window.__hmInit = true;
    if (!boot() && window.C2 && window.C2.onView) window.C2.onView('home', function () { boot(); });
  } else {
    boot();
  }
})();
