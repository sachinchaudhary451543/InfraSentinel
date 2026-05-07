#!/usr/bin/env python3
"""Fix current_user references in api.py by using typed helper"""

# Read the file with UTF-8 encoding
with open('web/routes/api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all instances of if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if 'if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:' in line:
        # Get the indentation
        indent = len(line) - len(line.lstrip())
        indent_str = ' ' * indent
        # Insert the typed assignment before the if
        new_lines.append(indent_str + 'cu = _get_current_user()')
        # Replace current_user references with cu
        new_line = line.replace('current_user', 'cu')
        new_lines.append(new_line)
    else:
        new_lines.append(line)
    i += 1

# Write back with UTF-8 encoding
with open('web/routes/api.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print('Successfully replaced all if statements')
