/* =============================================================================
 * 待办与目标 · 视图行为
 * -----------------------------------------------------------------------------
 * 两条线：
 *   A. **勾掉一条 ≠ 弹一句话**（上一轮的病："勾掉一件事得到零反馈"）
 *      一次勾选同时改四处，全部能从这里读出来：
 *         1. 三个实时计数（目标还没做 / 待办还没做 / 已完成）
 *         2. #ntImpact 写清"它动了哪里、缺口补上没有"（文案取自那一行的 data-nt-impact）
 *         3. 侧栏 #ntNext 换成下一个浮上来的条目
 *         4. 侧栏 #ntTrace 写它在复盘里留下什么（data-nt-trace）
 *      data-nt-impact / data-nt-trace 写在标记里，一条一句 —— 因为它讲的是
 *      "这一条独有的后果"，模板算不出来（计数、下一件那两处是算出来的）。
 *
 *   B. **顾问建议的 3 条要能被"加入"**
 *      「加入我的清单」把那一行从"建议"区挪进"自己写的"清单：状态保持未完成，
 *      计数进"待办还没做"，#ntSugN 变成"已加入 N"。这是"要不要加，你定"的落点，
 *      不是装饰按钮。
 *
 * 计数全部按 data-nt-kind / data-nt-done 从 DOM 算，不写死。
 * ========================================================================== */
(function () {
  'use strict';

  function boot() {
    var root = document.querySelector('[data-view="notes"]');
    if (!root) return false;

    var rows = Array.prototype.slice.call(root.querySelectorAll('[data-nt-id]'));
    var own = rows.filter(function (r) { return r.getAttribute('data-nt-kind') !== 'sug'; });
    var sugs = rows.filter(function (r) { return r.getAttribute('data-nt-kind') === 'sug'; });
    var impact = document.getElementById('ntImpact');
    var traceO = document.getElementById('ntTrace');
    var nextO = document.getElementById('ntNext');
    var impN = document.getElementById('ntImpN');
    var sugN = document.getElementById('ntSugN');
    var ownN = document.getElementById('ntOwnN');
    var goalN = document.getElementById('ntGoalN');
    var todoN = document.getElementById('ntTodoN');
    var doneN = document.getElementById('ntDoneN');
    var sugAddedN = document.getElementById('ntSugAddedN');
    if (!rows.length) return false;

    function titleOf(row) {
      var t = row.querySelector('.pick__title');
      return t ? t.textContent.replace(/\s+/g, ' ').trim() : '这一条';
    }
    function isDone(row) { return row.getAttribute('data-nt-done') === 'true'; }
    function kindOf(row) { return row.getAttribute('data-nt-kind'); }

    function counts() {
      var c = { goal: 0, todo: 0, done: 0, sugAdded: 0 };
      own.forEach(function (r) {
        if (isDone(r)) c.done++;
        else if (kindOf(r) === 'goal') c.goal++;
        else c.todo++;
      });
      sugs.forEach(function (r) { if (isDone(r)) c.sugAdded++; });
      return c;
    }

    function paint(changed) {
      var c = counts();

      if (goalN) goalN.textContent = String(c.goal);
      if (todoN) todoN.textContent = String(c.todo);
      if (doneN) doneN.textContent = String(c.done);
      if (sugAddedN) sugAddedN.textContent = String(c.sugAdded);
      if (ownN) ownN.textContent = own.length + ' 条 · 已完成 ' + c.done;
      if (sugN) sugN.textContent = sugs.length + ' 条 · 已加入 ' + c.sugAdded;

      /* 下一件：还没做的条目里，排在最前面的那一条（顺序 = 标记顺序 = "解锁什么"的排序） */
      var open = own.filter(function (r) { return !isDone(r); });
      if (nextO) {
        nextO.textContent = open.length ? titleOf(open[0]) : '这一轮 12 条都做完了 —— 去阶段计划挑下一步';
      }

      /* 条目上的勾选状态与标记 */
      own.forEach(function (r) {
        r.setAttribute('aria-checked', String(isDone(r)));
        var mark = r.querySelector('.conf--verified');
        if (!mark && isDone(r)) {
          var m = document.createElement('span');
          m.className = 'conf conf--verified';
          m.innerHTML = '<i aria-hidden="true"></i>已完成';
          var meta = r.querySelector('.pick__meta');
          if (meta) meta.appendChild(m);
        }
        if (mark && mark.textContent.indexOf('已完成') === 0 && !isDone(r)) mark.remove();
      });

      if (!changed) return;
      if (impN) impN.textContent = isDone(changed)
        ? '已勾 1 条 · 12 条里已完成 ' + c.done
        : '已撤销 1 条 · 12 条里已完成 ' + c.done;
    }

    rows.forEach(function (r) {
      r.addEventListener('click', function (e) {
        /* 行内的链接与"加入我的清单"按钮各自有动作，不在这里重复触发 */
        if (e.target.closest && (e.target.closest('a') || e.target.closest('[data-nt-add]'))) return;

        var wasDone = isDone(r);
        var next = !wasDone;
        r.setAttribute('data-nt-done', String(next));
        var impactText = r.getAttribute('data-nt-impact') || '';
        var traceText = r.getAttribute('data-nt-trace') || '';

        paint(r);

        var c = counts();
        var head = next ? '已勾掉「' + titleOf(r) + '」' : '已撤销「' + titleOf(r) + '」';
        if (impact) {
          impact.innerHTML = '<b>' + head + '</b>｜' + impactText +
            ' 现在：目标还没做 <b>' + c.goal + '</b> 条、待办还没做 <b>' + c.todo + '</b> 条、已完成 <b>' + c.done + '</b> 条。';
        }
        if (traceO) traceO.textContent = traceText;
        if (window.C2 && window.C2.toast) {
          window.C2.toast(next
            ? '已勾掉：' + titleOf(r) + '｜待办还没做 ' + c.todo + ' 条 · 下一件 ' + (open0() || '无')
            : '已撤销：' + titleOf(r));
        }
      });
    });

    function open0() {
      var open = own.filter(function (r) { return !isDone(r); });
      return open.length ? titleOf(open[0]) : '';
    }

    /* 顾问建议：加进自己的清单。它是"要不要加，你定"的落点。 */
    Array.prototype.forEach.call(root.querySelectorAll('[data-nt-add]'), function (b) {
      b.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var id = b.getAttribute('data-nt-add');
        var row = rows.filter(function (r) { return r.getAttribute('data-nt-id') === id; })[0];
        if (!row) return;
        var already = row.getAttribute('data-nt-done') === 'true';
        row.setAttribute('data-nt-done', 'true');
        b.disabled = true;
        b.textContent = '已加入';
        paint(row);
        var c = counts();
        if (impact) {
          impact.innerHTML = '<b>已把顾问的第 ' + id.slice(1) + ' 条建议加进你的清单</b>｜' + (row.getAttribute('data-nt-impact') || '') +
            ' 现在：目标还没做 <b>' + c.goal + '</b> 条、待办还没做 <b>' + c.todo + '</b> 条、顾问建议已加入 <b>' + c.sugAdded + '</b> 条。';
        }
        if (traceO) traceO.textContent = row.getAttribute('data-nt-trace') || '';
        if (window.C2 && window.C2.toast) {
          window.C2.toast(already ? '这条已经在你的清单里了' : '已加入你的清单：' + titleOf(row));
        }
      });
    });

    paint(null);
    return true;
  }

  if (!window.__ntInit) {
    window.__ntInit = true;
    if (!boot() && window.C2 && window.C2.onView) window.C2.onView('notes', function () { boot(); });
  } else {
    boot();
  }
})();
