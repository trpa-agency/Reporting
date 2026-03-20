import json, sys
with open(r'c:\Users\mbindl\Documents\GitHub\Reporting\update_existing_residential.ipynb', encoding='utf-8') as f:
    nb = json.load(f)
for i, c in enumerate(nb['cells']):
    src = ''.join(c['source'])
    first = src[:90].replace('\n', ' ')
    line = f"[{i:02d}] {c['cell_type']:8} id={c['id']:12}  {first}\n"
    sys.stdout.buffer.write(line.encode('utf-8'))
