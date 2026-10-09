"""Independent design acceptance checks for AA contrast and offline font delivery."""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'src/sonar_web/static'

def luminance(value):
    rgb = [int(value[i:i+2],16)/255 for i in (1,3,5)]
    linear = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))

def contrast(a,b):
    high,low=sorted((luminance(a),luminance(b)),reverse=True)
    return (high+.05)/(low+.05)

class DesignAccessibilityTests(unittest.TestCase):
    def setUp(self):
        self.css = (STATIC/'styles.css').read_text(encoding='utf-8-sig')
        self.themes = []
        for selector in [r':root\s*\{([^}]+)\}',r':root\[data-theme="dark"\]\s*\{([^}]+)\}']:
            block=re.search(selector,self.css).group(1)
            self.themes.append(dict(re.findall(r'--([\w-]+):\s*(#[\da-fA-F]{6})',block)))

    def test_small_text_and_status_contrast_in_both_themes(self):
        for t in self.themes:
            for fg,bg in [('ink','bg'),('ink','surface'),('muted','bg'),('muted','surface'),('muted','surface2'),('accent','surface'),('accent','accent-soft'),('warn','warn-bg'),('danger','warn-bg')]:
                with self.subTest(fg=fg,bg=bg,theme=t['bg']):
                    self.assertGreaterEqual(contrast(t[fg],t[bg]),4.5)

    def test_primary_buttons_and_control_boundaries(self):
        for i,t in enumerate(self.themes):
            self.assertGreaterEqual(contrast(t['accent'],'#ffffff' if i==0 else t['bg']),4.5)
            for bg in ['surface','bg','surface2']:
                self.assertGreaterEqual(contrast(t['control'],t[bg]),3)

    def test_font_rules_resolve_to_packaged_woff2(self):
        fonts=re.findall(r'url\("(/static/[^\"]+\.woff2)"\)',self.css)
        self.assertTrue(fonts)
        for font in fonts:
            self.assertEqual((STATIC/Path(font).name).read_bytes()[:4],b'wOF2')
        self.assertIn('SIL OPEN FONT LICENSE',(STATIC/'PLEX-LICENSE.txt').read_text(encoding='utf-8'))
        self.assertNotRegex(self.css,r'https?://')

    def test_mobile_navigation_and_reduced_motion_are_explicit(self):
        self.assertIn('env(safe-area-inset-bottom)',self.css)
        self.assertIn('prefers-reduced-motion',self.css)
        page=(STATIC/'index.html').read_text(encoding='utf-8')
        self.assertIn('aria-label="Primary navigation"',page)
        self.assertIn('href="#main"',page)
        self.assertNotIn('onclick=',page)
