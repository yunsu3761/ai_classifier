"""
YAML 차원 인식 문제 디버깅 스크립트
web_interface.py의 YAML 로딩과 차원 처리를 테스트합니다.
"""
import yaml
import os
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent))

from config_manager import DimensionConfig

def test_yaml_loading(yaml_path):
    """YAML 파일 로딩 테스트"""
    
    print(f"=== YAML 로딩 테스트: {yaml_path} ===")
    
    if not os.path.exists(yaml_path):
        print(f"❌ YAML 파일이 존재하지 않습니다: {yaml_path}")
        return None
    
    try:
        # 1. 파일 읽기
        with open(yaml_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        print(f"✅ 파일 크기: {len(raw_content)} characters")
        
        # 2. YAML 파싱
        raw_data = yaml.safe_load(raw_content)
        print(f"✅ YAML 파싱 성공")
        print(f"   최상위 키들: {list(raw_data.keys()) if raw_data else 'None'}")
        
        # 3. dimensions 키 확인
        if 'dimensions' not in raw_data:
            print("❌ 'dimensions' 키가 없습니다!")
            print(f"   사용 가능한 키들: {list(raw_data.keys())}")
            return None
        
        dimensions = raw_data['dimensions']
        print(f"✅ dimensions 키 발견: {len(dimensions)}개 차원")
        
        # 4. 각 차원 확인
        for i, (dim_name, dim_config) in enumerate(dimensions.items(), 1):
            print(f"   {i}. {dim_name}")
            if isinstance(dim_config, dict):
                for key in dim_config.keys():
                    value_preview = str(dim_config[key])[:100] + "..." if len(str(dim_config[key])) > 100 else str(dim_config[key])
                    print(f"      {key}: {value_preview}")
            else:
                print(f"      ⚠️  차원 설정이 dict가 아닙니다: {type(dim_config)}")
        
        # 5. DimensionConfig 생성 테스트
        config = DimensionConfig(config_path=None)
        config.dimensions = dimensions
        print(f"✅ DimensionConfig 생성 성공: {len(config.dimensions)}개 차원")
        
        return config
        
    except yaml.YAMLError as e:
        print(f"❌ YAML 파싱 오류: {e}")
        return None
    except Exception as e:
        print(f"❌ 기타 오류: {e}")
        return None


def test_prompts_generation(config, topic="test_topic"):
    """prompts.py 생성 테스트"""
    
    print(f"\n=== prompts.py 생성 테스트 ===")
    
    if not config or not config.dimensions:
        print("❌ 유효한 config가 없습니다.")
        return False
    
    try:
        import tempfile
        import shutil
        
        # 임시 디렉토리에서 테스트
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_prompts = Path(temp_dir) / "test_prompts.py"
            
            # 원본 prompts.py 복사
            original_prompts = Path(__file__).parent / 'prompts.py'
            shutil.copy(original_prompts, temp_prompts)
            
            print(f"✅ 원본 prompts.py 복사됨: {temp_prompts}")
            
            # dimension_definitions 생성 테스트
            dims = config.dimensions
            
            new_dim_defs = ["dimension_definitions = {"]
            for dim_name, dim_config in dims.items():
                definition = dim_config.get('definition', '').replace('"""', '\\"\\"\\"')
                new_dim_defs.append(f"    '{dim_name}': \"\"\"{definition}\"\"\",")
            new_dim_defs.append("    }")
            
            print(f"✅ dimension_definitions 생성됨:")
            for line in new_dim_defs[:3]:  # 처음 3줄만 출력
                print(f"   {line}")
            if len(new_dim_defs) > 5:
                print(f"   ... ({len(new_dim_defs)-5}개 줄 더)")
            for line in new_dim_defs[-2:]:  # 마지막 2줄 출력
                print(f"   {line}")
            
            # 실제 파일 수정은 하지 않음 (테스트만)
            print(f"✅ prompts.py 생성 테스트 완료")
            return True
            
    except Exception as e:
        print(f"❌ prompts.py 생성 테스트 실패: {e}")
        return False


def main():
    """메인 테스트 함수"""
    
    print("🔍 YAML 차원 인식 문제 디버깅")
    print("=" * 50)
    
    # 테스트할 YAML 파일들
    yaml_files = [
        "example_battery.yaml",
        "configs/example_steel.yaml", 
        "configs/example_nlp.yaml",
        "user_data/yuingo/configs/generated_config.yaml"
    ]
    
    for yaml_file in yaml_files:
        yaml_path = Path(__file__).parent / yaml_file
        
        config = test_yaml_loading(yaml_path)
        if config:
            test_prompts_generation(config)
        
        print()
    
    print("🏁 테스트 완료!")
    print("\n💡 사용법:")
    print("   python debug_yaml_dimensions.py")
    print("   또는 특정 YAML 파일 테스트:")
    print("   python debug_yaml_dimensions.py path/to/your.yaml")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 사용자가 특정 YAML 파일 지정
        yaml_path = sys.argv[1]
        config = test_yaml_loading(yaml_path)
        if config:
            test_prompts_generation(config)
    else:
        # 전체 테스트 실행
        main()