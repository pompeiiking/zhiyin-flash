/* =============================================================================
 * 阶段计划 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页的交互只做一件事：**让"里程碑 ↔ 任务"的对应关系显形**
 * （BRIEF 第五节给了显式对应表，不按标题猜）：
 *   m-j1→t1,t3 · m-j2→t2,t4 · m-j3→t5 · t6,t7,t8 不挂里程碑
 *
 * 两个入口，同一份筛选：
 *   · 里程碑那一段上的「挂 2 条任务」→ 下面的任务区只留那一段的
 *   · 任务区上面的一排 chip（全部 / 第 1 步 / 第 2 步 / 第 3 步 / 不挂里程碑）
 * 两处必须联动，否则用户点完上面、下面没反应，等于没做。
 *
 * 上一轮的病是"21 处折叠、嵌套 3 层"。所以这里**没有折叠**：
 * 筛选是"藏起来"，不是"折起来" —— 一行字说清现在显示了几条、其他几条去哪了。
 * ========================================================================== */
(function () {
  'use strict';

  var LABEL = {
    all: '全部',
    'm-j1': '第 1 步「完成简历修订并满足申请要求」',
    'm-j2': '第 2 步「申请 15 个岗位」',
    'm-j3': '第 3 步「获得 2 次面试机会」',
    none: '不挂里程碑'
  };

  function boot() {
    var root = document.querySelector('[data-view="plan"]');
    if (!root) return false;

    var tasks = Array.prototype.slice.call(root.querySelectorAll('.pl-task'));
    var chips = Array.prototype.slice.call(root.querySelectorAll('[data-pl-filter]'));
    var msBtns = Array.prototype.slice.call(root.querySelectorAll('[data-pl-focus]'));
    var out = document.getElementById('plFilterN');
    var lensN = document.getElementById('plLensN');
    if (!tasks.length) return false;

    function apply(key) {
      var shown = 0;
      tasks.forEach(function (t) {
        var on = key === 'all' || t.getAttribute('data-pl-ms-of') === key;
        t.setAttribute('data-pl-hidden', String(!on));
        if (on) shown++;
      });

      chips.forEach(function (c) {
        c.setAttribute('aria-pressed', String(c.getAttribute('data-pl-filter') === key));
      });
      msBtns.forEach(function (b) {
        b.setAttribute('aria-pressed', String(b.getAttribute('data-pl-focus') === key));
      });

      if (out) {
        out.textContent = key === 'all'
          ? '显示全部 ' + tasks.length + ' 条'
          : '只显示 ' + LABEL[key] + ' 的 ' + shown + ' 条（其余 ' + (tasks.length - shown) + ' 条还在，点「全部」就回来）';
      }
      if (lensN) lensN.textContent = key === 'all' ? tasks.length + ' 条' : shown + ' / ' + tasks.length + ' 条';
    }

    chips.forEach(function (c) {
      c.addEventListener('click', function () {
        var key = c.getAttribute('data-pl-filter');
        apply(key);
        if (window.C2 && window.C2.toast) {
          C2.toast(key === 'all' ? '已显示全部 ' + tasks.length + ' 条任务' : '只留下 ' + LABEL[key] + ' 的任务');
        }
      });
    });

    msBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        var key = b.getAttribute('data-pl-focus');
        var thenAll = b.getAttribute('aria-pressed') === 'true';
        apply(thenAll ? 'all' : key);
        if (window.C2 && window.C2.toast) {
          C2.toast(thenAll ? '已取消筛选，显示全部任务' : '只留下这一步挂着的任务');
        }
        if (!thenAll) {
          var host = document.getElementById('plItems');
          if (host && host.scrollIntoView) host.scrollIntoView({ block: 'nearest' });
        }
      });
    });

    apply('all');
    return true;
  }

  if (!window.__plInit) {
    window.__plInit = true;
    if (!boot() && window.C2 && window.C2.onView) window.C2.onView('plan', function () { boot(); });
  } else {
    boot();
  }
})();
