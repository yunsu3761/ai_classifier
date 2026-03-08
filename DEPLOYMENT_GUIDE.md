# TaxoAdapt 멀티유저 배포 가이드

## 아키텍처 개요

```
공용 PC (서버)
├── web_interface.py          ← Streamlit 앱
├── user_data/                ← 사용자별 데이터 (자동 생성)
│   ├── users.json            ← 사용자 등록 정보
│   ├── P12345/               ← 사번별 폴더
│   │   ├── datasets/         ← 사용자 전용 데이터셋
│   │   ├── configs/          ← 사용자 전용 YAML 설정
│   │   ├── save_output/      ← 사용자 전용 결과물
│   │   └── history/          ← 실행 이력
│   └── P67890/
│       └── ...
├── .streamlit/config.toml    ← Streamlit 서버 설정
└── ...
```

## 1. 공용 PC 설정 (1회)

### 1-1. Python 설치
- Python 3.10 이상 설치 (https://python.org)
- 설치 시 **"Add Python to PATH"** 반드시 체크

### 1-2. 프로젝트 폴더 이동
```powershell
cd "c:\Users\POSCORTECH\Desktop\프로젝트 관리\9. IPAS_TechTree\1. Taxoadapt 테스트\0.기본세팅\1.Web구동\1.기본코드"
```

### 1-3. 가상환경 생성 및 활성화
```powershell
python -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force
.\.venv\Scripts\Activate.ps1
```

### 1-4. 의존성 설치
```powershell
pip install -r requirements.txt
```

### 1-5. 환경변수 설정
프로젝트 폴더에 `.env` 파일 생성:
```
OPENAI_API_KEY=sk-your-api-key-here
```

## 2. 서버 실행

### 기본 실행 (개발/테스트)
```powershell
streamlit run web_interface.py
```

### 네트워크 공유 실행 (다른 PC에서 접속 가능)
```powershell
streamlit run web_interface.py --server.address 0.0.0.0 --server.port 4499
```

### 백그라운드 실행 (PC 켜놓기)
```powershell
# PowerShell에서 백그라운드 실행
Start-Process -NoNewWindow powershell -ArgumentList "-Command", "cd '$PWD'; .\.venv\Scripts\Activate.ps1; streamlit run web_interface.py --server.address 0.0.0.0 --server.port 4499"
```

## 3. 사용자 접속 방법

### 3-1. 공용 PC IP 확인
공용 PC IP: `192.168.0.231`

### 3-2. 접속 URL 공유
다른 사용자에게 아래 URL을 공유:
```
http://192.168.0.231:4499
```

### 3-3. 로그인
- 사번 (예: P12345)과 이름을 입력하면 자동으로 계정 생성
- 이후부터는 사번만 입력하면 로그인

## 4. 멀티유저 동작 방식

| 항목 | 설명 |
|------|------|
| **세션 격리** | Streamlit 세션은 브라우저 탭별로 독립 |
| **데이터 격리** | 각 사용자의 datasets, configs, results가 `user_data/{사번}/`에 분리 저장 |
| **동시 실행** | prompts.py 수정/실행 구간에 락(Lock) 적용 → 동시 실행 시 순차 처리 |
| **실행 이력** | 각 사용자별 실행 이력 자동 기록 |
| **권장 동시 사용자** | ~10명 (API 비용 및 서버 리소스 감안) |

## 5. 방화벽 설정 (필요 시)

Windows 방화벽에서 포트 4499를 허용:
```powershell
New-NetFirewallRule -DisplayName "TaxoAdapt Streamlit" -Direction Inbound -Protocol TCP -LocalPort 4499 -Action Allow
```

## 6. 자동 시작 설정 (선택)

PC 부팅 시 자동으로 Streamlit 서버를 시작하려면:

### 배치 파일 생성
`start_taxoadapt.bat` 파일을 프로젝트 폴더에 생성:
```batch
@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
streamlit run web_interface.py --server.address 0.0.0.0 --server.port 4499
```

### 작업 스케줄러에 등록
1. `Win + R` → `taskschd.msc`
2. "기본 작업 만들기" → 트리거: "컴퓨터 시작 시"
3. 동작: `start_taxoadapt.bat` 실행

## 7. 문제 해결

| 증상 | 해결 |
|------|------|
| 다른 PC에서 접속 안됨 | 방화벽 규칙 확인, `--server.address 0.0.0.0` 확인 |
| "사번을 입력해주세요" | 사번 필드를 비워두고 로그인 시도 → 사번 입력 |
| 동시 실행 시 대기 | 정상 동작 - 락으로 순차 처리됨 (대기 메시지 표시) |
| 메모리 부족 | 동시 사용자 수 제한 또는 서버 PC 메모리 증설 |
| 포트 4499 충돌 | `Get-NetTCPConnection -LocalPort 4499` 확인 후 PID 종료 |
