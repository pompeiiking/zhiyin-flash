/* =============================================================================
 * 账号设置 · 视图行为
 * -----------------------------------------------------------------------------
 * 这一页的开关不是"拨一下就完"：每一处拨动都要**当场说出失去了什么**，
 * 并且把依赖它的东西（.st-impact 的 chip、下面 .st-conseq 的那一条判断）一起改掉。
 * 三件事都做，才算"后果显形"：
 *   1. 开关自己的状态文案：已授权 → 已撤回 · 刚刚（可回滚）
 *   2. 「依赖它的是」那枚 chip：变成"停用中 —— …"
 *   3. 连坐清单：对应那条判断变成"信息不足"，计数 -1
 * 数字全部从 DOM 算出来，不写死。
 * ========================================================================== */
(function () {
  'use strict';

  /* 每一项授权拨回去之后，依赖它的东西变成什么样（词与卡片里那三行问答对齐） */
  var IMPACT = {
    '学籍与就读状态': '停用中 —— 画像 3 条退回待你确认 · 3 个里程碑要你每周自己确认',
    '课程、成绩与本周课表': '停用中 —— 成绩层级停用 · 排期改用你手填的 6 小时',
    '行为记录（投递与完成情况）': '停用中 —— 画像 1 条退回信息不足 · 复盘仍按已有记录算'
  };
  /* 连坐清单里哪一条由哪项授权撑着（.st-conseq__i 的 data-need） */
  var NEED = { edu: '学籍与就读状态', aca: '课程、成绩与本周课表', beh: '行为记录（投递与完成情况）' };

  C2.onView('settings', function () {
    var view = document.querySelector('[data-view="settings"]');
    if (!view || view.getAttribute('data-st-init') === 'true') return;
    view.setAttribute('data-st-init', 'true');

    var seqItems = Array.prototype.slice.call(view.querySelectorAll('.st-conseq__i'));
    var elConcN = view.querySelector('#stConcN');
    var elConseqEcho = view.querySelector('#stConseqEcho');
    var elNotifyN = view.querySelector('#stNotifyN');
    var elNotifyEcho = view.querySelector('#stNotifyEcho');
    var elAuthN = view.querySelector('#stAuthN');

    /* ---- 授权开关 -------------------------------------------------------- */
    var authInputs = Array.prototype.slice.call(view.querySelectorAll('.st-auth .st-sw__i'));

    function repaintAuth() {
      var on = 0, total = 0;
      authInputs.forEach(function (inp) {
        var card = inp.closest('.st-auth');
        var isOn = inp.checked;
        total++;
        if (isOn) on++;
        card.setAttribute('data-on', String(isOn));
        var s = card.querySelector('[data-st-state]');
        if (s) {
          var base = inp.getAttribute('data-st-base');
          if (base === null) { base = s.textContent; inp.setAttribute('data-st-base', base); }
          s.textContent = isOn ? base : '已撤回 · 刚刚';
        }
        var chip = card.querySelector('[data-st-chip]');
        if (chip) {
          var chipOn = inp.getAttribute('data-st-chip-on');
          if (chipOn === null) { chipOn = chip.textContent; inp.setAttribute('data-st-chip-on', chipOn); }
          chip.textContent = isOn ? chipOn : (IMPACT[inp.getAttribute('data-st-name')] || '停用中');
        }
      });
      if (elAuthN) elAuthN.textContent = '已授权 ' + on + ' / ' + total;

      /* 连坐：撤掉授权 → 那条判断当场变成"信息不足"，并计数 */
      var broken = 0;
      seqItems.forEach(function (li) {
        var need = NEED[li.getAttribute('data-need')];
        var inp = authInputs.filter(function (i) { return i.getAttribute('data-st-name') === need; })[0];
        var isBroken = !!(inp && !inp.checked);
        li.setAttribute('data-broken', String(isBroken));
        if (isBroken) broken++;
      });
      var alive = seqItems.length - broken;
      if (elConcN) elConcN.textContent = String(alive);
      if (elConseqEcho) {
        elConseqEcho.textContent = broken === 0
          ? '撤掉任何一项，对应那条会当场变成「信息不足」，而不是悄悄消失。'
          : '已经有 ' + broken + ' 条判断变成「信息不足」：它还在页面上，但现在写着"依据不足"，你不会以为它还算数。再打开开关就恢复。';
      }
    }

    authInputs.forEach(function (inp) {
      inp.addEventListener('change', function () {
        repaintAuth();
        var name = inp.getAttribute('data-st-name');
        C2.toast(inp.checked ? inp.getAttribute('data-st-on') : '已撤回「' + name + '」：' + IMPACT[name]);
      });
    });

    /* ---- 通知开关：不减少别处的数字，但要说清关掉后哪件事不再出现 ---- */
    var notifyInputs = Array.prototype.slice.call(view.querySelectorAll('.st-rows--sw .st-sw__i'));

    function repaintNotify() {
      var on = 0;
      notifyInputs.forEach(function (i) { if (i.checked) on++; });
      if (elNotifyN) elNotifyN.textContent = '已开 ' + on + ' / ' + notifyInputs.length;
      if (elNotifyEcho) {
        var off = notifyInputs.filter(function (i) { return !i.checked; })
          .map(function (i) { return i.getAttribute('data-st-name'); });
        elNotifyEcho.textContent = off.length === 0
          ? '4 项全开着：每天 8:30 一次、里程碑提前 2 天、每周一上午一次、停滞 3 天开口一次（冷却 48 小时，7 天最多 2 次）。'
          : '现在关着 ' + off.length + ' 项：' + off.join('、') + '。关掉不会让对应的事消失 —— 它只是不再主动出现。';
      }
    }

    notifyInputs.forEach(function (inp) {
      inp.addEventListener('change', function () {
        repaintNotify();
        var name = inp.getAttribute('data-st-name');
        C2.toast(inp.checked ? '已打开「' + name + '」' : inp.getAttribute('data-st-off'));
      });
    });

    /* ---- 账号那几行：占位数据，点了只解释，不假装保存 ---- */
    var NICK = view.querySelector('#stNick');
    if (NICK) NICK.addEventListener('change', function () {
      var v = (NICK.value || '').trim() || '陈亦然';
      NICK.value = v;
      C2.toast('昵称已改为「' + v + '」—— 只影响界面称呼，学籍里的姓名没有变');
    });
    var sim = [
      ['#stAvatar', '换头像', '演示样张不做上传：头像不会真的换，也不会存下任何图片'],
      ['#stPhone', '换号', '占位号码 138****0000：改号要走验证码，演示里不发短信'],
      ['#stMail', '换邮箱', '占位邮箱 demo@example.com：演示里不发任何邮件'],
      ['#stUpload', '自己传一份', '实习单位评价需要单位出具，学校这边取不到 —— 演示里不会真的上传'],
      ['#stExport', '导出我的资料', '演示样张：会导出画像 15 条与报告，含每条的来源与把握度，不联网也能打开'],
      ['#stExport2', '导出我的资料', '演示样张：先导出一份再决定注不注销 —— 导出内容包含来源与把握度']
    ];
    sim.forEach(function (row) {
      var b = view.querySelector(row[0]);
      if (!b) return;
      b.addEventListener('click', function () {
        var echo = view.querySelector('#stPrivEcho');
        if (echo && row[0].indexOf('Export') >= 0) echo.textContent = row[2];
        C2.toast(row[2]);
      });
    });

    /* ---- 清空咨询记录：连坐说清楚（画像里"来自对话"的条目会退回待验证） ---- */
    var WIPE = view.querySelector('#stWipe');
    if (WIPE) WIPE.addEventListener('click', function () {
      var echo = view.querySelector('#stPrivEcho');
      var msg = '已清空 14 轮对话：画像里 8 条「来自对话」的条目全部退回「待验证」—— 它们的依据就是那些话';
      if (echo) echo.textContent = msg + '。这一步在本页可以撤销，注销之后就不行了。';
      C2.toast(msg);
    });

    /* ---- 注销：两步，第一步只让你再看一遍后果 ---- */
    var DEL = view.querySelector('#stDelete');
    if (DEL) DEL.addEventListener('click', function () {
      var echo = view.querySelector('#stPrivEcho');
      if (DEL.getAttribute('data-armed') !== 'true') {
        DEL.setAttribute('data-armed', 'true');
        DEL.textContent = '确认注销（不可撤销）';
        if (echo) echo.textContent = '再确认一次：学信网与教务授权撤回，画像 15 条、14 轮对话、报告与方向方案一起删除；成长记录里已解锁的三项保留。';
        C2.toast('注销不可撤销：再点一次确认，或先去上面导出一份', 'warn');
        return;
      }
      DEL.textContent = '已注销（演示）';
      DEL.disabled = true;
      if (echo) echo.textContent = '演示样张里没有真的注销 —— 这一页只是把"会发生什么"写给你看。';
      C2.toast('演示样张：不会真的注销，也不会删掉任何东西', 'warn');
    });

    repaintAuth();
    repaintNotify();
  });
})();
