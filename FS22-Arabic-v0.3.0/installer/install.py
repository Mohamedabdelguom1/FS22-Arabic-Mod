"""
FS22 Arabic - one-click installer (run by Install.bat / Uninstall.bat).

Adds the Arabic letters to the game font with add_arabic_glyphs.py (which keeps
the original) and copies the mod into the mods folder. --uninstall puts the
original font back and removes the mod. --game skips the folder search.
"""

import argparse
import ctypes
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'add_arabic_glyphs.py')
MOD = os.path.join(HERE, 'FS22_ArabicLanguage.zip')
GUESSES = [
    r'C:\Program Files (x86)\Steam\steamapps\common\Farming Simulator 22',
    r'C:\Program Files (x86)\Farming Simulator 2022',
    r'C:\Program Files\Farming Simulator 2022',
    r'C:\Program Files\Epic Games\FarmingSimulator22',
]


def say(text):
    print('  ' + text, flush=True)


def fail(text):
    say('ERROR: ' + text)
    sys.exit(1)


def is_game(path):
    return bool(path) and os.path.isfile(os.path.join(path, 'shared', 'font', 'defaultFont.font'))


def find_game():
    for g in GUESSES:
        if is_game(g):
            return g
    from tkinter import Tk, filedialog, messagebox
    root = Tk()
    root.withdraw()
    while True:
        path = filedialog.askdirectory(title='Choose the Farming Simulator 22 game folder')
        if not path:
            fail('No game folder chosen.')
        if is_game(path):
            return os.path.normpath(path)
        messagebox.showwarning('FS22 Arabic', 'This is not the game folder (no shared\\font inside). Try again.')


def mods_folder():
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)   # 5 = Documents, follows OneDrive
    return os.path.join(buf.value, 'My Games', 'FarmingSimulator2022', 'mods')


def run_tool(game, *extra):
    if subprocess.call([sys.executable, TOOL, '--game', game, *extra]):
        fail('Could not change the game font. Close the game, or right-click Install.bat > Run as administrator.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game')
    ap.add_argument('--uninstall', action='store_true')
    args = ap.parse_args()

    say('==== FS22 Arabic ====\n')
    game = args.game or find_game()
    if not is_game(game):
        fail('Not the game folder: ' + game)
    say('Game: ' + game)
    target = os.path.join(mods_folder(), 'FS22_ArabicLanguage.zip')

    if args.uninstall:
        run_tool(game, '--restore')
        try:
            if os.path.exists(target):
                os.remove(target)
        except OSError:
            os.startfile(os.path.dirname(target))
            say('\nThe original font is back. Delete FS22_ArabicLanguage.zip from the open "mods" folder.')
            return
        say('\nDone: the original font is back and the mod is removed.')
        return

    say('[1/3] Preparing Python...')
    try:
        import numpy, PIL   # noqa: F401
    except ImportError:
        if subprocess.call([sys.executable, '-m', 'pip', 'install', '--quiet',
                            '--disable-pip-version-check', 'numpy', 'pillow']):
            fail('Could not install numpy and pillow (internet needed).')

    say('[2/3] Adding Arabic letters to the game font (about a minute)...')
    run_tool(game)

    say('[3/3] Copying the mod...')
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(MOD, target)
    except OSError:
        # e.g. Windows "Controlled folder access" keeps Python out of Documents
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.startfile(os.path.dirname(target))
        os.startfile(HERE)
        say('\nThe font is done, but Windows did not let this program copy the mod.')
        say('Two folders are now open: drag FS22_ArabicLanguage.zip into the "mods" folder.')
        return
    say('\nDone! Start the game, open a savegame and tick "Arabic Language".')


if __name__ == '__main__':
    main()
