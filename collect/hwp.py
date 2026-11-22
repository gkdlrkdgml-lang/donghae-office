"""한글(HWP) 파일 → 마크다운(표 포함). 류주임 kordoc(chrisryugj/kordoc, MIT)을 npx로 실행."""
import os
import subprocess
import tempfile


def hwp_text(data, name='a.hwp'):
    d = tempfile.mkdtemp()
    f = os.path.join(d, name)
    open(f, 'wb').write(data)
    r = subprocess.run(['npx', '-y', '--package', 'kordoc', '--package', 'pdfjs-dist', 'kordoc', f, '-o', f + '.md'],
                       capture_output=True, text=True, timeout=180)
    if not os.path.exists(f + '.md'):
        raise RuntimeError('kordoc 실패: %s' % (r.stderr or r.stdout)[-300:])
    return open(f + '.md', encoding='utf-8').read()
