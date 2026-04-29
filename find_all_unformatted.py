import re

with open('variables.txt', 'r', encoding='utf-16le') as f:
    lines = f.readlines()

for line in lines:
    line = line.strip()
    if not line:
        continue
    # parse "templates\file.html:  {{ var }}"
    if ':' in line:
        parts = line.split(':', 1)
        file_part = parts[0]
        match_part = parts[1].strip()
        
        # filter out things that are formatted
        if '|number' in match_part or '|currency' in match_part or '|integer' in match_part or '|format' in match_part:
            continue
            
        # exclude common non-numbers
        if ' url_for(' in match_part or ' csrf_token(' in match_part:
            continue
            
        if ' id ' in match_part or '.id' in match_part:
            continue
            
        if 'nombre' in match_part or 'fecha' in match_part or 'observaciones' in match_part:
            continue
            
        print(line)
