"""
Run the FS22_ArabicLanguage Lua scripts outside the game, against stand-ins for the
engine functions they use, and draw what they would draw with the game's own font.

  python test_mod.py <out.png>

Needs lupa (pip install lupa) for a Lua 5.1 interpreter, like the game's.
"""

import os
import sys
import tempfile
import xml.etree.ElementTree as ET

from lupa.lua51 import LuaRuntime
from PIL import Image

import preview
from add_arabic_glyphs import read_font

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
MOD = os.path.join(GAME, 'FS22_ArabicLanguage')
FONT_DIR = os.path.join(GAME, 'shared', 'font')

_, GLYPHS = read_font(os.path.join(FONT_DIR, 'defaultFont.font'))


def text_width(size, text):
    """Width as the engine measures it: glyph advances scaled from the 40 px font."""
    lines = str(text).split('\n')
    return max(sum(GLYPHS.get(ord(c), [(0, 0, 0, 0, 0, 0, 0)])[0][6] for c in line) for line in lines) * size / 40


class XmlFiles:
    """loadXMLFile / createXMLFile and friends, for paths like a.b.c(2)#attr."""

    def __init__(self):
        self.files = {}

    def _node(self, root, path, create):
        path, _, attr = path.partition('#')
        parts = path.split('.')
        node = root
        if parts[0] != root.tag:
            return None, attr
        for part in parts[1:]:
            name, _, idx = part.partition('(')
            idx = int(idx[:-1]) if idx else 0
            kids = [k for k in node if k.tag == name]
            while create and len(kids) <= idx:
                kids.append(ET.SubElement(node, name))
            if len(kids) <= idx:
                return None, attr
            node = kids[idx]
        return node, attr

    def load(self, name, path):
        handle = len(self.files) + 1
        self.files[handle] = (path, ET.parse(path).getroot())
        return handle

    def create(self, name, path, root):
        handle = len(self.files) + 1
        self.files[handle] = (path, ET.Element(root))
        return handle

    def get_string(self, handle, path):
        node, attr = self._node(self.files[handle][1], path, False)
        return None if node is None else node.get(attr)

    def set_string(self, handle, path, value):
        node, attr = self._node(self.files[handle][1], path, True)
        node.set(attr, value)

    def save(self, handle):
        path, root = self.files[handle]
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def run(out_png):
    profile = tempfile.mkdtemp(prefix='fs22profile_') + '/'
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    xml = XmlFiles()
    calls = []
    state = {'wrap': 0, 'align': 0}

    def render_text(x, y, size, text):
        calls.append({'x': x, 'size': size, 'text': text, 'wrap': state['wrap'], 'align': state['align']})

    def set_wrap(w):
        state['wrap'] = w

    def set_align(a):
        state['align'] = a

    g.renderText = render_text
    g.getTextWidth = lambda size, text: text_width(size, text)
    g.getTextHeight = lambda size, text: size * (str(text).count('\n') + 1)
    g.setTextWrapWidth = set_wrap
    g.setTextAlignment = set_align
    g.setTextBold = lambda b: None
    g.setTextColor = lambda *a: None
    g.utf8ToUpper = lambda s: s.upper()
    g.fileExists = lambda p: os.path.exists(p)
    g.createFolder = lambda p: os.makedirs(p, exist_ok=True)
    g.getUserProfileAppPath = lambda: profile
    g.loadXMLFile = xml.load
    g.createXMLFile = xml.create
    g.getXMLString = xml.get_string
    g.setXMLString = xml.set_string
    g.saveXMLFile = xml.save
    g.delete = lambda h: None
    g.g_currentModName = 'FS22_ArabicLanguage'
    g.g_currentModDirectory = MOD.replace('\\', '/') + '/'
    g.g_languageShort = 'en'
    lua.execute('''
        RenderText = {ALIGN_LEFT = 0, ALIGN_CENTER = 1, ALIGN_RIGHT = 2}
        Logging = {warning = function(fmt, ...) print("WARNING " .. string.format(fmt, ...)) end}
        listeners = {}
        function addModEventListener(l) table.insert(listeners, l) end
        g_i18n = {texts = {
            ui_colorBlack = "Black", ui_no = "No", unit_literShort = "l",
            configuration_valueDefault = "Default", other_key = "Untranslated",
        }}
        function g_i18n:getText(name) return self.texts[name] or ("Missing " .. name) end
        -- the game runs each mod in its own environment that falls back to the globals,
        -- with g_i18n there a proxy holding the mod's own texts (seen in log.txt)
        function runModFile(path)
            local chunk = assert(loadfile(path))
            setfenv(chunk, MOD_ENV)
            chunk()
        end
        local proxy = setmetatable({texts = {}}, {__index = g_i18n})
        function proxy.setGlobalText() end
        function proxy.hasModText() return false end
        function proxy.getText(self, name) return self.texts[name] or g_i18n:getText(name) end
        MOD_ENV = setmetatable({g_i18n = proxy}, {__index = _G})
        -- in the game, getfenv(0) inside a mod gives the mod environment, not the
        -- game's globals (in-game test of v0.2.0); game scripts keep using _G
        TextElement = {}
        MOD_ENV.getfenv = function(level)
            if level == 0 then return MOD_ENV end
            return getfenv(level)
        end
    ''')
    for name in ('ArabicShaper.lua', 'ArabicLanguage.lua'):
        lua.globals().runModFile(os.path.join(MOD, 'scripts', name))

    checks = []

    def check(label, ok):
        checks.append((label, bool(ok)))

    env = lua.eval('MOD_ENV')
    lis = lua.eval('listeners[1]')
    check('listener registered', lis is not None)
    # what the game and other mods see: the global instance, not this mod's proxy
    check('game getText returns Arabic', lua.eval('g_i18n:getText("ui_colorBlack")') == 'أسود')
    check('game texts table holds Arabic', lua.eval('g_i18n.texts.ui_colorBlack') == 'أسود')
    check('untranslated text kept', lua.eval('g_i18n:getText("other_key")') == 'Untranslated')

    lis.loadMap(lis, 'map')
    src = os.path.join(profile, 'modSettings', 'FS22_ArabicLanguage', 'l10n_source.xml')
    check('source texts exported', os.path.exists(src))
    if os.path.exists(src):
        root = ET.parse(src).getroot()
        exported = {t.get('name'): t.get('text') for t in root.iter('text')}
        check('export holds the original English', exported.get('ui_colorBlack') == 'Black')

    shaper = env.ArabicShaper
    for logical, ordered in [
        ('محاكي الزراعة', None),
        ('لا إله إلا الله', None),
        ('مصطفى', None),
    ]:
        check('shaped like the reference: ' + logical, shaper.toVisual(logical) == preview.visual(logical))
    check('Latin text untouched', shaper.toVisual('Farming Simulator 22') == 'Farming Simulator 22')

    # a label menus resolved to English before the mod loaded, as TextElement draws it
    calls.clear()
    lua.eval('renderText')(0.1, 0.5, 0.02, 'BLACK')
    check('English label swapped for Arabic', calls and calls[-1]['text'] == preview.visual('أسود'))

    lines = [
        'محاكي الزراعة ٢٠٢٢ — Farming Simulator 22',
        'السعر: 150,000 € والسعة 25% (تقريباً)',
        'الوقت 12:30 — اضغط F1 للمساعدة',
    ]
    drawn = []
    for line in lines:
        calls.clear()
        lua.eval('renderText')(0.1, 0.5, 0.02, line)
        drawn.append(calls[-1]['text'])

    # a wrapped paragraph, the way TextElement.draw sets it up
    paragraph = ('اجمع المحاصيل من حقولك ثم بعها في نقاط البيع، واستثمر أرباحك في شراء '
                 'آلات جديدة وتوسيع مزرعتك خطوة بعد خطوة.')
    calls.clear()
    lua.eval('setTextWrapWidth')(0.3)
    lua.eval('renderText')(0.1, 0.5, 0.02, paragraph)
    lua.eval('setTextWrapWidth')(0)
    call = calls[-1]
    wrapped = call['text'].split('\n')
    check('paragraph wrapped into several lines', len(wrapped) > 1)
    check('every wrapped line fits', all(text_width(0.02, l) <= 0.3 + 1e-9 for l in wrapped))
    check('engine wrapping off while drawing', call['wrap'] == 0)
    check('wrapped Arabic aligned right', call['align'] == 2 and abs(call['x'] - 0.4) < 1e-9)
    check('wrap width restored', state['wrap'] == 0)

    lis.draw(lis)
    expected = preview.visual('مود التعريب يعمل — %d نصاً مترجماً' % env.ArabicLanguage.count)
    check('confirmation line drawn, centred', calls[-1]['text'] == expected and calls[-1]['align'] == 1)

    for label, ok in checks:
        print('PASS' if ok else 'FAIL', label)

    regular, missing = preview.render(FONT_DIR, drawn + [''] + wrapped + ['', calls[-1]['text']], ordered=True)
    regular.save(out_png)
    if missing:
        print('Missing characters:', ' '.join(sorted(missing)))
    return all(ok for _, ok in checks)


if __name__ == '__main__':
    sys.exit(0 if run(sys.argv[1]) else 1)
