# -*- coding: utf-8 -*-
"""애니메이션 데모 영상: 부팅 → 빠른 키 → 제안 출력 → 확정 도장 → 학습 +1 → 서랍 → 알림 → 전원 끄기."""
import os, sys, tempfile, time, glob, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e_ui
from playwright.sync_api import sync_playwright

out_dir = sys.argv[1]
with tempfile.TemporaryDirectory() as tmp:
    fake, app, url, _, _ = e2e_ui.start_stack("native", tmp)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            ctx = b.new_context(viewport={"width": 460, "height": 800}, locale="ko-KR", **e2e_ui.TZ_ARG,
                                record_video_dir=tmp, record_video_size={"width": 460, "height": 800})
            p = ctx.new_page()
            p.goto(url)
            p.wait_for_selector(".msg.bot"); p.wait_for_timeout(900)
            def typ(text, wait=900):
                p.click("#msg"); p.keyboard.type(text, delay=35); p.wait_for_timeout(150); p.keyboard.press("Enter"); p.wait_for_timeout(wait)
            p.keyboard.press("Alt+1"); p.wait_for_timeout(1300)
            typ("월요일 3시 김과장 미팅 잡아줘 3A에서", 1600)
            p.click(".card.pending .okb"); p.wait_for_timeout(1900)
            typ("/학습 스크럼은 항상 15분", 1400)
            p.keyboard.press("Alt+m"); p.wait_for_timeout(1300)
            p.keyboard.press("Escape"); p.wait_for_timeout(400)
            p.click("#day-count"); p.wait_for_timeout(1400)
            p.keyboard.press("Escape"); p.wait_for_timeout(400)
            typ("/알림", 2200)
            p.click("#toast-x"); p.wait_for_timeout(400)
            p.once("dialog", lambda d: d.accept())
            p.click("#power"); p.wait_for_timeout(1900)
            video = p.video.path()
            ctx.close(); b.close()
            shutil.copy(video, os.path.join(out_dir, "secretary-1-demo.webm"))
            print("saved", os.path.join(out_dir, "secretary-1-demo.webm"), os.path.getsize(os.path.join(out_dir, "secretary-1-demo.webm")))
    finally:
        app.terminate(); fake.terminate()
