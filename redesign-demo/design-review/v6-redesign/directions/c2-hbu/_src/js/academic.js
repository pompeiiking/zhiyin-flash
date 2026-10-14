/* =============================================================================
 * 学籍与资料 · 视图行为
 * -----------------------------------------------------------------------------
 * 三处交互，各自对应一个「看得见的关系」：
 *   1. 冲突卡上的处理按钮 → 视角重组里撞在一起的那两条课亮起来、其余退到后景
 *      （结构显形：冲突不是一段说明，是两条课在同一个时段上）。
 *   2. 核验「重新对一遍」→ 进度是真会往前走的：还剩几项、哪一步在做、下一步
 *      什么时候能动，都跟着改（进行时 + 将来时，不是一句「已完成」）。
 *   3. 上传/重导/待定 → 演示样张，说清会发生什么，不假装真的执行。
 * 数字全部从 DOM 里算，不写死第二份。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('academic', function () {
    var view = '[data-view="academic"]';

    /* ---- 1 · 冲突：把那两条撞在一起的课挑出来 ---------------------------- */
    var clash = document.getElementById('acClash');
    var clashBtn = document.querySelector(view + ' [data-ac-conflict]');
    var lensItems = Array.prototype.slice.call(document.querySelectorAll(view + ' .lens__item'));

    if (clashBtn) clashBtn.addEventListener('click', function () {
      var hit = [], rest = [];
      lensItems.forEach(function (el) {
        var k = el.querySelector('.ac-k');
        var t = k ? k.textContent : '';
        var on = t.indexOf('材料实验') >= 0 || t.indexOf('创新项目讨论') >= 0;
        (on ? hit : rest).push(el);
      });
      /* 亮着的两条留在原位，其余退到后景 —— 上面的 .lens 就是这两条的成绩视图，
         所以这一下不是装饰：它在告诉你「冲突落在哪两条上」。 */
      hit.forEach(function (el) { el.setAttribute('data-hit', 'true'); el.setAttribute('data-dim', 'false'); });
      rest.forEach(function (el) { el.setAttribute('data-hit', 'false'); el.setAttribute('data-dim', 'true'); });

      var note = clash ? clash.querySelector('.ac-card__n') : null;
      if (note) note.textContent = '已标出撞在一起的 2 条';
      C2.toast('已标出撞在一起的两条：材料实验、创新项目讨论（在第 5 节那个视角里）');

      /* 6 秒后放开，让上面那批成绩回到完整形态 —— 用户没点「永远只看这两条」。 */
      window.setTimeout(function () {
        lensItems.forEach(function (el) {
          el.removeAttribute('data-hit');
          el.removeAttribute('data-dim');
        });
      }, 6000);
    });

    /* ---- 2 · 核验：进度真的会走一格 -------------------------------------- */
    var done = 2;
    var left = 3;
    var veDone = document.getElementById('acVeDone');
    var veN = document.getElementById('acVeN');
    var veNow = document.getElementById('acVeNow');
    var segs = Array.prototype.slice.call(document.querySelectorAll(view + ' .ac-ve .meter i'));
    var nowWhen = document.querySelector(view + ' .tl__i--now .tl__when');
    var nowWhat = document.querySelector(view + ' .tl__i--now .tl__what');
    var nowD = document.querySelector(view + ' .tl__i--now .tl__d');
    var nowMeta = document.querySelector(view + ' .tl__i--now .tl__meta');
    var recheck = document.getElementById('acRecheck');

    if (recheck) recheck.addEventListener('click', function () {
      if (left <= 0) {
        C2.toast('24 项已经全对完了，剩下两步都要你本人或实习单位才能往前走', 'warn');
        return;
      }
      left -= 1;
      if (left === 0) {
        done = 3;
        if (segs[2]) segs[2].classList.add('on');
        if (nowWhen) nowWhen.innerHTML = '<span class="ac-found">已完成</span>今天 10 月 14 日 · 本地课程快照';
        if (nowWhat) nowWhat.textContent = '检查课程与成绩 —— 24 项全部对完';
        if (nowD) nowD.textContent = '24 项对完了。其中 3 项是文字成绩（优秀、良好、通过），对完的结论仍然只是「学校给的是文字成绩」，不是换算成了分数。';
        if (nowMeta) nowMeta.innerHTML = '<span class="conf conf--verified"><i aria-hidden="true"></i>24 / 24 项已对</span><span class="ac-num">下一步出在线验证报告，要你本人的授权码</span>';
        if (veNow) {
          veNow.className = 'ac-ve__i ac-ve__i--done';
          veNow.textContent = '对 24 项课程：全部对完';
        }
        var next = document.querySelector(view + ' .ac-ve__i:not(.ac-ve__i--done)');
        if (next) next.classList.add('ac-ve__i--now');
        C2.toast('24 项对完了。下一步出在线验证报告，要用你授权的验证码');
      } else {
        if (nowD) nowD.textContent = '24 项里已经对完 ' + (24 - left) + ' 项。剩下 ' + left +
          ' 项是文字成绩（优秀、良好、通过），课表快照读不出对应的分数，我不能替学校补一个数字上去。';
        if (nowWhat) nowWhat.textContent = '检查课程与成绩 —— 24 项已取得，已经对完 ' + (24 - left) + ' 项';
        if (nowMeta) nowMeta.innerHTML = '<span class="conf conf--reported"><i aria-hidden="true"></i>' +
          (24 - left) + ' / 24 项已对</span><span class="ac-num">卡在：课程快照读不出文字成绩对应的分数</span>';
        if (veNow) veNow.textContent = '对 24 项课程，还剩 ' + left + ' 项文字成绩';
        C2.toast('又对完一项，还剩 ' + left + ' 项文字成绩');
      }
      if (veDone) veDone.textContent = String(done);
      if (veN) veN.setAttribute('aria-label', '已完成 ' + done + ' / 4 步');
    });

    /* ---- 3 · 其余动作：说清会发生什么，不假装真的执行 -------------------- */
    Array.prototype.forEach.call(document.querySelectorAll(view + ' [data-ac-upload]'), function (b) {
      b.addEventListener('click', function () {
        var what = b.getAttribute('data-ac-upload');
        var hint = document.getElementById('acSideHint');
        if (hint) {
          hint.innerHTML = '演示样张：<b>' + what + '</b> 不会真的上传。真的传上来之后它标成 <b>待验证</b>，' +
            '不会自动变成官方记录 —— 这点写在资料清单里。';
        }
        C2.toast('演示样张：' + what + ' 不会真的上传', 'warn');
      });
    });

    Array.prototype.forEach.call(document.querySelectorAll(view + ' [data-ac-wait]'), function (b) {
      b.addEventListener('click', function () {
        var note = b.parentNode ? b.parentNode.querySelector('.ac-card__n') : null;
        if (note) note.textContent = '已记下：周次一出来提醒你';
        C2.toast('已记下「企业参访」：周次一通知就提醒你，在那之前不往它上面押时间');
      });
    });

    var reimport = document.getElementById('acReimport');
    if (reimport) reimport.addEventListener('click', function () {
      C2.toast('演示样张：重新导入会拉一份新的课表快照，冲突与待定会重新判一次');
    });

    var uploadTop = document.getElementById('acUploadTop');
    if (uploadTop) uploadTop.addEventListener('click', function () {
      C2.toast('演示样张：这里会打开上传，收证书、证明和经历材料', 'warn');
    });
  });
})();
