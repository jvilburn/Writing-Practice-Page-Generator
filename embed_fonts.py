"""Generate a standalone HTML with all fonts embedded as base64 data URIs."""
import base64
import os

def b64_file(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Build embedded font-face declarations for all fonts
fonts = {
    'Schoolroom': ('Schoolroom.ttf', 'truetype'),
    'FRBCursive': ('fonts/FRBAmericanCursive-400-Regular.woff2', 'woff2'),
    'FRBCursiveDotted': ('fonts/FRBAmericanCursive-400-Dotted.woff2', 'woff2'),
    'FRBCursiveArrow': ('fonts/FRBAmericanCursive-400-ArrowPath.woff2', 'woff2'),
    'FRBCursiveGuideDotted': ('fonts/FRBAmericanCursive-400-GuidelinesArrowsDottedRegular.woff2', 'woff2'),
}

# Replace each font-face that references an external file with an embedded version
for name, (path, fmt) in fonts.items():
    mime = 'font/ttf' if fmt == 'truetype' else 'font/woff2'
    data = b64_file(path)
    # Find and replace the url() reference for this font
    content = content.replace(
        f"url('{path}') format('{fmt}')",
        f"url(data:{mime};base64,{data}) format('{fmt}')"
    )
    # Also handle without quotes around path
    content = content.replace(
        f"url({path}) format('{fmt}')",
        f"url(data:{mime};base64,{data}) format('{fmt}')"
    )
    # Handle truetype format spelling
    content = content.replace(
        f"url('{path}') format('truetype')",
        f"url(data:{mime};base64,{data}) format('truetype')"
    )

with open('index-standalone.html', 'w', encoding='utf-8') as f:
    f.write(content)

size = os.path.getsize('index-standalone.html')
print(f'Created index-standalone.html ({size/1024/1024:.1f} MB)')
