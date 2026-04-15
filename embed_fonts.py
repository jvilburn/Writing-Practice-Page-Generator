"""Generate a standalone HTML with all fonts embedded as base64 data URIs."""
import base64

def b64_file(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove Google Fonts links
content = content.replace(
    '  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '  <link href="https://fonts.googleapis.com/css2?family=Andika&display=swap" rel="stylesheet">\n',
    ''
)

# Build embedded font-face declarations
fonts = {
    'Andika': ('Andika-Regular.ttf', 'truetype'),
    'FRBCursive': ('fonts/FRBAmericanCursive-400-Regular.woff2', 'woff2'),
    'FRBCursiveDotted': ('fonts/FRBAmericanCursive-400-Dotted.woff2', 'woff2'),
    'FRBCursiveArrow': ('fonts/FRBAmericanCursive-400-ArrowPath.woff2', 'woff2'),
    'FRBCursiveGuideDotted': ('fonts/FRBAmericanCursive-400-GuidelinesArrowsDottedRegular.woff2', 'woff2'),
}

new_faces = '    /* Font Faces - Embedded */\n'
for name, (path, fmt) in fonts.items():
    mime = 'font/ttf' if fmt == 'truetype' else 'font/woff2'
    data = b64_file(path)
    new_faces += f'''    @font-face {{
      font-family: '{name}';
      src: url(data:{mime};base64,{data}) format('{fmt}');
      font-weight: normal;
      font-style: normal;{'''
      font-display: swap;''' if name == 'Andika' else ''}
    }}
'''

old_block = """    /* Font Faces */
    @font-face {
      font-family: 'FRBCursive';
      src: url('fonts/FRBAmericanCursive-400-Regular.woff2') format('woff2');
      font-weight: normal;
      font-style: normal;
    }
    @font-face {
      font-family: 'FRBCursiveDotted';
      src: url('fonts/FRBAmericanCursive-400-Dotted.woff2') format('woff2');
      font-weight: normal;
      font-style: normal;
    }
    @font-face {
      font-family: 'FRBCursiveArrow';
      src: url('fonts/FRBAmericanCursive-400-ArrowPath.woff2') format('woff2');
      font-weight: normal;
      font-style: normal;
    }
    @font-face {
      font-family: 'FRBCursiveGuideDotted';
      src: url('fonts/FRBAmericanCursive-400-GuidelinesArrowsDottedRegular.woff2') format('woff2');
      font-weight: normal;
      font-style: normal;
    }"""

content = content.replace(old_block, new_faces)

with open('index-standalone.html', 'w', encoding='utf-8') as f:
    f.write(content)

import os
size = os.path.getsize('index-standalone.html')
print(f'Created index-standalone.html ({size/1024/1024:.1f} MB)')
