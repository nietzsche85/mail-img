"""영상에 마우스 커서와 클릭 파장을 그려주는 오버레이 스크립트 (브라우저에서 실행).

화면 캐스트에는 운영체제 커서가 찍히지 않습니다. 그래서 페이지 안에 점을 하나 그려
포인터 위치를 보여줍니다. 수동 녹화에서는 이 점이 영상 속 유일한 포인터입니다.
"""

CURSOR_INIT_SCRIPT = r"""
(() => {
  if (window.__autopilotCursor) return;
  window.__autopilotCursor = true;
  const install = () => {
    if (!document.body) return;
    const style = document.createElement("style");
    style.textContent = `
      #ap-cursor{position:fixed;left:-100px;top:-100px;width:26px;height:26px;
        box-sizing:border-box;margin:-13px 0 0 -13px;
        border-radius:50%;background:rgba(255,255,255,.35);border:2px solid rgba(20,20,20,.7);
        box-shadow:0 2px 8px rgba(0,0,0,.35);pointer-events:none;z-index:2147483647;
        transition:transform .08s ease-out}
      #ap-cursor.ap-down{transform:scale(.72)}
      .ap-ripple{position:fixed;width:12px;height:12px;box-sizing:border-box;
        margin:-6px 0 0 -6px;border-radius:50%;
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
    // 첫 움직임 전까지는 화면 밖에 둡니다.
    // transform 으로 숨기면 그 값이 남아 점이 실제 포인터에서 어긋납니다.
    // 위치는 left/top 으로만 잡고, transform 은 누를 때 크기 줄이는 데만 씁니다.
    document.body.appendChild(dot);

    // 페이지가 body 를 통째로 갈아끼워도(SPA) 점이 사라지지 않게 다시 붙입니다.
    const attach = (el) => { if (!el.isConnected && document.body) document.body.appendChild(el); };

    addEventListener("mousemove", (e) => {
      attach(dot);
      dot.style.left = e.clientX + "px";
      dot.style.top = e.clientY + "px";
    }, true);

    addEventListener("mousedown", (e) => {
      attach(dot);
      dot.classList.add("ap-down");
      const ripple = document.createElement("div");
      ripple.className = "ap-ripple";
      ripple.style.left = e.clientX + "px";
      ripple.style.top = e.clientY + "px";
      document.body.appendChild(ripple);
      setTimeout(() => ripple.remove(), 600);
    }, true);

    addEventListener("mouseup", () => dot.classList.remove("ap-down"), true);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
  else install();
})();
"""
