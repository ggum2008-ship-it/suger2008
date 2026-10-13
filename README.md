# 오늘의 이슈 에이전트

매일 아침 뉴스를 찾아 유튜브 쇼츠 영상을 만들고, 일요일에는 주간 정리 영상을 만들어
**내 Gmail로 영상 파일과 제목·설명을 보내 주는 로봇**입니다.

| 언제 | 메일 제목 | 첨부 파일 |
| --- | --- | --- |
| 매일 오전 6시 30분쯤 | [오늘의 이슈] 날짜 + 추천 제목 | shorts.mp4, preview.png, youtube_upload.txt |
| 일요일 오전 8시 30분쯤 | [주간 이슈] 주차 + 추천 제목 | weekly.mp4, thumbnail.png, youtube_upload.txt |

## 처음 한 번만 하는 설정 (약 30분)

### 1. GitHub 가입하고 저장소 만들기
1. https://github.com 에서 무료로 가입해요.
2. 오른쪽 위 `+` → `New repository`를 눌러요.
3. 이름에 `issue-agent`를 쓰고, **Private(비공개)**를 고른 뒤 `Create repository`를 눌러요.

### 2. 파일 올리기
1. 받은 zip 파일의 압축을 풀어요.
2. 저장소 화면에서 `uploading an existing file`을 눌러요.
3. 압축 푼 폴더 안의 **보이는 파일과 폴더를 모두** 끌어다 놓고 `Commit changes`를 눌러요.
   (agent.py, issue_maker.py, settings.json, history.json, requirements.txt, README.md, sample 폴더, 자동실행_설정 폴더)
4. 자동 실행 파일 2개는 따로 만들어요. (`.github` 폴더는 컴퓨터에서 숨김 폴더라 끌어 놓기가 잘 안 돼요.)
   - `Add file` → `Create new file`
   - 파일 이름 칸에 `.github/workflows/daily.yml` 을 그대로 써요.
   - `자동실행_설정/daily.yml` 파일을 메모장으로 열어 내용 전체를 복사해 붙여넣고 `Commit changes`.
   - 같은 방법으로 `.github/workflows/weekly.yml` 도 만들어요.

### 3. 비밀번호 3개 준비하기
| 이름 | 무엇인가요 | 어디서 받나요 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Claude를 부르는 열쇠 | https://console.anthropic.com/settings/keys → `Create Key` (먼저 Billing에서 크레딧 충전 필요) |
| `GMAIL_ADDRESS` | 내 Gmail 주소 | 예: myname@gmail.com |
| `GMAIL_APP_PASSWORD` | 메일을 보내기 위한 16자리 비밀번호 | Google 계정 2단계 인증을 켠 뒤 https://myaccount.google.com/apppasswords 에서 만들기 (띄어쓰기 없이 붙여 쓰기) |

### 4. 비밀번호를 GitHub에 넣기
1. 저장소 위쪽 `Settings` → 왼쪽 `Secrets and variables` → `Actions`
2. `New repository secret`을 눌러 위 표의 **이름**과 **값**을 하나씩, 모두 3개 넣어요.

### 5. 시험해 보기
1. 저장소 위쪽 `Actions` 탭을 눌러요. (처음이면 초록 버튼으로 켜 줘요.)
2. 왼쪽에서 `오늘의 이슈 쇼츠 (매일)`을 누르고, 오른쪽 `Run workflow`를 눌러요.
3. **시험 모드에 체크된 채로** 실행해요. 3~5분 뒤 Gmail에 예시 영상 메일이 오면 성공이에요. (시험 모드는 Claude 비용이 들지 않아요.)
4. 이번엔 시험 모드 체크를 **끄고** 한 번 더 실행해요. 진짜 오늘의 뉴스로 만든 영상이 메일로 와요.

이제 끝! 다음 날부터 매일 자동으로 메일이 와요.

## 설정 바꾸기
저장소에서 `settings.json`을 열고 연필(✏️) 아이콘을 눌러 고친 뒤 `Commit changes`를 눌러요.

| 항목 | 고를 수 있는 값 |
| --- | --- |
| `쇼츠_재생속도`, `주간영상_재생속도` | `느리게`, `보통`, `빠르게` |
| `요일별_분야` | `사회·시사`, `교육`, `AI·IT`, `생활·경제` |
| `추가로_받을_메일` | 함께 받을 메일 주소 예: `["friend@gmail.com"]` |

**잠깐 멈추기:** `Actions` 탭 → 워크플로 선택 → 오른쪽 `…` → `Disable workflow`

## 비용
- GitHub: 비공개 저장소도 매달 2,000분까지 무료예요. 이 로봇은 한 달에 약 150~250분을 써요.
- Claude API: 뉴스 검색 1번에 약 14원(1,000번에 10달러) + 글 쓰는 비용이 들어요. 하루 한 번 쇼츠와 주 1회 주간 영상을 만들면 **한 달 약 1만~2만 원**으로 예상해요. 실제 사용량은 console.anthropic.com 에서 볼 수 있고, 거기서 한 달 최대 사용 금액을 정해 둘 수 있어요.

## 문제가 생기면
- 실패하면 **[오늘의 이슈] 만들기 실패** 메일이 와요. 그 내용을 그대로 Claude에게 보여 주면 고칠 방법을 알려 줘요.
- 메일이 아예 안 오면 `Actions` 탭에서 빨간 ✕가 있는 실행을 눌러 내용을 Claude에게 보여 주세요.
- GitHub 자동 실행은 사람이 많이 쓰는 시간에 몇 분~수십 분 늦을 수 있어요.
