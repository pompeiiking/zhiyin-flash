/* =============================================================================
 * 提醒 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页的行为只做一件核心的事：**让"处理掉一条"这件事有落点、有连坐**。
 *   点「这事了了 / 标记完成」→ 卡片压暗划掉 → 移到下面「已处理」→
 *   队列计数 -1 → 页头徽标、列表计数、四块读数一起变 → toast 说出还剩几条。
 *   点「延后」→ 卡片虚线化 → 移到「稍后再说」→ 写明推到什么时候（不减少队列）。
 *   点「标为已读」→ 去掉未读，但**不**移出队列 —— 读过不等于办过。
 *
 * 所有数字都是从 DOM 里**算出来**的，不是写死的：数据改了数字自己会跟上，
 * 数字不对就是数据不对，不是文案不对。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('reminders', function () {
    var view = document.querySelector('[data-view="reminders"]');
    if (!view || view.getAttribute('data-rm-init') === 'true') return;
    view.setAttribute('data-rm-init', 'true');

    var cards = Array.prototype.slice.call(view.querySelectorAll('.rm-card'));
    var doneBox = view.querySelector('#rmDone');
    var doneList = view.querySelector('#rmDoneL');
    var laterBox = view.querySelector('#rmLater');
    var laterList = view.querySelector('#rmLaterL');
    var elQueued = view.querySelector('#rmQueued');
    var elNeed = view.querySelector('#rmStatNeed');
    var elUnread = view.querySelector('#rmStatUnread');
    var elLater = view.querySelector('#rmStatLater');
    var elDone = view.querySelector('#rmStatDone');
    var elListN = view.querySelector('#rmListN');

    /* 计数口径一处算完，三处显示共用它 —— 防止"徽标说 4、卡片说 5" */
    function counts() {
      var c = { queued: 0, need: 0, unread: 0, later: 0, done: 0 };
      cards.forEach(function (card) {
        var st = card.getAttribute('data-rm-state');
        if (st === 'done') { c.done++; return; }
        c.queued++;
        if (st === 'later') c.later++;
        if (st === 'unread' || st === 'later') c.unread++;
        if (card.getAttribute('data-need') === '1' && st !== 'done') c.need++;
      });
      return c;
    }

    function setNum(el, n) { if (el) el.textContent = String(n); }

    function paint() {
      var c = counts();
      setNum(elQueued, c.queued);
      setNum(elNeed, c.need);
      setNum(elUnread, c.unread);
      setNum(elLater, c.later);
      setNum(elDone, c.done);
      setNum(elListN, c.queued);
      /* 已处理 / 稍后再说两个盒子：空了就收起来，别留一个空壳 */
      if (doneBox) doneBox.hidden = c.done === 0;
      if (laterBox) laterBox.hidden = c.later === 0;
      var dn = view.querySelector('#rmDoneN');
      var ln = view.querySelector('#rmLaterN');
      setNum(dn, c.done);
      setNum(ln, c.later);
    }

    function titleOf(card) {
      var t = card.querySelector('.rm-card__t');
      return t ? t.textContent.trim() : '这一条';
    }

    function toList(list, card, tail) {
      if (!list) return;
      var li = document.createElement('li');
      li.className = 'rm-gone__i';
      li.innerHTML = '<b></b> — <span></span> <small></small>';
      li.querySelector('b').textContent = titleOf(card);
      li.querySelector('span').textContent = tail.text;
      li.querySelector('small').textContent = tail.when;
      list.appendChild(li);
    }

    function finish(card, why) {
      card.setAttribute('data-rm-state', 'done');
      var lbl = card.querySelector('[data-rm-state-label]');
      if (lbl) lbl.textContent = why;
      toList(doneList, card, { text: why, when: '刚刚' });
      paint();
      var c = counts();
      C2.toast('已从队列里移出：' + titleOf(card) + ' —— 队列还剩 ' + c.queued + ' 条');
    }

    cards.forEach(function (card) {
      /* ---- 处理掉 ---- */
      var bDone = card.querySelector('[data-rm-done]');
      if (bDone) bDone.addEventListener('click', function () {
        if (card.getAttribute('data-rm-state') === 'done') return;
        finish(card, '已处理 · 刚刚');
      });

      /* ---- 延后：不减少队列，但要写明推到什么时候 ---- */
      var bLater = card.querySelector('[data-rm-later]');
      if (bLater) bLater.addEventListener('click', function () {
        if (card.getAttribute('data-rm-state') === 'done') return;
        var when = bLater.textContent.trim();
        card.setAttribute('data-rm-state', 'later');
        var lbl = card.querySelector('[data-rm-state-label]');
        if (lbl) lbl.textContent = '已延后 · ' + when;
        toList(laterList, card, { text: '已延后', when: when });
        paint();
        var c = counts();
        C2.toast('已延后（' + when + '）：这条仍占着队列，现在还剩 ' + c.queued + ' 条');
      });

      /* ---- 标为已读：读过不等于办过，所以它留在队列里 ---- */
      var bRead = card.querySelector('[data-rm-read]');
      if (bRead) bRead.addEventListener('click', function () {
        if (card.getAttribute('data-rm-state') === 'done') return;
        var wasLater = card.getAttribute('data-rm-state') === 'later';
        card.setAttribute('data-rm-state', wasLater ? 'later' : 'read');
        var lbl = card.querySelector('[data-rm-state-label]');
        if (lbl && !wasLater) lbl.textContent = '已读';
        paint();
        C2.toast(wasLater ? '这一条已经延后过了，不用再标已读' : '已读：它还在队列里，办完再点「标记完成」');
      });
    });

    /* ---- 全部标为已读 ---- */
    var bAll = view.querySelector('#rmAllRead');
    if (bAll) bAll.addEventListener('click', function () {
      var n = 0;
      cards.forEach(function (card) {
        if (card.getAttribute('data-rm-state') === 'unread') {
          card.setAttribute('data-rm-state', 'read');
          var lbl = card.querySelector('[data-rm-state-label]');
          if (lbl) lbl.textContent = '已读';
          n++;
        }
      });
      paint();
      var c = counts();
      C2.toast(n ? '已把 ' + n + ' 条标为已读；队列数不变（还是 ' + c.queued + ' 条）—— 已读不是处理完'
                 : '没有未读的条目了');
    });

    /* ---- 免打扰：设了之后哪几条被推到什么时候（内容随开关与时段重算） ---- */
    var quietOn = view.querySelector('#rmQuietOn');
    var qStart = view.querySelector('#rmQStart');
    var qEnd = view.querySelector('#rmQEnd');
    var qEcho = view.querySelector('#rmQuietEcho');
    var qEx = view.querySelector('#rmQuietEx');
    var qN = view.querySelector('#rmQuietN');
    var qTitle = view.querySelector('.rm-quiet__ext');
    var qList = view.querySelector('.rm-quiet__l');

    function quietPaint() {
      if (!quietOn || !qEcho || !qList) return;
      var on = quietOn.checked;
      var s = (qStart && qStart.value) || '22:00';
      var e = (qEnd && qEnd.value) || '07:00';
      var c = counts();
      if (qN) qN.textContent = on ? '已开启' : '已关闭';
      if (qEx) qEx.setAttribute('data-off', String(!on));
      if (qTitle) qTitle.textContent = on
        ? '设成 ' + s + '–' + e + ' 之后，现在队列里的 ' + c.queued + ' 条会这样走：'
        : '关掉之后，现在队列里的 ' + c.queued + ' 条会这样走：';

      var rows = on ? [
        ['中建某院结构岗（后天 18:00 截止）', '有时限的提醒只在 ' + s + ' 那一刻静音，' + e + ' 一到端点恢复；截止前 12 小时无论如何都会响一次。'],
        ['今天那一件（投 3 家，25 分钟）', '原本 8:30 提醒，落在时段之外，不受影响。'],
        ['干预（陪你推进的人）', '主动开口的那一类夜里不单独弹，压到 ' + e + ' 之后跟着早间那一条一起说，只保留一个动作：先投 1 家（5 分钟）。'],
        ['2 条情报', '本来就不该半夜吵你，全部压到 ' + e + ' 之后的早间汇总，不再单独弹。']
      ] : [
        ['中建某院结构岗（后天 18:00 截止）', '恢复原时间：只要到点就弹，包括 ' + s + '–' + e + ' 之间。'],
        ['今天那一件（投 3 家，25 分钟）', '恢复每天 8:30 提醒。'],
        ['干预（陪你推进的人）', '恢复即时弹：停滞满 3 天的当晚就会开口，不再等到早上。'],
        ['2 条情报', '恢复按各自的推送时间弹，不再合并成早间汇总。']
      ];
      qList.innerHTML = rows.map(function (r) {
        return '<li class="rm-quiet__i"><b></b> — <span></span></li>';
      }).join('');
      Array.prototype.forEach.call(qList.children, function (li, i) {
        li.querySelector('b').textContent = rows[i][0];
        li.querySelector('span').textContent = rows[i][1];
      });

      if (qEcho) {
        qEcho.textContent = on
          ? s + '–' + e + ' 之间不弹任何东西。这 ' + hoursBetween(s, e) + ' 小时正好盖住你晚上写代码和早上第一节有课的两段时间。'
          : '已关闭：上面 ' + c.queued + ' 条恢复到各自的时间直接弹。夜里那 2 条情报也会直接弹出来 —— 这就是关掉的实际代价。';
      }
    }

    function hoursBetween(s, e) {
      function m(t) { var p = String(t).split(':'); return (Number(p[0]) || 0) * 60 + (Number(p[1]) || 0); }
      var d = m(e) - m(s);
      if (d <= 0) d += 24 * 60;
      return Math.round(d / 60);
    }

    if (quietOn) quietOn.addEventListener('change', function () {
      quietPaint();
      C2.toast(quietOn.checked
        ? '已开启免打扰：' + ((qStart && qStart.value) || '22:00') + '–' + ((qEnd && qEnd.value) || '07:00') + ' 之间不弹；有时限的提醒恢复后仍会响一次'
        : '已关闭免打扰：5 条会按各自时间直接弹，包括夜里那 2 条情报');
    });
    [qStart, qEnd].forEach(function (el) {
      if (!el) return;
      el.addEventListener('change', function () {
        quietPaint();
        if (quietOn && quietOn.checked) C2.toast('免打扰改为 ' + qStart.value + '–' + qEnd.value + '，上面的推后时间已经重算');
      });
    });

    /* ---- 哪几天生效：按天开关，点一天就重算一次提示 ---- */
    Array.prototype.forEach.call(view.querySelectorAll('.rm-day'), function (b) {
      b.addEventListener('click', function () {
        var on = b.getAttribute('aria-pressed') === 'true';
        b.setAttribute('aria-pressed', String(!on));
        var days = Array.prototype.filter.call(view.querySelectorAll('.rm-day'), function (x) {
          return x.getAttribute('aria-pressed') === 'true';
        }).map(function (x) { return x.textContent.trim(); });
        C2.toast(days.length ? '免打扰生效的日子：周' + days.join('、周') : '所有日子都不生效 —— 等于关掉了免打扰');
      });
    });

    quietPaint();
    paint();
  });
})();
