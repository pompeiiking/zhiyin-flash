/* =============================================================================
 * 成长记录（achievements）· 视图行为
 * -----------------------------------------------------------------------------
 * 只做一件事：勾掉「今天就能做的那一件」→ 解锁进度推进、剩余件数重算、
 * 页头那句总览跟着变、并给一条即时反馈。
 *
 * 这是 BRIEF §2.1 明确鼓励的那一类动效 —— 它回答"这里发生了什么"
 * （一件条件被满足，未解锁的条目朝解锁走了一格），不是进场装饰：
 * 没有淡入、没有位移进场、没有数字滚动、没有粒子、没有自动播放。
 * 所有信息都写在标记的静态文字里，JS 不跑（或无 JS）时页面照样读得完整。
 * ========================================================================== */
(function () {
  'use strict';

  if (typeof window.C2 !== 'object' || !window.C2) return;

  var TOTAL = 5;   /* 5 件：实验写"方法" 1 件 + 城市 3 件 + 一句优先级 1 件 */

  function byAttr(sel) { return document.querySelector(sel); }

  function restText(rest) {
    if (rest <= 0) return '5 件都做完了 —— 三条记录会一起变成"记录已计入"。';
    if (rest === 1) return '还差最后 1 件。';
    return '还差 ' + rest + ' 件（其中 2 件合计约 10 分钟）。';
  }

  window.C2.onView('achievements', function () {
    var root = byAttr('.main > .main__scroll[data-active="true"]');
    if (!root) return;

    var picks = Array.prototype.slice.call(root.querySelectorAll('[data-ach-pick]'));
    if (!picks.length || root.getAttribute('data-ach-init') === 'true') return;
    root.setAttribute('data-ach-init', 'true');

    var live = root.querySelector('[data-ach-live]');
    var leftN = root.querySelector('[data-ach-left]');

    function apply() {
      var remaining = TOTAL;

      picks.forEach(function (btn, i) {
        var done = btn.getAttribute('data-done') === 'true';
        var key = btn.getAttribute('data-ach-step');
        var meter = root.querySelector('[data-ach-meter="' + key + '"]');
        var progress = root.querySelector('[data-ach-progress="' + key + '"]');

        if (done) remaining--;

        if (meter) {
          var segs = Array.prototype.slice.call(meter.querySelectorAll('i'));
          var on = done ? i + 1 : 0;                       /* 勾掉的是这一组第几件 */
          segs.forEach(function (s, k) { s.className = k < on ? 'on' : ''; });
          meter.setAttribute('aria-label', '解锁进度：3 件里已完成 ' + on + ' 件');
        }
        if (progress) {
          var on2 = done ? i + 1 : 0;
          var tpl = progress.getAttribute('data-ach-tpl');
          if (!tpl) { tpl = progress.textContent; progress.setAttribute('data-ach-tpl', tpl); }
          progress.textContent = tpl.replace(/已完成 \d+ \/ 3 件/, '已完成 ' + on2 + ' / 3 件');
        }
      });

      if (leftN) leftN.textContent = '解锁还差 ' + Math.max(remaining, 0) + ' 件';
      if (live) {
        var any = picks.some(function (b) { return b.getAttribute('data-done') === 'true'; });
        live.textContent = any
          ? '已勾掉「写方法」：实践证据的进度走到 1 / 3，' + restText(remaining)
          : '还没有勾。勾掉之后进度会立刻更新，也能再取消。';
        live.setAttribute('data-on', any ? 'true' : 'false');
      }
    }

    picks.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var next = btn.getAttribute('data-done') !== 'true';
        btn.setAttribute('data-done', String(next));
        btn.setAttribute('aria-pressed', String(next));
        apply();
        window.C2.toast(next ? '已记下：写方法（1 / 3）' : '已取消，进度退回 0 / 3');
      });
    });

    apply();   /* 初始化一次，保证 aria-label 与静态文字一致 */
  });

  /* 导出：真导出（写文件）是外壳能力，这里只给即时反馈，不假装写了文件 */
  window.C2.onView('achievements', function () {
    var root = byAttr('.main > .main__scroll[data-active="true"]');
    if (!root) return;
    var ex = root.querySelector('[data-ach-export]');
    if (!ex || ex.getAttribute('data-ach-bound') === 'true') return;
    ex.setAttribute('data-ach-bound', 'true');
    ex.addEventListener('click', function () {
      window.C2.toast('演示样张：导出动作到此为止，不生成文件', 'warn');
    });
  });
})();
