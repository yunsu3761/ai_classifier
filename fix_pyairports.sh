#!/bin/bash
# pyairports 수동 설치 스크립트
# 
# 배경: PyPI의 pyairports 패키지가 손상됨 (메타데이터만 있고 Python 파일 없음)
# 목적: vLLM의 outlines 라이브러리가 요구하는 pyairports를 직접 생성하여 설치
# 사용: ./fix_pyairports.sh

set -e  # 에러 발생 시 중단

echo "=========================================="
echo "pyairports 수동 설치 시작"
echo "=========================================="
echo ""
echo "이유: PyPI의 pyairports 패키지 손상"
echo "해결: 최소 기능 구현 패키지를 직접 생성"
echo ""

# 1. 작업 디렉토리 생성
cd /root/taxo
rm -rf pyairports_fix  # 기존 디렉토리 삭제
mkdir -p pyairports_fix/pyairports
echo "✓ 디렉토리 생성 완료"

# 2. __init__.py 생성
cat > pyairports_fix/pyairports/__init__.py << 'EOF'
"""Minimal pyairports implementation for vLLM compatibility."""
__version__ = "0.0.2"

from .airports import AIRPORT_LIST

__all__ = ['AIRPORT_LIST']
EOF
echo "✓ __init__.py 생성 완료"

# 3. airports.py 생성 (outlines가 요구하는 tuple 형식)
cat > pyairports_fix/pyairports/airports.py << 'EOF'
"""Airport data for outlines compatibility."""

# Format expected by outlines: tuple with index 3 being IATA code
# (name, city, country, iata_code, icao_code, lat, lon, alt, timezone, dst, tz_name)
AIRPORT_LIST = [
    ("Incheon International Airport", "Seoul", "South Korea", "ICN", "RKSI", "37.469", "126.451", "23", "9", "U", "Asia/Seoul"),
    ("Gimpo International Airport", "Seoul", "South Korea", "GMP", "RKSS", "37.558", "126.791", "59", "9", "U", "Asia/Seoul"),
    ("John F. Kennedy International Airport", "New York", "United States", "JFK", "KJFK", "40.639", "-73.779", "13", "-5", "A", "America/New_York"),
    ("Los Angeles International Airport", "Los Angeles", "United States", "LAX", "KLAX", "33.942", "-118.408", "38", "-8", "A", "America/Los_Angeles"),
    ("London Heathrow Airport", "London", "United Kingdom", "LHR", "EGLL", "51.471", "-0.461", "83", "0", "E", "Europe/London"),
    ("Tokyo Narita International Airport", "Tokyo", "Japan", "NRT", "RJAA", "35.765", "140.386", "43", "9", "U", "Asia/Tokyo"),
    ("Singapore Changi Airport", "Singapore", "Singapore", "SIN", "WSSS", "1.350", "103.994", "22", "8", "U", "Asia/Singapore"),
]
EOF
echo "✓ airports.py 생성 완료"

# 4. setup.py 생성
cat > pyairports_fix/setup.py << 'EOF'
from setuptools import setup, find_packages

setup(
    name="pyairports",
    version="0.0.2",
    packages=find_packages(),
    python_requires=">=3.7",
    description="Minimal airport data for vLLM/outlines compatibility",
    author="Custom Fix",
)
EOF
echo "✓ setup.py 생성 완료"

# 5. 가상환경에서 설치
cd pyairports_fix
echo ""
echo "패키지 설치 중..."
uv pip install -e . --force-reinstall --no-deps
cd ..

# 6. 검증
echo ""
echo "=========================================="
echo "설치 검증 중..."
echo "=========================================="

python << 'PYEOF'
try:
    from pyairports.airports import AIRPORT_LIST
    print(f"✓ pyairports 모듈 import 성공")
    print(f"✓ 공항 데이터 개수: {len(AIRPORT_LIST)}")
    print(f"✓ 데이터 형식 확인: {type(AIRPORT_LIST[0])}")
    print(f"✓ IATA 코드 접근 테스트: {AIRPORT_LIST[0][3]}")
    
    # outlines가 사용하는 방식대로 검증
    airport_codes = {(airport[3], airport[3]) for airport in AIRPORT_LIST if airport[3] != ""}
    print(f"✓ outlines 형식 호환성 확인: {len(airport_codes)}개 코드")
    
    print("\n========================================")
    print("✅ pyairports 설치 및 검증 완료!")
    print("========================================")
    print("\n이제 vLLM을 사용할 수 있습니다:")
    print("  VLLM_WORKER_MULTIPROC_METHOD=spawn python taxoadapt/main2.py --llm vllm")
    
except Exception as e:
    print(f"\n❌ 검증 실패: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
PYEOF

echo ""
echo "설치 완료. pyairports_fix/ 디렉토리는 유지됩니다."
    print("========================================")
except Exception as e:
    print(f"\n❌ 검증 실패: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
PYEOF
