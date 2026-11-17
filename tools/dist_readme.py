"""Write dist/README.md for the current patch (called by tools/release.sh)."""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name, report = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))
ips = open(os.path.join(ROOT, "dist", name), "rb").read()
script = json.load(open(os.path.join(ROOT, "data", "script_ko.json"), encoding="utf-8"))
states = {}
for e in list(script["entries"].values()) + list(script.get("menu", {}).values()):
    states[e["state"]] = states.get(e["state"], 0) + 1
open(os.path.join(ROOT, "dist", "README.md"), "w", encoding="utf-8").write(f"""# 패치 파일

| 파일 | 적용 후 롬 SHA-1 | IPS SHA-1 |
|---|---|---|
| `{name}` | `{report['sha1']}` | `{hashlib.sha1(ips).hexdigest()}` |

- 적용 대상: 일본판 iNES 롬 「The Lord of King」, SHA-1 `b1cad2d3e38ccd7780437d2c83effa254576861b` (262,160바이트)
- 적용하면 CHR-ROM이 256KB로 늘어납니다(393,232바이트).
- 번역 상태: {', '.join(f'{k} {v}' for k, v in sorted(states.items()))}
- `-dev` 버전은 검수 전 개발용입니다. 변경 내용은 [CHANGELOG.md](../CHANGELOG.md).
- 패치에는 원본 롬의 텍스트나 그래픽이 들어 있지 않습니다(`tools/check_patch.py`로 검사).
- 한글 글꼴: Galmuri11 Condensed © quiple, SIL Open Font License 1.1.
- Mesen에서 입력이 안 되면 1P 컨트롤러가 연결돼 있는지 확인하세요(수정된 롬은 게임 DB 자동 설정이 적용되지 않음).
""")
