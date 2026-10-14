/* =============================================================================
 * 复盘记录 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页的交互只做两件事，都对应「证据是怎么攒起来的」：
 *   1. 点结论 → 撑它的那几条复盘亮起来、其余退到后景，并把「靠几条、哪几条、
 *      各是什么状态」念出来（DESIGN-LANGUAGE §4.1 结构显形、§8 报告行）。
 *   2. 干预那两个按钮 → 它改的是哪一个条目、改完那一条现在算什么状态。
 * 反馈文字里的数字全程从 DOM 里**数出来**，不写死：数不对是数据不对。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('review', function () {
    var view = '[data-view="review"]';

    /* ---- 1 · 结论 ↔ 支撑它的那几条 ---------------------------------------- */
    var btn = document.getElementById('rvConcBtn');
    var echo = document.getElementById('rvConcEcho');

    function itemsByIds(list) {
      return list.map(function (id) { return document.getElementById(id); }).filter(Boolean);
    }

    function paint() {
      if (!btn) return;
      var on = btn.getAttribute('aria-pressed') === 'true';
      var ids = (btn.getAttribute('data-rv-from') || '').split(',').filter(Boolean);
      var hit = itemsByIds(ids);
      var all = Array.prototype.slice.call(document.querySelectorAll(view + ' .rv-item'));

      /* 全部条目按「是不是这条结论的支撑」分亮暗。这是用户点出来的连线，
         不是进页面自己演的 —— 加载时一条都不压暗。 */
      all.forEach(function (el) {
        var isHit = on && hit.indexOf(el) >= 0;
        el.setAttribute('data-hit', String(isHit));
        el.setAttribute('data-dim', String(on && !isHit));
      });

      if (!echo) return;
      if (!on) {
        echo.textContent = '这条结论现在还压着 ' + ids.length + ' 条复盘，没有一条撤掉。点上面的按钮，看它具体压在哪几条上。';
        return;
      }

      var whens = [], stats = {};
      hit.forEach(function (el) {
        whens.push(el.getAttribute('data-rv-when') || '');
        var st = el.getAttribute('data-rv-st') || '未标状态';
        stats[st] = (stats[st] || 0) + 1;
      });
      var mix = Object.keys(stats).map(function (k) { return stats[k] + ' 条' + k; }).join('、');

      /* 这几句是从上面数出来的固定事实，不是模板填空 —— 数字对不上就该改数据。 */
      var tail;
      if (stats['没做']) {
        tail = '唯一没做的那一条给的归因是「任务太大」，所以结论不写「你不自律」' +
               '（归因只在 任务太大 / 方法不对 / 方向要重估 里选一个，不归到人）。';
      } else if (stats['做了一部分']) {
        tail = '有一条只做了一部分，所以结论里那句「不是你不自律」也含它。';
      } else {
        tail = '四条都是完成，所以「有 3 天动了手」这句话本身是稳的。';
      }

      echo.innerHTML = '「这一周你有 3 天动了手」现在靠 <b>' + hit.length + ' 条</b>撑着：' +
        whens.join('、') + '（' + mix + '）。' + tail;
    }

    if (btn) {
      btn.setAttribute('aria-pressed', 'false');
      btn.addEventListener('click', function () {
        btn.setAttribute('aria-pressed', String(btn.getAttribute('aria-pressed') !== 'true'));
        paint();
      });
      paint();
    }

    /* ---- 2 · 干预：改的是哪一条、改完算什么状态 --------------------------- */
    var interHint = document.getElementById('rvInterHint');
    var accept = document.querySelector(view + ' [data-rv-accept]');
    var defer = document.querySelector(view + ' [data-rv-defer]');
    var nextBtn = document.getElementById('rvNextAdd');

    if (accept) accept.addEventListener('click', function () {
      var row = document.getElementById('rvRow1006');
      var st = row ? row.querySelector('.rv-st') : null;
      if (st) {
        st.className = 'rv-st rv-st--partial';
        st.textContent = '已改口径 · 进行中';
      }
      if (interHint) {
        interHint.textContent = '「投 3 家半导体方向」已经改成「先投 1 家（5 分钟）」。原条目没有删掉，' +
          '在计划里标成「已改口径」留着 —— 改过什么要留痕。做完之前它不算完成。';
      }
      C2.toast('已改成「先投 1 家（5 分钟）」，原条目留痕');
    });

    if (defer) defer.addEventListener('click', function () {
      if (interHint) {
        interHint.textContent = '这一条按「这周先缓一缓」收下，同一条 48 小时内不会再开口。' +
          '「投 3 家」那一条还挂在计划里，没有消失，也没有被算成完成。';
      }
      C2.toast('这一条先收下，48 小时内不再提', 'warn');
    });

    if (nextBtn) nextBtn.addEventListener('click', function () {
      C2.toast('已记进下次复盘：先看「先投 1 家（5 分钟）」动没动');
    });

    /* ---- 其余动作：演示样张，说清会发生什么，不假装真的执行 -------------- */
    var map = {
      rvAdd: '演示样张：这里会新开一条复盘，先让你填「原计划 / 实际 / 原因」，再落进这四条上面。',
      rvExport: '演示样张：导出的是一份只读记录，给你自己或顾问看，不会外发。'
    };
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('click', function () { C2.toast(map[id]); });
    });
  });
})();
