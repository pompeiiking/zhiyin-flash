/* =============================================================================
 * 岗位资讯 · 视图行为（把筛选做成真的会筛）
 * -----------------------------------------------------------------------------
 * 为什么需要这个文件：intel.html 的类别 chip / 热词 chip / 排序 chip / 清空筛选 /
 * 空态都是**可点的**，但上一个作者只被授权写 CSS，所以它们点了不动 ——
 * 页面看起来对、探针也全绿（无异常、无溢出），可"点了不筛"正是本项目最忌讳的那种
 * "看起来完成了"的假完成。这一页的落点②（组织权交给用户）必须是真的。
 *
 * 三条轴各自不同语义，所以三种形状（见 intel.css）：
 *   类别 chip  = 多选（并集）；「全部」= 清空类别
 *   热词 chip  = 多选（且集：每个词都要在正文里出现）
 *   排序 chip  = 互斥单选（相关度 / 什么时候用得上 / 类别）
 *
 * 与视角重组的配合：筛完必须调 C2.relens(view) —— 否则组头与组内条数还是筛前的数字
 * （引擎只对可见条目分组，`hidden` 的不参与，见 _src/app.js 的 live()）。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('intel', function () {
    var view = document.querySelector('[data-view="intel"]');
    if (!view) return;
    var host = view.querySelector('.lens__items');
    var cards = Array.prototype.slice.call(view.querySelectorAll('.int-card'));
    if (!host || !cards.length) return;

    var kindBtns = Array.prototype.slice.call(view.querySelectorAll('.chipf[data-int-kind]'));
    var hotBtns = Array.prototype.slice.call(view.querySelectorAll('.chipf[data-int-hot]'));
    var sortBtns = Array.prototype.slice.call(view.querySelectorAll('.chipf[data-int-sort]'));
    var echo = document.getElementById('intEcho');
    var countEl = document.getElementById('intCount');
    var empty = document.getElementById('intEmpty');
    var reset = document.getElementById('intReset');
    var onlyCareer = document.getElementById('intOnlyCareer');
    var emptyReset = document.getElementById('intEmptyReset');

    var state = { kinds: [], hots: [], sort: 'fit' };
    var SORT_NAME = { fit: '对你的相关度', when: '什么时候用得上', kind: '类别' };
    var FIT_RANK = {
      '直接对上主攻方向': 0,
      '用来比较两个方向': 1,
      '决定前必须核对': 2,
      '不影响现在的决定': 3
    };

    function textOf(el) { return (el.textContent || '').replace(/\s+/g, ' '); }

    function matches(el, kinds, hots) {
      if (kinds.length && kinds.indexOf(el.getAttribute('data-kind')) < 0) return false;
      for (var i = 0; i < hots.length; i++) {
        if (textOf(el).indexOf(hots[i]) < 0) return false;
      }
      return true;
    }

    function sortKeyOf(el, sort) {
      var idx = el.getAttribute('data-int-idx') || '';
      if (sort === 'fit') {
        var r = FIT_RANK[el.getAttribute('data-fit')];
        return (r === undefined ? 9 : r) + '-' + idx;
      }
      if (sort === 'when') return (el.getAttribute('data-when') || '') + '-' + idx;
      return (el.getAttribute('data-kind') || '') + '-' + idx;
    }

    function apply(silentMsg) {
      /* 1) 排序是真的改 DOM 顺序（不是只写个 data 属性）：先重排，再让引擎重组分组，
            这样组内顺序也跟着排序走。 */
      cards.slice().sort(function (a, b) {
        var ka = sortKeyOf(a, state.sort), kb = sortKeyOf(b, state.sort);
        return ka < kb ? -1 : ka > kb ? 1 : 0;
      }).forEach(function (el) { host.appendChild(el); });

      /* 2) 筛选 */
      var shown = 0;
      cards.forEach(function (el) {
        if (matches(el, state.kinds, state.hots)) { el.removeAttribute('hidden'); shown++; }
        else el.setAttribute('hidden', '');
      });

      /* 3) 视角重组按新的可见集合重算（组头与"N 条"跟着走） */
      C2.relens(view);

      /* 4) chip 上的数字 = 点它之后会剩下几条（所以数字本身就是"下一步会发生什么"） */
      kindBtns.forEach(function (b) {
        var k = b.getAttribute('data-int-kind');
        var n = cards.filter(function (el) {
          return matches(el, k === '全部' ? [] : [k], state.hots);
        }).length;
        var s = b.querySelector('small');
        if (s) s.textContent = String(n);
        b.setAttribute('aria-pressed', String(k === '全部' ? state.kinds.length === 0 : state.kinds.indexOf(k) >= 0));
      });
      hotBtns.forEach(function (b) {
        var w = b.getAttribute('data-int-hot');
        var on = state.hots.indexOf(w) >= 0;
        var next = on ? state.hots.filter(function (x) { return x !== w; }) : state.hots.concat([w]);
        var n = cards.filter(function (el) { return matches(el, state.kinds, next); }).length;
        var s = b.querySelector('small');
        if (s) s.textContent = String(n);
        b.setAttribute('aria-pressed', String(on));
      });
      sortBtns.forEach(function (b) {
        b.setAttribute('aria-pressed', String(b.getAttribute('data-int-sort') === state.sort));
      });

      /* 5) 回声与空态 */
      if (silentMsg) {
        if (echo) echo.textContent = silentMsg;
      } else if (echo) {
        var parts = [state.kinds.length ? '只看 ' + state.kinds.join('、') : '不限类别'];
        if (state.hots.length) parts.push('正文里有「' + state.hots.join('」且「') + '」');
        parts.push('排序按' + SORT_NAME[state.sort]);
        echo.textContent = parts.join(' · ') + '：剩下 ' + shown + ' 条。分组头与 chip 上的数字都跟着变了。';
      }
      if (countEl) countEl.textContent = shown + ' 条';
      if (empty) empty.hidden = shown > 0;
      return shown;
    }

    kindBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        var k = b.getAttribute('data-int-kind');
        if (k === '全部') {
          state.kinds = [];
        } else {
          var i = state.kinds.indexOf(k);
          if (i >= 0) state.kinds.splice(i, 1); else state.kinds.push(k);
        }
        apply();
      });
    });

    hotBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        var w = b.getAttribute('data-int-hot');
        var i = state.hots.indexOf(w);
        if (i >= 0) state.hots.splice(i, 1); else state.hots.push(w);
        apply();
      });
    });

    sortBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        state.sort = b.getAttribute('data-int-sort');
        apply();
      });
    });

    function clearAll(msg) {
      state.kinds = [];
      state.hots = [];
      state.sort = 'fit';
      apply(msg);
      C2.toast('筛选已清空，12 条全在。');
    }
    if (reset) reset.addEventListener('click', function () {
      clearAll('筛选已清空：12 条全在，排序回到按对你的相关度。');
    });
    if (emptyReset) emptyReset.addEventListener('click', function () {
      clearAll('筛选已清空：12 条全在。');
    });
    if (onlyCareer) onlyCareer.addEventListener('click', function () {
      var already = state.kinds.length === 1 && state.kinds[0] === '岗位示例';
      state.kinds = already ? [] : ['岗位示例'];
      state.hots = [];
      apply();
      C2.toast(already ? '取消「只看岗位示例」，12 条全在。' : '只看岗位示例：5 条。');
    });

    apply();
  });
})();
