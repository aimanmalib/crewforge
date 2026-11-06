#!/usr/bin/env python3
"""Render brand/logo.svg to brand/logo-512.png and brand/logo-64.png with Chromium (Playwright).

    uv run --with playwright==1.58.0 python3 brand/jana-aset.py

Same script as sasateguh/codr and sasateguh/mypii. The PNGs are committed because the README is also
shown on PyPI, and not every renderer there draws an SVG with gradients reliably.
"""

import os

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "logo.svg"), encoding="utf-8") as f:
    svg = f.read()
with sync_playwright() as p:
    b = p.chromium.launch()
    for size in (512, 64):
        pg = b.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
        inner = svg.replace('width="256" height="256"', f'width="{size}" height="{size}"')
        pg.set_content(f'<html><body style="margin:0;background:transparent">{inner}</body></html>')
        pg.screenshot(path=os.path.join(HERE, f"logo-{size}.png"), omit_background=True)
    b.close()
