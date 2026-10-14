/* =============================================================================
 * 通用组件与状态 · 视图行为
 * -----------------------------------------------------------------------------
 * 为什么这一页必须有 JS：它是**状态与反馈的示范页**，而独立审计抓到
 *   · 3 个带 data-gl-toast 的按钮点了**零反馈**（.toast 0→0）
 *   · 骨架样张以 skelSweep 无限跑，"加载态"永远加载不完
 *   · "已加入今日行动"是个死按钮，旁边那行 aria-live 的说明永远不变
 * 也就是说：HANDOFF §4.2 认定的病（"成功反馈静默"）**正好复发在这一页**，
 * 而这一页的职责恰恰是教别人别犯这个病。示范页自己不合格，比普通页不合格更糟。
 *
 * 三个动作，都只做"让状态真的会变"这一件事：
 *   1. [data-gl-toast]        → C2.toast（把按钮上写好的那句话真的说出来）
 *   2. .btn[data-done]        → 切换 data-done，并更新旁边那行 aria-live 的说明
 *   3. [data-gl-skel]         → 骨架跑一次（1.8s）再停下
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('gallery', function () {
    var view = document.querySelector('[data-view="gallery"]');
    if (!view) return;

    /* ---- 1. 会说话的按钮 ----------------------------------------------------
       文案就写在按钮的 data-gl-toast 上（作者已经写好了，只是没人读它）。
       "重试 / 自己传" 这类是错误态里的动作，用 warn 档；其余用默认档。 */
    Array.prototype.forEach.call(view.querySelectorAll('[data-gl-toast]'), function (b) {
      b.addEventListener('click', function () {
        var text = b.getAttribute('data-gl-toast') || b.textContent.trim();
        var isError = /重试|没取到|传/.test(text);
        C2.toast(text, isError ? 'warn' : undefined);
      });
    });

    /* ---- 2. 「已加入今日行动」要能撤销，并同步那行说明 ---------------------
       上一轮病历里有一条正相反：勾掉一件事得到零反馈。所以这里不是 disabled，
       而是 data-done 的双向切换（页面自己的 §1.4 也这么写着）。 */
    var doneBtn = view.querySelector('.btn[data-done]');
    var live = view.querySelector('[data-gl-addline]');
    if (doneBtn) {
      doneBtn.addEventListener('click', function () {
        var done = doneBtn.getAttribute('data-done') === 'true';
        doneBtn.setAttribute('data-done', String(!done));
        doneBtn.textContent = done ? '加入今日行动' : '已加入今日行动';
        if (live) {
          live.textContent = done
            ? '现在是"加入今日行动"：实心主色只出现这一次。'
            : '已加入：按钮回到中性（完成不给颜色奖励），并且可以再点一次撤销 —— 状态变化有落点，而不是变成死按钮。';
        }
        C2.toast(done ? '已加入今日行动（再点一次可撤销）' : '已撤销：它不再是今日行动里的一条');
      });
    }

    /* ---- 3. 骨架样张：点一次跑一次 ----------------------------------------- */
    var skelBtn = view.querySelector('[data-gl-skel]');
    var skel = view.querySelector('.skel');
    var skelNote = view.querySelector('[data-gl-skel-note]');
    if (skelBtn && skel) {
      var timer = null;
      skelBtn.addEventListener('click', function () {
        skel.setAttribute('data-gl-run', 'running');
        skelBtn.setAttribute('aria-disabled', 'true');
        if (skelNote) skelNote.textContent = '正在跑一次加载：骨架扫光。跑完就停下 —— 它不会一直动。';
        if (timer) clearTimeout(timer);
        timer = setTimeout(function () {
          skel.removeAttribute('data-gl-run');
          skelBtn.removeAttribute('aria-disabled');
          if (skelNote) {
            skelNote.innerHTML = '这次加载跑完了。骨架默认<b>不动</b>：一整页一直在扫光的骨架属于"持续背景运动"，是反例表里点名的装饰。';
          }
        }, 1800);
      });
    }
  });
})();
