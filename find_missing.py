import os
import re

regex = re.compile(r'\{\{\s*([^|}]*(?:monto|kg|total|saldo|precio|cantidad|subtotal|piezas|deuda)[^|}]*)\s*\}\}', re.IGNORECASE)

missing = []

for root, dirs, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    for match in regex.finditer(line):
                        var_name = match.group(1).strip()
                        if ' ' in var_name and not var_name.startswith('('):
                            continue # probably python code, though jinja could be
                        if var_name.endswith('.strftime') or var_name.endswith('()'):
                            continue
                        missing.append(f"{filepath}:{i+1}: {match.group(0)}")

with open('missing_filters.txt', 'w', encoding='utf-8') as f:
    for m in missing:
        f.write(m + '\n')
