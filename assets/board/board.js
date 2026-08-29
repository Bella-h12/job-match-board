/* 求职看板 · 前端交互（2026-08-13 起页面重新有 JS）
 *
 * 只做两件事：
 *   1. 侧边栏的计数从 DOM 现数，不写死——数字和页面上真实存在的条目永远对得上。
 *   2. ✓「我投了」的标记。
 *
 * ✓ 这件事有一条必须守住的边界：**它不是「已投」的凭据，只是 Bella 的一次声明**。
 * 台账里那些条目都带着邮件原话或 LinkedIn 指纹行当凭据；页面上点一下没有这些。
 * 所以本地标记单独一种样式、单独一句话说明「待值班员核」，绝不混进「已投待回」
 * 那一堆里假装是同一件事（R19-3、R19-4）。
 *
 * 存储只有 localStorage 可用（Artifact 运行时没给数据库能力），意味着：
 * 换浏览器 / 换设备就看不到这些标记。所以必须提供导出，让它能真的回到
 * applications.json 里去——那才是唯一的事实源。
 */
(function () {
  'use strict';

  var KEY = 'jobsboard.marked.v1';
  var SKIP = 'jobsboard.skipped.v1';   // 「不适合」归档掉的岗，跟「已投」是两回事

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; }
  }
  function save(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {}
  }
  function jobIdOf(el) {
    var a = el.querySelector('a[href*="/jobs/view/"]');
    if (!a) return null;
    var m = a.getAttribute('href').match(/\/jobs\/view\/(\d+)/);
    return m ? m[1] : null;
  }
  function textOf(el, sel) {
    var n = el.querySelector(sel);
    return n ? n.textContent.trim().replace(/\s+/g, ' ') : '';
  }

  /* ---------- 侧边栏计数：现数 DOM，别写死 ---------- */
  /* 分组计数：从某个分组标题开始，数到下一个分组标题为止。
     这样「点 ✓ 之后数字要跟着变」是自动成立的——数的就是页面上真实剩下的东西，
     不存在第二份计数需要同步（R7：一个对外的数字只能有一个来源）。 */
  function countAfter(startId, rowSel, stopSel) {
    var start = document.getElementById(startId);
    if (!start) return 0;
    var n = 0, el = start.nextElementSibling;
    while (el) {
      if (el.matches(stopSel)) break;
      if (el.matches(rowSel) && !el.hidden) n++;
      el = el.nextElementSibling;
    }
    return n;
  }

  function recount() {
    /* 2026-08-18：台账拆成四段独立 section 之后，「数到下一个分组标题为止」这套
       不需要了 —— 每一段就是一个 section，直接数它里面的 .lg-row。
       仍然是现数 DOM，点 ✓ 之后数字自动跟着变（一个数字只能有一个来源）。 */
    function inSec(id, sel) {
      var n = document.getElementById(id);
      if (!n) return 0;
      return Array.prototype.filter.call(n.querySelectorAll(sel), function (e) {
        return !e.hidden;
      }).length;
    }
    var c = {
      fresh: countAfter('fresh', '.jc', '.grp'),
      rest: countAfter('rest', '.jc', '.grp'),
      /* 2026-08-27 加：「判据未核 / JD 无硬门槛」那组卡也在 01 这一屏里，
         漏掉它，侧栏就会说 52 而标题说 3 + 53 —— 同一屏两个数（R7）。
         今早适配度改版之前这一组恒为 0，所以这个洞一直没露。 */
      unscored: countAfter('unscored', '.jc', '.grp'),
      waiting: inSec('waiting', '.lg-row'),
      interviewing: inSec('interviewing', '.lg-row'),
      offers: inSec('offers', '.lg-row'),
      rejected: inSec('rejected', '.lg-row'),
      visible: document.querySelectorAll('#visible .vz-row').length,
      /* 第五部分数的是「渠道体检」那张表的行数＝扫了几家中介，不是岗位数。
         别改成数全部 .lg-row —— 那张 section 里还有「值得投的」4 条，两个语义混一起。
         也别写 .ledger:first-of-type —— :first-of-type 按标签名算不按 class 算，
         #agencies 的第一个 div 是 .callout，那个选择器恒为空（8-13 实测数出 0）。 */
      agencies: (function () {
        var t = document.querySelector('#agencies .ledger');
        return t ? t.querySelectorAll('.lg-row').length : 0;
      })()
    };
    c.apply = c.fresh + c.rest + c.unscored;   /* 决策台那三张是下面那些里的三张，不重复计 */
    Object.keys(c).forEach(function (k) {
      Array.prototype.forEach.call(document.querySelectorAll('[data-count="' + k + '"]'), function (b) {
        b.textContent = c[k];
      });
    });
  }

  /* ---------- 已被值班员用真凭据收录的，本地标记就该退场 ---------- */
  function confirmedIds() {
    var s = {};
    /* :not(.lg-mine) 是必须的 —— 本地标记的那些行自己也带 data-job-id，
       不排掉的话它们会把自己当成「已被值班员收录」然后自我删除。 */
    Array.prototype.forEach.call(document.querySelectorAll('.lg-row[data-job-id]:not(.lg-mine)'), function (r) {
      var id = r.getAttribute('data-job-id');
      if (id) s[id] = true;
    });
    return s;
  }

  /* ---------- 把一条本地标记渲染进「已申请但没有面试」 ---------- */
  function renderMine(list, justId) {
    /* 插槽在「已投无消息」那段的台账容器最前面，由 render-applications.py 生成。
       别再用 `#waiting 之后` —— #waiting 现在是整个 section，插在它后面
       等于插到了下一段里去。 */
    var slot = document.getElementById('mine-slot-waiting');
    if (!slot) return;
    Array.prototype.forEach.call(document.querySelectorAll('.lg-row.lg-mine'), function (n) { n.remove(); });
    var note = document.getElementById('mine-note');
    if (note) note.remove();
    if (!list.length) { recount(); return; }

    var p = document.createElement('p');
    p.className = 'lg-note';
    p.id = 'mine-note';
    p.innerHTML = '<b>下面 ' + list.length + ' 条是你自己在这页上标的</b>，还没有凭据。'
      + '下次跑批会去邮箱核实，核到了才并进台账。';
    slot.insertAdjacentElement('afterend', p);

    /* 跟台账里其他行同一套结构（也是 <details>），否则它长得像另一种东西 */
    var after = p;
    list.forEach(function (m) {
      var d = document.createElement('details');
      d.className = 'lg-row lg-mine' + (m.id === justId ? ' landed' : '');
      d.setAttribute('data-job-id', m.id || '');
      d.innerHTML =
        '<summary class="lg-sum"><div class="lg-main"><div class="lg-t">' + m.title + '</div>'
        + '<div class="jc-mini"><span>' + m.at + ' 你标的</span><span>还没有凭据</span></div>'
        + '<div class="lg-lead"><span class="act-s ref">等值班员核实</span></div></div>'
        + '<div class="lg-stage">待核</div>'
        + '<div class="lg-ops"><span class="jc-more">详情</span></div></summary>'
        + '<div class="lg-body"><p class="lg-src"><b>凭据</b>无 —— 这条只有你在看板上点了 ✓ '
        + '这一个来源，待下次跑批去邮箱核实。</p></div>';
      after.insertAdjacentElement('afterend', d);
      after = d;
    });
  }

  /* ---------- 应用存量标记：把对应的待申请卡片藏起来 ---------- */
  function applyMarks(justId) {
    var list = load();
    var done = confirmedIds();
    var kept = list.filter(function (m) { return !done[m.id]; });
    if (kept.length !== list.length) save(kept);

    var byId = {};
    kept.forEach(function (m) { byId[m.id] = true; });

    var skipped = {};
    loadSkips().forEach(function (m) { skipped[m.id] = true; });
    Array.prototype.forEach.call(document.querySelectorAll('.jc, .t10row, .tcard'), function (el) {
      var id = jobIdOf(el);
      if (id && (byId[id] || skipped[id])) el.hidden = true;
    });
    renderSkips();

    renderMine(kept, justId);
    var btn = document.getElementById('btn-export');
    if (btn) {
      btn.hidden = kept.length === 0;
      var n = document.getElementById('mark-n');
      if (n) n.textContent = kept.length;
    }
    recount();
  }

  /* ---------- ✓ 按钮 ---------- */
  var CHECK = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10.5l4 4 8-9"/></svg>';

  function addButtons() {
    /* 今日决策台的三张卡（2026-08-18）：按钮插进 .tc-ops，「详情」已经在里面了 */
    Array.prototype.forEach.call(document.querySelectorAll('.tcard'), function (el) {
      if (!jobIdOf(el) || el.querySelector('.mark')) return;
      var ops = el.querySelector('.tc-ops');
      if (!ops) return;
      ops.insertBefore(mkSkip(el), ops.firstChild);
      ops.appendChild(mkBtn(el));
    });
    Array.prototype.forEach.call(document.querySelectorAll('.t10row'), function (el) {
      if (!jobIdOf(el) || el.querySelector('.mark')) return;
      var b = mkBtn(el);
      var ops = el.querySelector('.t10ops');
      if (ops) {
        var more = ops.querySelector('.t10more');
        ops.insertBefore(mkSkip(el), more);
        ops.insertBefore(b, more);
      } else {
        var sc = el.querySelector('.t10sc');
        if (sc) { el.insertBefore(mkSkip(el), sc); el.insertBefore(b, sc); }
        else { el.appendChild(mkSkip(el)); el.appendChild(b); }
      }
    });
    /* 2026-08-18：按钮改挂到 summary 右侧的 .jc-ops（不适合 / ✓已投 / 查看详情
       三个并排）。.jc-ops 是 rebuild-board.py 一定会生成的，找不到就说明模板和
       这段脚本脱节了 —— 那种情况下**不要静默什么都不做**（按钮永远不出现，
       而页面看起来一切正常），退回把按钮挂在卡片头上，至少还点得到。 */
    Array.prototype.forEach.call(document.querySelectorAll('.jc'), function (el) {
      if (!jobIdOf(el) || el.querySelector('.mark')) return;
      var b = mkBtn(el);
      var ops = el.querySelector('.jc-ops');
      if (ops) {
        var more = ops.querySelector('.jc-more');
        ops.insertBefore(mkSkip(el), more);
        ops.insertBefore(b, more);
      } else {
        var sum = el.querySelector('.jc-sum');
        if (sum) { sum.appendChild(mkSkip(el)); sum.appendChild(b); }
      }
    });
  }

  /* ---------- 「不适合」：把这个岗归档，不是投了 ---------- */
  function loadSkips() {
    try { return JSON.parse(localStorage.getItem(SKIP) || '[]'); } catch (e) { return []; }
  }
  function saveSkips(l) { try { localStorage.setItem(SKIP, JSON.stringify(l)); } catch (e) {} }

  function mkSkip(el) {
    var b = document.createElement('button');
    b.className = 'skip-btn';
    b.type = 'button';
    b.textContent = '不适合';
    b.title = '归档这个岗，不再出现在待申请里';
    b.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation(); skip(el);
    });
    return b;
  }

  function skip(el) {
    var id = jobIdOf(el);
    if (!id) return;
    var co = textOf(el, '.t10co a') || textOf(el, '.jc-co a');
    var role = textOf(el, '.t10role') || textOf(el, '.jc-role');
    var l = loadSkips();
    if (!l.some(function (m) { return m.id === id; })) { l.push({ id: id, company: co, role: role }); saveSkips(l); }
    var twins = [];
    Array.prototype.forEach.call(document.querySelectorAll('.jc, .t10row, .tcard'), function (n) {
      if (jobIdOf(n) === id) twins.push(n);
    });
    twins.forEach(function (n) { n.classList.add('fading'); });
    setTimeout(function () {
      twins.forEach(function (n) { n.classList.remove('fading'); n.hidden = true; });
      applyMarks();
      toast('已归档 ' + (co || '这个岗'));
    }, 340);
  }

  function unskip(id) {
    saveSkips(loadSkips().filter(function (m) { return m.id !== id; }));
    Array.prototype.forEach.call(document.querySelectorAll('.jc, .t10row, .tcard'), function (n) {
      if (jobIdOf(n) === id) n.hidden = false;
    });
    applyMarks();
  }

  /* 归档区渲染在待申请段末尾：**归档不等于消失**，随时能翻出来撤销 */
  function renderSkips() {
    var list = loadSkips();
    var box = document.getElementById('skipbox');
    if (!list.length) { if (box) box.remove(); return; }
    if (!box) {
      box = document.createElement('details');
      box.className = 'skipped'; box.id = 'skipbox';
      var host = document.getElementById('overreach');
      if (host && host.parentNode) host.parentNode.insertBefore(box, host); else return;
    }
    box.innerHTML = '<summary>你标为「不适合」的 ' + list.length + ' 个 · 点开可撤销</summary>'
      + list.map(function (m) {
        return '<div class="sk-row"><span>' + m.company + ' · ' + m.role + '</span>'
          + '<button class="sk-undo" data-undo="' + m.id + '">撤销</button></div>';
      }).join('');
    Array.prototype.forEach.call(box.querySelectorAll('[data-undo]'), function (b) {
      b.addEventListener('click', function () { unskip(b.getAttribute('data-undo')); });
    });
  }

  function mkBtn(el) {
    var b = document.createElement('button');
    b.className = 'mark';
    b.type = 'button';
    b.innerHTML = CHECK;
    b.title = '我已经投了这个岗';
    b.setAttribute('aria-label', '标记为已投递');
    b.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      mark(el, b);
    });
    return b;
  }

  function mark(el, btn) {
    var id = jobIdOf(el);
    if (!id) return;
    var list = load();
    if (list.some(function (m) { return m.id === id; })) return;

    var co = textOf(el, '.t10co a') || textOf(el, '.jc-co a');
    var role = textOf(el, '.t10role') || textOf(el, '.jc-role');
    var d = new Date();
    var at = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
      + '-' + String(d.getDate()).padStart(2, '0');

    list.push({
      id: id,
      company: co,
      role: role,
      at: at,
      title: '<a class="jd-link" href="https://www.linkedin.com/jobs/view/' + id
        + '/" target="_blank" rel="noopener">' + co + ' · ' + role + '</a>'
    });
    save(list);

    btn.classList.add('on');
    btn.disabled = true;
    firework(btn);

    // 同一个岗在 Top 10 和卡片列表里各有一份，两处一起收
    var twins = [];
    Array.prototype.forEach.call(document.querySelectorAll('.jc, .t10row, .tcard'), function (n) {
      if (jobIdOf(n) === id) twins.push(n);
    });
    twins.forEach(function (n) { n.classList.add('marking', 'collapsing'); });
    setTimeout(function () {
      twins.forEach(function (n) {
        n.classList.remove('marking', 'collapsing');
        n.hidden = true;
      });
      applyMarks(id);
      toast(co);
    }, 720);
  }

  /* 烟花：粒子挂在 body 上、fixed 定位，免得被卡片的 overflow:hidden 剪掉 */
  function firework(btn) {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var r = btn.getBoundingClientRect();
    var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    var box = document.createElement('div');
    box.className = 'fx';
    box.style.transform = 'translate(' + cx + 'px,' + cy + 'px)';
    var ring = document.createElement('div');
    ring.className = 'fx-ring';
    box.appendChild(ring);
    for (var i = 0; i < 16; i++) {
      var p = document.createElement('i');
      var a = (Math.PI * 2 * i) / 16 + (Math.random() - 0.5) * 0.3;
      var d = 34 + Math.random() * 46;
      p.style.setProperty('--dx', Math.cos(a) * d + 'px');
      p.style.setProperty('--dy', Math.sin(a) * d + 'px');
      p.style.animationDelay = (Math.random() * 0.05) + 's';
      box.appendChild(p);
    }
    document.body.appendChild(box);
    setTimeout(function () { box.remove(); }, 900);
  }

  /* 目标区在页面很下面，不给一句反馈的话，点完像什么都没发生 */
  var toastTimer = null;
  function toast(co) {
    var t = document.getElementById('toast');
    if (!t) {
      t = document.createElement('div');
      t.className = 'toast';
      t.id = 'toast';
      document.body.appendChild(t);
    }
    t.innerHTML = '已记下 <b>' + (co || '这个岗') + '</b> · '
      + '<a href="#waiting">去「已投无消息」看</a>';
    requestAnimationFrame(function () { t.classList.add('on'); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('on'); }, 4200);
  }

  /* ---------- 导出：让本地标记能真的回到 applications.json ---------- */
  function wireExport() {
    var btn = document.getElementById('btn-export');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var list = load();
      if (!list.length) return;
      var payload = JSON.stringify({
        exported_at: new Date().toISOString(),
        note: '来自看板上的 ✓ 标记，尚无邮件凭据。值班员：逐条去邮箱找确认信，'
          + '找到了再写进 applications.json 并附 evidence 原话；找不到的保留在这里别升级。',
        marked: list.map(function (m) {
          return { job_id: m.id, company: m.company, role: m.role, marked_on: m.at };
        })
      }, null, 2);
      var name = 'marked-' + (list[0] ? list[0].at : 'today') + '.json';

      if (window.claude && window.claude.downloads && window.claude.downloads.save) {
        window.claude.downloads.save({ filename: name, data: payload }).catch(function () {
          fallback(payload);
        });
      } else {
        fallback(payload);
      }
    });
  }

  function fallback(payload) {
    // 下载被拒或不可用时，退到剪贴板；两条路都失败就明说失败，不装作成功
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(payload).then(function () {
        flash('下载没走成，内容已复制到剪贴板');
      }, function () {
        flash('导出失败：下载和剪贴板都不可用');
      });
    } else {
      flash('导出失败：这个浏览器不支持下载或剪贴板');
    }
  }

  function flash(msg) {
    var btn = document.getElementById('btn-export');
    if (!btn) return;
    var old = btn.innerHTML;
    btn.textContent = msg;
    setTimeout(function () { btn.innerHTML = old; }, 2600);
  }

  /* Top 10 的「查看详情」→ 跳到下面那张卡。<details> 不会因为锚点自己展开，
     所以必须显式 open —— 不 open 的话跳过去看到的还是收起态，等于没跳。 */
  function wireJump() {
    document.addEventListener('click', function (e) {
      var a = e.target.closest ? e.target.closest('.t10more') : null;
      if (!a) return;
      var t = document.getElementById(a.getAttribute('href').slice(1));
      if (!t) return;                       // 卡片被 ✓ / 不适合 收走了，让浏览器自己处理
      e.preventDefault();
      t.open = true;
      t.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
  }

  function init() {
    addButtons();
    wireJump();
    applyMarks();
    wireExport();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
