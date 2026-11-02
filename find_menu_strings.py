import re
data = open(r'C:\Dev\arika\source_data\SLUS_214.42', 'rb').read()
for m in re.finditer(rb'[A-Za-z0-9_/.\-]*(?:menu|main_menu|option|result|title|vs|vs_select|character_select|network|load|save)', data, re.IGNORECASE):
    start = max(0, m.start() - 8)
    end = min(len(data), m.end() + 8)
    ctx = data[start:end]
    print(f'0x{m.start():06X}: {ctx}')