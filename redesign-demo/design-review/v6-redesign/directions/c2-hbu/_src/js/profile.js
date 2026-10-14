/* =============================================================================
 * 个人画像 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页的交互只做一件事：**把"判断"和"它依赖的条目"之间的连线变可见**
 * （DESIGN-LANGUAGE §4.1 结构显形、§8 报告行"点结论 → 证据亮起来"）。
 *
 * 连线怎么对齐：判断卡上的依赖 chip 文本 == 画像条目的字段名（两者用同一套词）。
 * 所以不另加一遍 key 属性 —— 词只有一个来源，改文案时两边一起改。
 *
 * 反馈文字是从 DOM 里**算出来**的，不是写死的：数亮起来的条目里各有几条
 * 依据充分 / 待验证 / 信息不足。数字不对时，是数据不对，不是文案不对。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('profile', function () {
    var wrap = document.getElementById('pfConc');
    var echo = document.getElementById('pfConcEcho');
    if (!wrap) return;

    var concs = Array.prototype.slice.call(wrap.querySelectorAll('.pf-conc__r'));
    var items = Array.prototype.slice.call(
      document.querySelectorAll('[data-view="profile"] .lens__item')
    );

    function labelOf(item) {
      var el = item.querySelector('.pf-k');
      return el ? el.textContent.trim() : '';
    }
    function confOf(item) {
      if (item.querySelector('.conf--verified')) return 'verified';
      if (item.querySelector('.conf--reported')) return 'reported';
      if (item.querySelector('.conf--inferred')) return 'inferred';
      return 'plain';
    }
    var CONF_TEXT = { verified: '依据充分', reported: '待验证', inferred: '信息不足', plain: '未标注' };

    function paint(active) {
      var deps = Array.prototype.map.call(active.querySelectorAll('.pf-dep'), function (d) {
        return d.textContent.trim();
      });
      var hit = [];
      items.forEach(function (item) {
        var on = deps.indexOf(labelOf(item)) >= 0;
        item.setAttribute('data-hit', String(on));
        item.setAttribute('data-dim', String(!on));
        if (on) hit.push(item);
      });

      if (!echo) return;
      var title = active.querySelector('.pf-conc__t');
      var counts = {};
      var weak = [];
      hit.forEach(function (item) {
        var c = confOf(item);
        counts[c] = (counts[c] || 0) + 1;
        if (c === 'inferred') weak.push(labelOf(item));
      });
      var mix = Object.keys(counts).map(function (k) {
        return counts[k] + ' 条' + CONF_TEXT[k];
      }).join('、');
      var names = hit.map(labelOf).join('、');

      var tail;
      if (weak.length) {
        /* 判断压着一条没聊透的信息 —— 这比"结论成立/不成立"更有用：
           用户看到的是"这条判断现在靠什么站住、还差哪一口"。 */
        tail = '其中 <b>' + weak.join('、') + '</b> 还没聊透 —— 这条判断现在就压在这个缺口上，去对话页问一句就能把它补成依据。';
      } else if (counts.reported) {
        tail = '其中 <b>' + counts.reported + ' 条只有你自己的说法</b>，还没被别的事实印证。';
      } else {
        tail = '每一条都是<b>依据充分</b>的，所以这条判断现在站得住。';
      }
      echo.innerHTML = '「' + (title ? title.textContent.trim() : '') + '」现在靠 <b>' + hit.length +
        ' 条</b>撑着：' + names + '（' + mix + '）。' + tail;
    }

    concs.forEach(function (btn) {
      btn.addEventListener('click', function () {
        /* 单选：这条判断亮着的时候，别的判断的连线不显示 */
        concs.forEach(function (b) { b.setAttribute('aria-pressed', String(b === btn)); });
        paint(btn);
      });
    });
    /* 加载时**不预选**任何一条判断：页面先把"信息都在"的完整形态给你，
       点哪条判断才把它的连线显示出来。这是用户主动的组织动作，不是开场表演 ——
       一进页面就把 12 条压暗 3 条点亮，等于替用户决定了该看什么。 */
    concs.forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
    items.forEach(function (item) {
      item.removeAttribute('data-hit');
      item.removeAttribute('data-dim');
    });

    /* ---- "去补"：把问题送到对话页的输入框，并把页面切过去 ----------------
       这是"组织权交给用户"的下一半：看到了缺口，能当场去补，而不是记在心里。
       对话页的 #msg 永远在文档里（视图只是隐藏），所以可以直接写入。 */
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-view="profile"] [data-pf-ask]'),
      function (b) {
        b.addEventListener('click', function () {
          var text = b.getAttribute('data-pf-ask');
          var msg = document.getElementById('msg');
          if (msg) {
            msg.value = text;
            msg.dispatchEvent(new Event('input'));
          }
          C2.show('chat');
          C2.toast('已写进对话输入框：' + text);
          if (msg) setTimeout(function () { msg.focus(); }, 60);
        });
      }
    );

    Array.prototype.forEach.call(
      document.querySelectorAll('[data-view="profile"] [data-pf-upload]'),
      function (b) {
        b.addEventListener('click', function () {
          C2.toast('演示样张：' + b.getAttribute('data-pf-upload') + ' 不会真的上传', 'warn');
        });
      }
    );

    /* ---- 侧栏三个动作：改 / 撤 / 重算 ------------------------------------- */
    var hint = document.getElementById('pfCtlHint');
    function say(text) {
      if (hint) hint.textContent = text;
      C2.toast(text);
    }
    var edit = document.querySelector('[data-view="profile"] [data-pf-edit]');
    if (edit) edit.addEventListener('click', function () {
      say('演示样张：这里会打开「改一条」，改完标成「你改的」，诊断报告重算一次。');
    });
    var hide = document.querySelector('[data-view="profile"] [data-pf-hide]');
    if (hide) hide.addEventListener('click', function () {
      say('改过的条目会标成「你改的」，不会消失 —— 顾问需要知道你改过什么。');
    });
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-view="profile"] [data-pf-recheck]'),
      function (b) {
        b.addEventListener('click', function () {
          var row = document.querySelector('[data-view="profile"] .conf--stale');
          if (row) {
            row.className = 'conf conf--verified';
            row.innerHTML = '<i aria-hidden="true"></i>刚刚按最新课表重算';
          }
          var stale = document.querySelector('[data-view="profile"] .tl, [data-view="profile"] tr.stale');
          if (stale) stale.classList.remove('stale');
          say('已按 10 月 14 日的课表重算，空档仍是周三、周五下午各 2 小时。');
        });
      }
    );
  });
})();
