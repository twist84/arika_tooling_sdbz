import struct
from pathlib import Path

for name in ['GAME.DAT', 'INFO.DAT']:
    p = Path(r'C:\Dev\arika\source_data') / name
    if p.exists():
        size = p.stat().st_size
        data = p.read_bytes()
        print(f'{name}: {size} bytes ({size/1024/1024:.1f} MB)')
        print(f'  First 16 bytes: {" ".join(f"{b:02X}" for b in data[:16])}')
        if data[:4] == b' ZBE':
            print(f'  Magic: ZBE')
        elif data[:4] == b'INFO':
            print(f'  Magic: INFO')
        else:
            print(f'  Magic: {data[:4]!r}')
        print()
