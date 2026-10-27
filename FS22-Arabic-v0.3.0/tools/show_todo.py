"""Print untranslated texts (from todo.json) whose key starts with one of the given prefixes."""
import json, sys
todo = json.load(open(sys.argv[1], encoding='utf-8'))
prefixes = tuple(sys.argv[2:])
for k in sorted(todo):
    if k.startswith(prefixes):
        print(k + '=' + todo[k].replace('\n', '\n'))
