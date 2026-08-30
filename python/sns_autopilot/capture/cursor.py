"""영상에 마우스 커서와 클릭 파장을 그려주는 오버레이 스크립트 (브라우저에서 실행)."""

CURSOR_INIT_SCRIPT = r"""
(() => {
  if (window.__autopilotCursor) return;
  window.__autopilotCursor = true;
  const install = () => {
    if (!document.body) return;
    const style = document.createElement("style");
    style.textContent = `
      #ap-cursor{position:fixed;left:0;top:0;width:26px;height:26px;margin:-13px 0 0 -13px;
        border-radius:50%;background:rgba(255,255,255,.35);border:2px solid rgba(20,20,20,.7);
        box-shadow:0 2px 8px rgba(0,0,0,.35);pointer-events:none;z-index:2147483647;
        transition:transform .08s ease-out}
      #ap-cursor.ap-down{transform:scale(.72)}
      .ap-ripple{position:fixed;width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;
        border:3px solid rgba(79,195,247,.95);pointer-events:none;z-index:2147483646;
        animation:ap-ripple .55s ease-out forwards}
      @keyframes ap-ripple{to{width:76px;height:76px;margin:-38px 0 0 -38px;opacity:0}}
      .ap-focus{outline:3px solid rgba(79,195,247,.95)!important;outline-offset:3px!important;
        border-radius:8px;transition:outline-color .2s}
      @keyframes ap-pulse{0%,100%{box-shadow:0 0 0 0 rgba(79,195,247,.85)}50%{box-shadow:0 0 0 14px rgba(79,195,247,0)}}
      .ap-pulse{animation:ap-pulse 1.1s ease-out 2}
    `;
    document.head.appendChild(style);
    const dot = document.createElement("div");
    dot.id = "ap-cursor";
    dot.style.transform = "translate3d(-100px,-100px,0)";
    document.body.appendChild(dot);
    addEventListener("mousemove", (e) => {
      dot.style.left = e.clientX + "px";
      dot.style.top = e.clientY + "px";
    }, true);
    addEventListener("mousedown", (e) => {
      dot.classList.add("ap-down");
      const r = document.createElement("div");
      r.className = "ap-ripple";
      r.style.left = e.clientX + "px";
      r.style.top = e.clientY + "px";
      document.body.appendChild(r);
      setTimeout(() => r.remove(), 600);
    }, true);
    addEventListener("mouseup", () => dot.classList.remove("ap-down"), true);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
  else install();
})();
"""
