/* =============================================================================
 * 登录 · 视图行为
 * -----------------------------------------------------------------------------
 * 只做三件事，每一件都要能回答"这里发生了什么"：
 *   1. 换登录方式（学号 / 手机）只换字段，并**同时**重排上面那批"这次要填什么"；
 *   2. 提交前把同意项当作真的前置条件（不是默认勾上的装饰）；
 *   3. 提交后不跳转，只把"演示样张不会真的登录"再说一遍。
 * 演示契约：不发送任何请求，不校验任何输入。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('login', function () {
    var view = document.querySelector('[data-view="login"]');
    if (!view || view.getAttribute('data-lg-init') === 'true') return;
    view.setAttribute('data-lg-init', 'true');

    var ways = Array.prototype.slice.call(view.querySelectorAll('[data-lg-way]'));
    var panels = Array.prototype.slice.call(view.querySelectorAll('[data-lg-panel]'));
    var lensItems = Array.prototype.slice.call(view.querySelectorAll('.lens__item'));
    var elNeedN = view.querySelector('#lgNeedN');
    var elEcho = view.querySelector('#lgEcho');
    var box = view.querySelector('#lgForm');

    var NEED_TEXT = {
      id: '当前方式：学号 + 密码 · 选这个是因为你要在实验室的电脑上登，不想收短信。',
      sms: '当前方式：手机 + 验证码 · 选这个是因为你在换一台设备，想确认是本人在登。'
    };

    function setWay(way) {
      ways.forEach(function (b) {
        b.setAttribute('aria-selected', String(b.getAttribute('data-lg-way') === way));
      });
      panels.forEach(function (p) {
        p.hidden = p.getAttribute('data-lg-panel') !== way;
      });
      /* 上面那批"这次要填什么"跟着走：只留这件事真正要填的那几项，其余收起 */
      var shown = 0;
      lensItems.forEach(function (it) {
        var need = it.getAttribute('data-need');
        if (need !== '第一次进这台设备' && need !== '换一台设备登录' && need !== '我忘了密码') return;
        var on = (way === 'id')
          ? (need === '第一次进这台设备')
          : (need === '换一台设备登录' || need === '我忘了密码');
        it.setAttribute('data-lg-fit', String(on));
        if (on) shown++;
      });
      if (elNeedN) elNeedN.textContent = '填 2 项 · 相关 ' + shown + ' 条说明';
      if (elEcho) elEcho.textContent = NEED_TEXT[way] || '';
    }

    ways.forEach(function (b) {
      b.addEventListener('click', function () {
        setWay(b.getAttribute('data-lg-way'));
        var first = view.querySelector('[data-lg-panel="' + b.getAttribute('data-lg-way') + '"] .lg-field__i');
        if (first) first.focus();
      });
    });

    /* 提交：先把同意项当回事，再明说这一次不会真的登录 */
    if (box) box.addEventListener('submit', function (e) {
      e.preventDefault();
      var agree = view.querySelector('#lgAgree');
      var echo = view.querySelector('#lgEcho');
      if (agree && !agree.checked) {
        if (echo) echo.textContent = '上面那个同意项还没勾：这一页只用于界面评审，勾上不表示你接受了任何服务条款。';
        C2.toast('先勾一下"我读过使用说明"—— 演示里它也是真的前置条件', 'warn');
        agree.focus();
        return;
      }
      var way = view.querySelector('[data-lg-way][aria-selected="true"]').getAttribute('data-lg-way');
      if (echo) echo.textContent = '演示样张：没有发生登录，也没有向学校或任何服务发送请求。';
      C2.toast(way === 'id'
        ? '演示样张：学号与密码不会被校验，也不会发出去'
        : '演示样张：没有短信发出，验证码不会被校验');
    });

    var other = view.querySelector('#lgOther');
    if (other) other.addEventListener('click', function () {
      C2.toast('演示样张不接第三方登录：不出现任何第三方品牌名，也不跳转');
    });

    setWay('id');
  });
})();
