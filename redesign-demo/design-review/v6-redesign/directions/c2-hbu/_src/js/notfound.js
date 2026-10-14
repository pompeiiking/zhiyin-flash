/* =============================================================================
 * 异常页 · 视图行为（key=notfound）
 * -----------------------------------------------------------------------------
 * 只做两件事，都不带动效：
 *   1. 三态切换（404 / 无权限 / 服务不可用）—— 改 hidden，不搬动、不淡入；
 *   2. 有效地址清单 —— **从外壳注入的 #viewRegistry 生成**，不在这里写死第二份
 *      清单（build.mjs 的那份来自 _src/views.json，是唯一来源）。
 *      这样"地址列表"永远不会指向一个不存在的页面，也不会漏掉新加的页面。
 *
 * 为什么地址列表必须动态生成：BRIEF §6 与上一轮的裁定都点在"写死第二份清单"上
 * （lib/workspace-nav.ts 的 INTERNAL_PAGE_TITLES 就是被这件事逼出来的补丁）。
 * 标记里那份清单只是 JS 没跑起来时的兜底，跑起来就被替换掉。
 * ========================================================================== */
(function () {
  'use strict';

  C2.onView('notfound', function () {
    var root = document.querySelector('[data-view="notfound"]');
    if (!root) return;

    /* ---- 1. 三态切换 ------------------------------------------------------ */
    var btns = Array.prototype.slice.call(root.querySelectorAll('[data-nf-set]'));
    var panels = Array.prototype.slice.call(root.querySelectorAll('[data-nf-panel]'));

    function setState(name) {
      panels.forEach(function (p) {
        p.hidden = p.getAttribute('data-nf-panel') !== name;
      });
      btns.forEach(function (b) {
        b.setAttribute('aria-selected', String(b.getAttribute('data-nf-set') === name));
      });
    }

    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        setState(b.getAttribute('data-nf-set'));
      });
    });

    /* 键盘左右键在三态之间走 —— 它长得像分段控件，就得像分段控件一样能用。
       只在组内响应，不动别的视图的 .lensbtn。 */
    btns.forEach(function (b, i) {
      b.addEventListener('keydown', function (e) {
        var next = null;
        if (e.key === 'ArrowRight') next = (i + 1) % btns.length;
        else if (e.key === 'ArrowLeft') next = (i - 1 + btns.length) % btns.length;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = btns.length - 1;
        if (next === null) return;
        e.preventDefault();
        setState(btns[next].getAttribute('data-nf-set'));
        btns[next].focus();
      });
    });

    /* 404 那一态要说清"你打开的到底是哪个地址" —— 地址本身从 location.hash 读，
       不写死在文案里（写死了就成了一句假话）。 */
    var asked = document.getElementById('nfAsked');
    if (asked) {
      var hash = (location.hash || '').replace(/^#\/?/, '').trim();
      asked.textContent = hash ? '#/' + hash : '（这一页是样张里直接打开的）';
    }

    /* ---- 2. 有效地址清单：读 #viewRegistry --------------------------------- */
    var host = document.getElementById('nfAddrList');
    var count = document.getElementById('nfAddrN');
    if (!host) return;

    var registry = [];
    var raw = document.getElementById('viewRegistry');
    if (raw) {
      try { registry = JSON.parse(raw.textContent) || []; } catch (e) { registry = []; }
    }
    if (!registry.length) return; /* 读不到就保留标记里的兜底清单，不清空 */

    /* 分组顺序：按 views.json 里首次出现的顺序（外壳已经按文件顺序序列化），
       这样"入口与账户 / 系统与规范"排在最后，和学生导航的顺序一致。 */
    var order = [];
    var byGroup = {};
    registry.forEach(function (v) {
      var g = v.group || '其它';
      if (!byGroup[g]) { byGroup[g] = []; order.push(g); }
      byGroup[g].push(v);
    });

    var here = C2.view();
    var html = order.map(function (g) {
      var items = byGroup[g];
      return '<section class="nf-group">' +
        '<p class="nf-group__t"><span>' + C2.esc(g) + '</span>' +
        '<span class="nf-group__n">' + items.length + ' 个</span></p>' +
        '<div class="nf-group__l">' +
        items.map(function (v) {
          var isHere = v.key === here;
          return '<a class="nf-a' + (isHere ? ' nf-a--here' : '') + '" href="#/' + C2.esc(v.key) + '"' +
            (isHere ? ' aria-current="page"' : '') + '>' +
            '<span class="nf-a__t">' + C2.esc(v.title) + '</span>' +
            '<code class="nf-a__k">#/' + C2.esc(v.key) + '</code>' +
            '</a>';
        }).join('') +
        '</div></section>';
    }).join('');

    host.innerHTML = html;
    if (count) count.textContent = registry.length + ' 个';
  });
})();
