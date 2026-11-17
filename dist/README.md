# 패치 파일

| 파일 | 적용 후 롬 SHA-1 | IPS SHA-1 |
|---|---|---|
| `LordOfKing_KR_v0.11.2-dev.ips` | `a8912a4566f7bda5db7a30643b08a3ef25c839f5` | `4be1333eefa80ca61bea2e2d508037708e68c6f7` |

- 적용 대상: 일본판 iNES 롬 「The Lord of King」, SHA-1 `b1cad2d3e38ccd7780437d2c83effa254576861b` (262,160바이트)
- 적용하면 CHR-ROM이 256KB로 늘어납니다(393,232바이트).
- 번역 상태: needs_review 81
- `-dev` 버전은 검수 전 개발용입니다. 변경 내용은 [CHANGELOG.md](../CHANGELOG.md).
- 패치에는 원본 롬의 텍스트나 그래픽이 들어 있지 않습니다(`tools/check_patch.py`로 검사).
- 한글 글꼴: Galmuri11 Condensed © quiple, SIL Open Font License 1.1.
- Mesen에서 입력이 안 되면 1P 컨트롤러가 연결돼 있는지 확인하세요(수정된 롬은 게임 DB 자동 설정이 적용되지 않음).
