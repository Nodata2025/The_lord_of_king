# 패치 파일

| 파일 | 적용 후 롬 SHA-1 | IPS SHA-1 |
|---|---|---|
| `LordOfKing_KR_v0.12.6-dev.ips` | `7dcec8ee0df2f7808b7311bf5e40dba025cd2f09` | `7828206b9c97fec2c0ca9c398680f72a63509d99` |

- 적용 대상: 일본판 iNES 롬 「The Lord of King」, SHA-1 `b1cad2d3e38ccd7780437d2c83effa254576861b` (262,160바이트)
- 적용하면 CHR-ROM이 256KB로 늘어납니다(393,232바이트).
- 번역 상태: needs_review 81
- `-dev` 버전은 검수 전 개발용입니다. 변경 내용은 [CHANGELOG.md](../CHANGELOG.md).
- 패치에는 원본 롬의 텍스트나 그래픽이 들어 있지 않습니다(`tools/check_patch.py`로 검사).
- 한글 글꼴: Galmuri11 Condensed © quiple, SIL Open Font License 1.1.
- Mesen에서 입력이 안 되면 1P 컨트롤러가 연결돼 있는지 확인하세요(수정된 롬은 게임 DB 자동 설정이 적용되지 않음).
