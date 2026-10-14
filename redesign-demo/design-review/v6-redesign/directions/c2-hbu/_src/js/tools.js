/* =============================================================================
 * 工具页 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页只有一个"真的会动"的东西：画像分析那个「跑一次」按钮。
 * 它要证明的事不是"动画"，是**状态迁移看得见**：
 *   还没跑（.state） → 正在跑（.skel，读的是哪 12 条 + 14 轮） → 跑完（结果卡）
 *
 * 三种形态全部写在标记里，JS 只改工具卡上的 data-tl-run 属性 —— 和 .zoom 一样，
 * 信息不在动画里，动画停了信息还在（BRIEF §2.1）。
 *
 * 结果卡里的每一个数字都来自 _src/DEMO-DATA.md 与 demo-ai.ts 的
 * portraitAnalysis / noteSuggestions，没有新造；页面与卡片上都标着「演示数据」。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('tools', function () {
    var root = document.querySelector('[data-view="tools"]');
    if (!root) return;

    /* ---- 1. 跑一次画像分析 ------------------------------------------------
       跑完把按钮换成「再跑一次」并把焦点还回去 —— 键盘用户按完之后不该被丢在
       一个已经不存在的按钮位置上。 */
    var card = document.getElementById('tlRun');
    var btn = root.querySelector('[data-tl-run-btn="portrait"]');
    var out = document.getElementById('tlRunOut');

    if (card && btn) {
      btn.addEventListener('click', function () {
        if (card.getAttribute('data-tl-run') === 'running') return;

        /* 重跑之前把上一份结果收回去：否则"正在跑"的时候下面还摆着旧结论，
           那正好是这一页要修的病 —— 让人分不清哪些是新的。 */
        if (out) out.hidden = true;
        card.setAttribute('data-tl-run', 'running');
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');

        window.setTimeout(function () {
          card.setAttribute('data-tl-run', 'done');
          if (out) out.hidden = false;
          btn.disabled = false;
          btn.removeAttribute('aria-busy');
          btn.textContent = '再跑一次';

          var head = out && out.querySelector('.tl-out__head');
          C2.toast('画像分析跑完了：12 条已读、3 条还没聊到不参与（演示预设结果）');
          if (head) {
            head.setAttribute('tabindex', '-1');
            head.focus();
          }
        }, 900);
      });
    }

    /* ---- 2. 任务建议：加进待办 --------------------------------------------
       这一页不真的写待办（待办页有自己的账本），但必须给即时反馈并说清去哪看。 */
    Array.prototype.forEach.call(root.querySelectorAll('[data-tl-pick]'), function (b) {
      b.addEventListener('click', function () {
        var label = b.getAttribute('data-tl-pick');
        C2.toast('已把「' + label + '」写进待办（演示：不会真的保存）');
        b.textContent = '已加进待办';
        b.setAttribute('aria-pressed', 'true');
      });
    });

    /* ---- 3. 还缺资料的两个按钮 -------------------------------------------
       缺口不是错误，所以不给红色 toast；只说清"缺的是哪一份、补上能解开什么"。 */
    Array.prototype.forEach.call(root.querySelectorAll('[data-tl-need]'), function (b) {
      b.addEventListener('click', function () {
        var what = b.getAttribute('data-tl-need');
        C2.toast('还缺「' + what + '」：补上能解开呈现能力那 4 分差距（演示）');
      });
    });

    /* ---- 4. 全部重跑一遍 --------------------------------------------------
       这一条存在的理由是"工具是一条链"：上游重跑，下游的结论就该重新算。
       所以反馈里必须出现下游的名字，否则这个按钮只是个装饰。 */
    var reset = root.querySelector('[data-tl-reset]');
    if (reset) {
      reset.addEventListener('click', function () {
        if (out) out.hidden = true;
        if (card) card.setAttribute('data-tl-run', 'idle');
        if (btn) btn.textContent = '跑一次画像分析';
        C2.toast('已按顺序重跑：画像分析 → 方向对比 → 任务建议（演示，结果与上一次相同）');
      });
    }
  });
})();
