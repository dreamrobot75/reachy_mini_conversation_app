import os
import subprocess
import sys
import time

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    html_path = os.path.join(repo_root, "docs", "oss_report", "발표자료.html")
    output_dir = os.path.join(repo_root, "docs", "oss_report", "slides_png")
    os.makedirs(output_dir, exist_ok=True)

    # Detect browser
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    browser_bin = None
    for p in edge_paths:
        if os.path.exists(p):
            browser_bin = p
            break
    if not browser_bin:
        for p in chrome_paths:
            if os.path.exists(p):
                browser_bin = p
                break

    if not browser_bin:
        print("Error: neither Edge nor Chrome found.")
        sys.exit(1)

    print(f"Using browser: {browser_bin}")
    total_slides = 13

    slide_names = [
        "01_표지",
        "02_개발배경_및_목표",
        "03_시스템_아키텍처",
        "04_기능_비교_및_차별성",
        "05_시연_시나리오_개요",
        "06_서면평가_기준_충족도",
        "07_기대효과_및_로드맵",
        "08_시연_1단계_간지",
        "09_시연_2단계_간지",
        "10_시연_3단계_간지",
        "11_시연_4단계_간지",
        "12_시연_5단계_간지",
        "13_마무리_및_QnA",
    ]

    for i in range(total_slides):
        name = slide_names[i] if i < len(slide_names) else f"slide_{i+1:02d}"
        output_png = os.path.join(output_dir, f"{name}.png")
        url = f"file:///{html_path.replace(os.sep, '/')}?slide={i}&capture=true"

        cmd = [
            browser_bin,
            "--headless=new",
            "--disable-gpu",
            "--window-size=1920,1080",
            "--force-device-scale-factor=1",
            "--hide-scrollbars",
            "--virtual-time-budget=2000",
            f"--screenshot={output_png}",
            url,
        ]

        print(f"[{i+1}/{total_slides}] Capturing {name}.png ...")
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_png):
            print(f"  -> Saved ({os.path.getsize(output_png):,} bytes)")
        else:
            print(f"  -> Failed to create {name}.png")

    print(f"\nAll slides exported successfully to: {output_dir}")

if __name__ == "__main__":
    main()
