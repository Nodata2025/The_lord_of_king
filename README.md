# The Lord of King (FC, 일본판) 한글패치

잘레코 「ザ・ロード・オブ・キング」(패미컴, 1989) 한글화 프로젝트.

- 롬 이미지와 롬에서 뽑은 원문·그래픽은 저장소에 넣지 않습니다. 직접 가진 롬으로 도구를 실행하세요.
- 작업 방법론: [create-retro-game-kr-patch](https://github.com/mcpads/create-retro-game-kr-patch)

## 지원 원본

| 항목 | 값 |
|---|---|
| 형식 | iNES (헤더 포함) |
| 크기 | 262,160 바이트 |
| SHA-1 | `b1cad2d3e38ccd7780437d2c83effa254576861b` |

## 패치

패치는 [dist/](dist/)에 버전별로 올립니다(`LordOfKing_KR_v<버전>.ips`). 일본판 원본 롬에 IPS로 적용하세요. 변경 내용은 [CHANGELOG.md](CHANGELOG.md).

## 도구

```sh
# 원문 추출 (build/script_ja.json, git 제외)
python3 tools/extract_script.py 롬경로.nes
# 빌드 (build/lok_ko_dev.nes) 와 IPS 생성
LOK_FONT=Galmuri11-Condensed.ttf python3 tools/build.py 롬경로.nes
# 한 번에: 빌드 + IPS + 검사 + dist 갱신 (버전은 VERSION 파일)
LOK_FONT=Galmuri11-Condensed.ttf tools/release.sh 롬경로.nes
# 패치에 원문 텍스트·가나 타일이 없는지 검사 (실패 시 종료 코드 1)
LOK_FONT=Galmuri11-Condensed.ttf python3 tools/check_patch.py 롬경로.nes dist/LordOfKing_KR_dev.ips
```

## 문서

- [docs/decisions.md](docs/decisions.md) — 확정된 방향과 미결 사항
- [docs/survey.md](docs/survey.md) — 롬 구조 조사 결과

## 글꼴

[Galmuri](https://github.com/quiple/galmuri) 11 Condensed (SIL Open Font License 1.1). 폰트 파일은 저장소에 포함하지 않습니다.
