/* =============================================================================
 * 方向方案 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页只做一件被点名的事：**改权重 → 三条方向当场重排**（DESIGN-LANGUAGE §8）。
 *
 * 为什么它不是"换一段文字"：
 *   1. 三条方向卡的 DOM 顺序真的被重排（appendChild），不是只改分数；
 *   2. 判据是现算的：排序分 = Σ(该项分数 × 权重) ÷ Σ(权重)，权重来自五档控件；
 *   3. 每次调整都说出"变了什么"（谁升到第几、为什么），而不是笼统的"已更新"。
 *
 * 数字从哪来：五个比较项在三条方向上的分数**从页首表格的 DOM 里读**（标记里只写
 * 一次），刷新时再由同一份数据回写表格 —— 表、排序卡、读数条永远是同一套数。
 * 页头那份演示预设比例（0.82 / 0.64 / 0.58）是内容，本脚本不碰。
 * ========================================================================== */
(function () {
  'use strict';

  /* 五个比较项：权重键 → 三条方向的分数（0–100 演示刻度；权威值在标记里的表格中） */
  var CRIT = [
    { key: 'major',  name: '专业对口',   v: { semi: 90, new: 74, mat: 84 } },
    { key: 'jobs',   name: '岗位数量',   v: { semi: 90, new: 74, mat: 70 } },
    { key: 'pay',    name: '起薪水平',   v: { semi: 78, new: 86, mat: 58 } },
    { key: 'stable', name: '稳定性',     v: { semi: 66, new: 52, mat: 92 } },
    { key: 'place',  name: '通勤与地点', v: { semi: 70, new: 60, mat: 88 } }
  ];
  var DIRS = [
    { key: 'semi', name: '半导体材料工艺',   role: '主攻' },
    { key: 'new',  name: '新能源电池研发助理', role: '平行' },
    { key: 'mat',  name: '省内国企材料检测岗', role: '保底' }
  ];
  var STEPS = 5;          /* 五档：1 档最轻、5 档最重 */
  var DEFAULT_STEP = 3;   /* 默认一样重 */

  var weight = {};
  CRIT.forEach(function (c) { weight[c.key] = DEFAULT_STEP; });
  var initDone = false;

  function critOf(key) {
    var hit = null;
    CRIT.forEach(function (c) { if (c.key === key) hit = c; });
    return hit;
  }

  C2.onView('directions', function () {
    var root = document.querySelector('[data-view="directions"]');
    if (!root) return;

    var rankBox = document.getElementById('dirRank');
    if (!rankBox) return;
    var liveT = document.getElementById('dirLiveT');
    var liveD = document.getElementById('dirLiveD');
    var leadEl = document.getElementById('dirLead');
    var casN = document.getElementById('dirCasN');
    var casLive = document.getElementById('dirCasLive');

    /* 排序卡按方向键存一份；重排就是 appendChild —— 顺序由 DOM 决定 */
    var cards = {};
    Array.prototype.forEach.call(rankBox.querySelectorAll('[data-dir-d]'), function (el) {
      cards[el.getAttribute('data-dir-d')] = el;
    });

    /* 页脚那段"怎么算的"保留原文，读数条复用它 —— 口径只写一次 */
    var note = document.getElementById('dirCalc');
    var howText = note ? note.textContent.trim() : '';

    /* ---- 1. 手写标记里没有的东西：档位刻度（刻度是图形，交给 JS，不手抄五遍） */
    Array.prototype.forEach.call(root.querySelectorAll('.dir-ctl__bar'), function (bar) {
      for (var i = 0; i < STEPS; i++) bar.appendChild(document.createElement('i'));
    });

    /* ---- 2. 分数从表格读进来（标记里只写一次） ----------------------------- */
    var rows = Array.prototype.slice.call(root.querySelectorAll('.dir-scores tbody tr'));
    rows.forEach(function (row, ri) {
      var c = CRIT[ri];
      if (!c) return;
      Array.prototype.forEach.call(row.querySelectorAll('.dir-sc__v'), function (cell, ci) {
        var raw = parseFloat(cell.textContent);
        if (!isNaN(raw) && DIRS[ci]) c.v[DIRS[ci].key] = raw;
      });
    });

    /* ---- 3. 算分 → 排名 → "为什么是它" ----------------------------------- */
    function rankedScores() {
      var wsum = 0;
      CRIT.forEach(function (c) { wsum += weight[c.key] / STEPS; });
      return DIRS.map(function (d) {
        var s = 0;
        CRIT.forEach(function (c) { s += c.v[d.key] * (weight[c.key] / STEPS); });
        var exact = s / wsum;
        return { key: d.key, name: d.name, role: d.role, exact: exact, score: Math.round(exact) };
      }).sort(function (a, b) {
        /* 先比四舍五入后的显示值，再比没舍入的真实值 —— 否则 81.4 和 81.2 谁在前面是随机的 */
        return (b.score - a.score) || (b.exact - a.exact);
      });
    }

    /* 在所有比较项里挑"权重 × 三条方向的分数差"最大的那一项 —— 它才是这次排序的成因 */
    function decisiveCrit() {
      var best = null, bestPull = -1;
      CRIT.forEach(function (c) {
        var vs = DIRS.map(function (d) { return c.v[d.key]; });
        var spread = Math.max.apply(null, vs) - Math.min.apply(null, vs);
        var pull = (weight[c.key] / STEPS) * spread;
        if (pull > bestPull) { bestPull = pull; best = { key: c.key, name: c.name }; }
      });
      return best;
    }
    function whyText(list, key) {
      var w = key ? { key: key, name: critOf(key).name } : decisiveCrit();
      if (!w) return '';
      var c = critOf(w.key);
      /* 说清楚"为什么是它"：拿第 1 名和第 2 名比这一项 —— 它们才是互相顶位的那两个 */
      var hi = list[0];
      var lo = list[1];
      if (!hi || !lo) return '';
      var a = c.v[hi.key], b = c.v[lo.key];
      if (a === b) {
        var third = list[2];
        if (!third || c.v[hi.key] === c.v[third.key]) return '';
        lo = third; b = c.v[third.key];
      }
      var up = a > b;
      return '你给的档位里「' + w.name + '」最重，这一项上' + (up ? hi.name : lo.name) + '（' +
        (up ? a : b) + '）比' + (up ? lo.name : hi.name) + '（' + (up ? b : a) + '）高 ' +
        Math.abs(a - b) + ' 分。';
    }

    /* ---- 4. 一次刷完：表格、五档刻度、排序卡、读数条 ----------------------- */
    function paintTable() {
      rows.forEach(function (row, ri) {
        var c = CRIT[ri];
        if (!c) return;
        var vs = DIRS.map(function (d) { return c.v[d.key]; });
        var top = Math.max.apply(null, vs);
        var low = Math.min.apply(null, vs);
        Array.prototype.forEach.call(row.querySelectorAll('.dir-sc'), function (sc, ci) {
          var v = c.v[DIRS[ci].key];
          var i = sc.querySelector('.dir-sc__t>i');
          var n = sc.querySelector('.dir-sc__n');
          if (i) {
            i.setAttribute('data-lvl', String(v === top ? 2 : (v === low ? 0 : 1)));
            i.style.setProperty('--dir-fill', String(v / 100));
          }
          if (n) n.textContent = v === top ? '最高' : (v === low ? '最低' : '');
          if (v === top) sc.setAttribute('data-tone', 'hi');
          else if (v === low) sc.setAttribute('data-tone', 'lo');
          else sc.removeAttribute('data-tone');
        });
      });
    }

    function paintControls() {
      Array.prototype.forEach.call(root.querySelectorAll('.dir-ctl__r'), function (row) {
        var val = weight[row.getAttribute('data-dir-wkey')];
        var out = row.querySelector('[data-dir-val]');
        if (out) out.textContent = String(val);
        Array.prototype.forEach.call(row.querySelectorAll('.dir-ctl__bar>i'), function (seg, i) {
          seg.style.background = i < val ? 'var(--c-text-2)' : 'var(--c-border)';
        });
        Array.prototype.forEach.call(row.querySelectorAll('[data-dir-step]'), function (b) {
          var step = Number(b.getAttribute('data-dir-step'));
          b.disabled = step < 0 ? val <= 1 : val >= STEPS;
        });
      });
    }

    function paintRank(list, prev) {
      list.forEach(function (d, i) {
        var el = cards[d.key];
        if (!el) return;
        el.setAttribute('data-dir-rank', String(i + 1));
        var pos = el.querySelector('.dir-rank__pos');
        if (pos) pos.textContent = String(i + 1);
        var v = el.querySelector('.dir-rank__v b');
        if (v) v.textContent = String(d.score);
        var bar = el.querySelector('.dir-rank__bar');
        if (bar) bar.style.setProperty('--dir-fill', String(d.score / 100));
        var gap = el.querySelector('.dir-rank__g');
        if (gap) {
          var lead2 = list[1] ? (list[0].score - list[1].score) : 0;
          if (i === 0) {
            gap.textContent = lead2 === 0
              ? '与第 2 名同分，靠未舍入的差别排前'
              : '领先第 2 名 ' + lead2 + ' 分';
          } else {
            var back = list[0].score - d.score;
            gap.textContent = back === 0
              ? '与第 1 名同分，差别在第 3 位小数'
              : '落后第 1 名 ' + back + ' 分';
          }
        }
        var was = prev ? prev.indexOf(d.key) : -1;
        if (was >= 0 && was !== i) el.setAttribute('data-dir-move', was > i ? 'up' : 'down');
        else el.removeAttribute('data-dir-move');
        rankBox.appendChild(el);   /* ← DOM 真的重排 */
      });

      if (liveT) {
        liveT.innerHTML = '当前排序：' + list.map(function (d, i) {
          return (i === 0 ? '<b>' : '') + d.name + ' ' + d.score + (i === 0 ? '</b>' : '');
        }).join(' &gt; ');
      }
      if (liveD) {
        liveD.textContent = howText + ' 现在最靠前的是「' + list[0].name + '」。';
      }
      if (leadEl) leadEl.textContent = list[0].name + '（' + list[0].score + ' 分）';
    }

    var lastRank = null;

    function render() {
      var list = rankedScores();
      paintTable();
      paintControls();
      paintRank(list, lastRank);
      var before = lastRank;
      lastRank = list.map(function (d) { return d.key; });
      return { list: list, prev: before };
    }

    /* ---- 5. 调权重：即时反馈 + 说清"变了什么" ----------------------------- */
    function bump(row, delta) {
      var key = row.getAttribute('data-dir-wkey');
      var wname = row.getAttribute('data-dir-w');
      var before = weight[key];
      var after = Math.min(STEPS, Math.max(1, before + delta));
      if (after === before) return;
      weight[key] = after;

      var out = render();
      var list = out.list;
      var msg = '「' + wname + '」' + before + ' → ' + after + ' 档：';

      var moved = [];
      list.forEach(function (d, i) {
        var was = out.prev ? out.prev.indexOf(d.key) : -1;
        if (was >= 0 && was !== i) moved.push(d.name + (i < was ? ' 升到第 ' + (i + 1) : ' 掉到第 ' + (i + 1)));
      });
      if (moved.length) {
        msg += moved.join('、') + '。';
        /* 顺序真变了才解释为什么 —— 说明的是"哪一项把它顶上去的"，所以用刚调的这项 */
        msg += whyText(list, key);
      } else {
        msg += '顺序没变，分数动了（' + list.map(function (d) { return d.score; }).join(' / ') + '）。';
      }
      C2.toast(msg);
    }

    Array.prototype.forEach.call(root.querySelectorAll('.dir-ctl__r'), function (row) {
      Array.prototype.forEach.call(row.querySelectorAll('[data-dir-step]'), function (b) {
        b.addEventListener('click', function () {
          bump(row, Number(b.getAttribute('data-dir-step')));
        });
      });
    });

    var reset = document.getElementById('dirReset');
    if (reset) reset.addEventListener('click', function () {
      var changed = 0;
      CRIT.forEach(function (c) {
        if (weight[c.key] !== DEFAULT_STEP) changed++;
        weight[c.key] = DEFAULT_STEP;
      });
      var list = render().list;
      var tail = list.map(function (d) { return d.name + ' ' + d.score; }).join(' / ');
      C2.toast(changed
        ? '五个比较项回到一样重（都是 3 档）：' + tail + '。'
        : '本来就是一样重（都是 3 档），没有可回退的改动。');
    });

    /* ---- 6. 选定方向：连带改动当场显形，随时可撤销 ------------------------ */
    var cardEls = Array.prototype.slice.call(root.querySelectorAll('.dir-card'));
    var picked = null;

    function paintPick() {
      cardEls.forEach(function (el) {
        var on = el.getAttribute('data-dir-d') === picked;
        var name = el.getAttribute('data-dir-name');
        el.setAttribute('data-dir-state', on ? 'picked' : 'candidate');
        el.setAttribute('aria-pressed', String(on));
        var now = el.querySelector('.dir-card__now');
        if (now) {
          now.textContent = on
            ? '现在是选中的：下面这几处已按「' + name + '」改了口径。'
            : '现在不是选中的：这几处按它算的改动只是预演，点下面的按钮才算。';
        }
        var btn = el.querySelector('[data-dir-pick]');
        if (btn) btn.textContent = on ? '撤销这个选定' : btn.getAttribute('data-dir-label');
      });

      if (casN) casN.textContent = picked ? '已选 1 条' : '还没选';
      if (!casLive) return;
      var hit = null;
      DIRS.forEach(function (x) { if (x.key === picked) hit = x; });
      var t = casLive.querySelector('.dir-live__t');
      var d = casLive.querySelector('.dir-live__d');
      if (t) {
        t.textContent = hit
          ? '已选定「' + hit.name + '」（' + hit.role + '）：岗位资讯按这一条筛、今日行动补它的缺口、报告里对应那条结论重写、投递清单重排。'
          : '现在没有选定方向。三条都还开着，所以岗位资讯、今日行动、报告结论都保持中性，不按任何一条预筛。';
      }
      if (d) {
        d.textContent = hit
          ? '随时可撤销：撤销后上面几处回退到不预筛的状态。选定不改你档案里的任何数字。'
          : '选定只影响上面那几处的取舍方式，不改你档案里的任何数字；认定选错了就撤销，改动回退。';
      }
    }

    cardEls.forEach(function (el) {
      var btn = el.querySelector('[data-dir-pick]');
      if (!btn) return;
      btn.setAttribute('data-dir-label', btn.textContent.trim());
      btn.addEventListener('click', function () {
        var key = el.getAttribute('data-dir-d');
        var name = el.getAttribute('data-dir-name');
        if (picked === key) {
          picked = null;
          paintPick();
          C2.toast('已撤销「' + name + '」的选定，连带改动回退。');
          return;
        }
        picked = key;
        paintPick();
        C2.toast('已选定「' + name + '」，连带改动按这一条标出了 4 处。');
      });
    });
    paintPick();

    /* ---- 7. 页头两个动作：都是"送到别处"，不在这一页假装完成 --------------- */
    var ask = root.querySelector('[data-dir-ask]');
    if (ask) ask.addEventListener('click', function () {
      var text = ask.getAttribute('data-dir-ask');
      var msg = document.getElementById('msg');
      if (msg) {
        msg.value = text;
        msg.dispatchEvent(new Event('input'));
      }
      C2.show('chat');
      C2.toast('已写进对话输入框：' + text);
      if (msg) setTimeout(function () { msg.focus(); }, 60);
    });
    var copy = root.querySelector('[data-dir-copy]');
    if (copy) copy.addEventListener('click', function () {
      C2.toast('演示样张：这版比较（含你调过的权重）不会真的复制到剪贴板。');
    });

    /* ---- 8. 首屏：权重都是 3 档，先把表与排序画好 ------------------------- */
    render();
    if (initDone) return;
    initDone = true;
  });
})();
