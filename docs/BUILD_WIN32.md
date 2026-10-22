# Mu Editor Windows 32-bit (Win7 / Win10) 빌드 및 검증 가이드

이 문서는 단일 코드베이스(`mu64`)에서 **Windows 7 / Windows 10 32-bit (x86)** 호환 인스톨러(MSI)를 빌드하고 검증하는 방법을 정리한 매뉴얼입니다.

---

## 1. 아키텍처 및 호환 레이어 개요

1. **PyQt5 / PyQt6 호환 레이어 (`mu/qt.py`)**
   - 64-bit Windows: `PyQt6` 로드
   - 32-bit Windows: `PyQt5` 자동 폴백 (Windows 7 지원)
   - 소스 코드 전반에서 `from mu.qt.QtWidgets import ...` 형태로 단일 네임스페이스 사용

2. **조건부 의존성 분기 (`setup.py`)**
   - `struct.calcsize("P") * 8 == 32` 조건으로 32비트 환경 감지
   - 32-bit: `PyQt5==5.15.9`, `PyQt5-Qt5==5.15.2`, `QScintilla==2.14.1`, `PyQtChart==5.15.6` 자동 설치
   - 64-bit: `PyQt6==6.6.0` 계열 패키지 설치

3. **패키징 런타임 (`make.py`)**
   - `bitness=32` 시 **CPython 3.7.9 32-bit Standalone** 런타임을 다운로드하여 패키징
   - Python 3.7은 Windows 7 SP1을 공식 지원하는 안정적인 버전

4. **가상환경 패키지 설치 안전장치 (`mu/virtual_environment.py`)**
   - 32-bit 환경 및 백신 감시 상황 대비 `uv` 실패 시 **표준 `pip` 자동 폴백(Fallback)** 구현

---

## 2. 사전 환경 요구사항

* **32-bit Python 환경 (빌드 러너용)**
  * 경로: `C:\Users\JJ\miniconda3\envs\mu32\python.exe`
  * Python 버전: 3.7.x (32-bit Intel)
* **WiX Toolset**: pup 패키징 시 MSI 생성을 위해 필요 (시스템에 이미 설치되어 있음)
* **Git**: 저장소 관리용

---

## 3. 사전 검증: 32-bit Win7용 Wheels 정상 다운로드 확인

실제 빌드 전, `mode_packages`에 정의된 휠들이 Python 3.7 Win32 환경용 바이너리로 정상 수급되는지 검증합니다.

```powershell
# 현재 디렉터리: c:\dev\mu\mu64
# conda 환경의 OpenSSL DLL(Library\bin)이 PATH에 잡히도록 실행
$mu32 = "C:\Users\JJ\miniconda3\envs\mu32"
$env:PATH = "$mu32;$mu32\Library\bin;$mu32\Scripts;$env:PATH"
& "$mu32\python.exe" -m mu.wheels --package
```

* **검증 결과 (성공)**:
  - 32-bit Windows(`is_32bit and sys.platform == "win32"`) 환경에서 64비트 전용 `mediapipe`가 자동 제외되고 `neopia<=0.3.6`이 선택되어 **총 50개의 Win7 32-bit 바이너리 휠이 에러 없이 100% 정상 수급됨**이 검증되었습니다.
  - 64-bit Windows에서는 기존대로 최신 `neopia>=0.4.0` 및 `mediapipe`가 정상 포함됩니다.

---

## 4. 32-bit Windows 인스톨러(MSI) 빌드 절차

### 1단계: 기존 임시 빌드 폴더 정리
```powershell
# venv-pup 잔여 폴더 삭제
if (Test-Path venv-pup) { Remove-Item -Recurse -Force venv-pup }
```

### 2단계: 32-bit 빌드 명령 실행
```powershell
# 32비트 콘다 환경으로 make.py win32 실행
& "C:\Users\JJ\miniconda3\envs\mu32\python.exe" make.py win32
```

### 3단계: 빌드 산출물 확인
빌드가 완료되면 `dist/` 디렉터리에 32비트 MSI 인스톨러가 생성됩니다.
```powershell
dir dist/*.msi
```
* 필요 시 파일명 구분: `Mu Editor Custom 1.3.4 (32 bit).msi`로 이름 변경.

---

## 5. 트러블슈팅

1. **`Pillow` 빌드 에러 (zlib 누락 등)**
   - 빌드 러너로 반드시 Python 3.7 (32-bit) 전용 환경(`mu32`)을 사용해야 합니다. (3.11 등 최신 버전으로 실행 시 구형 C-확장 컴파일 오류 발생)
2. **`uv.exe` 미지원 경고**
   - 32-bit Windows에서는 64-bit용 `uv.exe`가 동작하지 않으므로, 앱 실행 시 자동으로 `pip` 폴백으로 전환되어 패키지가 안전하게 설치됩니다.
3. **WiX 관련 에러**
   - `build/pup` 임시 디렉터리 삭제 후 재시도.
