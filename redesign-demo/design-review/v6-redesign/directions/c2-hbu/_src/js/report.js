/* =============================================================================
 * 诊断报告 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页的交互只做三件事，每件都回答"这里发生了什么"：
 *   1. 点一条判断 → 它在「九条结论」里的那几条亮起来、其余退到后景（结构显形）
 *   2. 追到原始来源 → 落到那一条的**原文**层（粒度缩放，不是折叠框）
 *   3. 切版本 / 标重算 → 看见状态真的变了（不是灰字说明）
 *
 * 反馈文字一律从 DOM 里**算出来**，不写死：数亮起来的条目里各有几条
 * 依据充分 / 待验证 / 信息不足、几条标着过期。数字不对时是数据不对，不是文案不对。
 *
 * 连线怎么对齐：判断卡上的依赖 chip 文本 == 结论条目的「维度」名（同一套词）。
 * 所以不另加一遍 key —— 词只有一个来源，改文案时两边一起改。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('report', function () {
    var root = document.querySelector('[data-view="report"]');
    if (!root) return;

    /* ---- 1 · 判断 ↔ 依据 -------------------------------------------------
       一进页面**不预选**任何一条：先把"信息都在"的完整形态给你，
       点哪条判断才把它的连线显示出来。这是用户主动的组织动作，不是开场表演。 */
    var wrap = document.getElementById('rpConc');
    var echo = document.getElementById('rpConcEcho');
    var items = Array.prototype.slice.call(root.querySelectorAll('.rp-it'));

    function itemName(el) { return el.getAttribute('data-rp-item') || ''; }
    function confOf(el) {
      if (el.querySelector('.conf--verified')) return 'verified';
      if (el.querySelector('.conf--reported')) return 'reported';
      if (el.querySelector('.conf--inferred')) return 'inferred';
      return 'plain';
    }
    var CONF_TEXT = { verified: '依据充分', reported: '待验证', inferred: '信息不足', plain: '未标注' };

    function paint(active) {
      var deps = Array.prototype.map.call(active.querySelectorAll('.rp-dep'), function (d) {
        return d.textContent.trim();
      });
      var hit = [];
      items.forEach(function (item) {
        var on = deps.indexOf(itemName(item)) >= 0;
        item.setAttribute('data-rp-hit', String(on));
        item.setAttribute('data-rp-dim', String(!on));
        if (on) hit.push(item);
      });

      if (!echo) return;
      if (!hit.length) {
        echo.textContent = '这条判断现在挂空 —— 它依赖的那几条不在报告里，得先去补资料。';
        return;
      }
      var counts = {};
      var weak = [];
      var stale = 0;
      hit.forEach(function (item) {
        var c = confOf(item);
        counts[c] = (counts[c] || 0) + 1;
        if (c === 'inferred') weak.push(itemName(item));
        if (item.querySelector('.conf--stale')) stale++;
      });
      var mix = Object.keys(counts).map(function (k) {
        return counts[k] + ' 条' + CONF_TEXT[k];
      }).join('、');
      var names = hit.map(itemName).join('、');
      var title = active.querySelector('.rp-conc__t');

      var tail;
      if (weak.length) {
        tail = '其中 <b>' + weak.join('、') + '</b> 还是信息不足 —— 这条判断现在就压在这个缺口上，去对话里问一句就能把它补成依据。';
      } else if (counts.reported) {
        tail = '其中 <b>' + counts.reported + ' 条只有你自己说过或只有演示数据</b>，还没有别的事实印证。';
      } else {
        tail = '每一条都是<b>依据充分</b>的，所以这条判断现在站得住。';
      }
      if (stale) tail += '另有 <b>' + stale + ' 条标着要重算</b>，重算之前它算不得数。';

      echo.innerHTML = '「' + (title ? title.textContent.trim() : '') + '」现在靠 <b>' + hit.length +
        ' 条</b>撑着：' + names + '（' + mix + '）。' + tail;
    }

    if (wrap) {
      var concs = Array.prototype.slice.call(wrap.querySelectorAll('.rp-conc__r'));
      concs.forEach(function (btn) {
        btn.addEventListener('click', function () {
          concs.forEach(function (b) { b.setAttribute('aria-pressed', String(b === btn)); });
          paint(btn);
        });
        btn.setAttribute('aria-pressed', 'false');
      });
      /* 加载时不压暗任何一条 */
      items.forEach(function (item) {
        item.removeAttribute('data-rp-hit');
        item.removeAttribute('data-rp-dim');
      });
      var first = concs[0];
      if (first && echo) {
        echo.textContent = '点上面任意一条判断：它在「九条结论」里的那几条会亮起来、别的退到后景。' +
          '这一页一共 ' + items.length + ' 条结论。';
      }
    }

    /* ---- 2 · 追到原始来源：落到那一层的**原文**上 ------------------------ */
    function showFull(zoom) {
      if (!zoom) return;
      zoom.setAttribute('data-zoom', 'full');
      Array.prototype.forEach.call(zoom.querySelectorAll('[data-zoom-set]'), function (b) {
        b.setAttribute('aria-pressed', String(b.getAttribute('data-zoom-set') === 'full'));
      });
    }
    var reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    Array.prototype.forEach.call(root.querySelectorAll('[data-rp-jump]'), function (b) {
      b.addEventListener('click', function () {
        var target = document.getElementById(b.getAttribute('data-rp-jump'));
        if (!target) return;
        var z = target.classList.contains('zoom') ? target : target.querySelector('.zoom');
        showFull(z);
        target.scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
        C2.toast('已翻到原文层：数字、日期、原话都在这一层，可以核对');
      });
    });

    /* ---- 3 · 三个版本：切一版，看得见那一版留下了什么 -------------------- */
    var ver = document.getElementById('rpVer');
    if (ver) {
      var VER = {
        v3: { when: '10 月 8 日', fit: 82, what: '补上"呈现能力"与岗位门槛的差距' },
        v2: { when: '9 月 24 日', fit: 71, what: '学籍核验后，成绩层级参与折算' },
        v1: { when: '9 月 12 日', fit: 61, what: '首次生成：只有对话来源' }
      };
      Array.prototype.forEach.call(ver.querySelectorAll('[data-rp-ver]'), function (b) {
        b.addEventListener('click', function () {
          var key = b.getAttribute('data-rp-ver');
          ver.setAttribute('data-rp-ver-sel', key);
          Array.prototype.forEach.call(ver.querySelectorAll('[data-rp-ver]'), function (o) {
            o.setAttribute('aria-pressed', String(o === b));
          });
          var v = VER[key];
          C2.toast('已切到 ' + key + '（' + v.when + '）：契合度 ' + v.fit + ' —— ' + v.what);
        });
      });
    }

    /* ---- 4 · 重算的落点：状态真的变，但不编一个新分数 -------------------- */
    var staleEcho = document.getElementById('rpStaleEcho');
    Array.prototype.forEach.call(root.querySelectorAll('[data-rp-recalc]'), function (b) {
      b.addEventListener('click', function () {
        var kind = b.getAttribute('data-rp-recalc');
        if (kind === 'intel') {
          var item = root.querySelector('.rp-it[data-rp-item="岗位供给"]');
          if (item) {
            var chip = item.querySelector('.conf--stale');
            if (chip) {
              chip.className = 'conf conf--reported';
              chip.innerHTML = '<i aria-hidden="true"></i>已排进重算队列';
            }
          }
          if (staleEcho) staleEcho.textContent = '已经把它标成待重算，但重算要等真实的岗位来源到位 —— 演示样张不会替你造一个新数字。';
          C2.toast('已把「岗位供给」标成待重算：它不会再参与首屏那句结论', 'warn');
          return;
        }
        var head = document.querySelector('[data-view="report"] .pgh__meta .conf--stale');
        if (head) {
          head.className = 'conf conf--reported';
          head.innerHTML = '<i aria-hidden="true"></i>已排进重算队列（演示）';
        }
        C2.toast('演示样张：重算会用最新资料重跑，分数不会在这里真的变 —— 九条结论仍是 10 月 8 日那一版');
      });
    });

    /* ---- 5 · 去补缺口：把问题送进对话页输入框（与画像页同一套做法） ------- */
    Array.prototype.forEach.call(root.querySelectorAll('[data-rp-ask]'), function (b) {
      b.addEventListener('click', function () {
        var text = b.getAttribute('data-rp-ask');
        var msg = document.getElementById('msg');
        if (msg) {
          msg.value = text;
          msg.dispatchEvent(new Event('input'));
        }
        C2.show('chat');
        C2.toast('已写进对话输入框：' + text);
        if (msg) setTimeout(function () { msg.focus(); }, 60);
      });
    });
  });
})();
