"""Inline the processed dataset into the viewer: python3 -I tools/build.py src/index.html data/campus.json dist/uoft-twin.html"""
import sys

src, data, out = sys.argv[1:4]
html = open(src, encoding='utf-8').read()
payload = open(data, encoding='utf-8').read().replace('</', '<\\/')
assert '__TWIN_DATA__' in html
open(out, 'w', encoding='utf-8').write(html.replace('__TWIN_DATA__', payload))
print(out, round(len(html) / 1024), 'KB template +', round(len(payload) / 1024), 'KB data')

# a standalone copy with its own document skeleton, for opening locally
standalone = out.replace('uoft-twin.html', 'index.html')
if standalone != out:
    skel = ('<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
            'body{margin:0}[hidden]{display:none!important}</style>\n</head>\n<body>\n')
    open(standalone, 'w', encoding='utf-8').write(skel + open(out, encoding='utf-8').read() + '\n</body>\n</html>\n')
    print(standalone)
