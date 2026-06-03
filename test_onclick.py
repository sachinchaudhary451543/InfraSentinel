#!/usr/bin/env python3
"""Test the onclick code generation"""

# Test the onclick code generation
full = '/api/screenshot/2'
title = 'screenshot_1_test-agent_20260601_015640.jpg'
meta = '2026-06-01 07:56:40 • —'

# Simulate the template code
onClickCode = f"openLb('{full.replace(chr(39), chr(92)+chr(39))}','{title.replace(chr(39), chr(92)+chr(39))}','{meta.replace(chr(39), chr(92)+chr(39))}')".replace('\n', '\\n')

print('Generated onclick code:')
print(repr(onClickCode))
print()
print('HTML attribute:')
print(f'onclick="{onClickCode}"')
print()

# Test with different paths
test_cases = [
    ('Local path', '/api/screenshot/2'),
    ('SharePoint URL', 'https://contoso.sharepoint.com/sites/project/Shared%20Documents/screenshots/image.jpg'),
    ('Simple filename', 'image.jpg'),
]

print('Test cases:')
for desc, url in test_cases:
    onClickCode = f"openLb('{url.replace(chr(39), chr(92)+chr(39))}','title','meta')"
    print(f"\n{desc}:")
    print(f"  URL: {url}")
    print(f"  Code: {onClickCode}")
