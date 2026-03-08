# Dimension Update Script

YAML 파일에서 차원(dimension) 정의를 읽어서 자동으로 `prompts.py`와 `main2.py`를 업데이트하는 스크립트입니다.

## 사용법

```bash
python update_dimensions.py <yaml_file_path>
```

## 예시

```bash
# Battery 차원으로 업데이트
python update_dimensions.py configs/example_battery.yaml

# 다른 YAML 파일 사용
python update_dimensions.py configs/my_custom_dimensions.yaml
```

## 기능

이 스크립트는 YAML 파일의 `dimensions` 섹션을 읽어서 다음 항목들을 자동으로 업데이트합니다:

### prompts.py에서 업데이트되는 항목:
1. `dimension_definitions` - 차원 정의 딕셔너리
2. `node_dimension_definitions` - 노드 차원 정의 딕셔너리
3. `type_cls_system_instruction` - 분류 시스템 프롬프트
4. `TypeClsSchema` - Pydantic 스키마 클래스
5. `type_cls_main_prompt()` - 분류 프롬프트 함수

### main2.py에서 업데이트되는 항목:
1. `args.dimensions` - 차원 리스트

## YAML 파일 형식

```yaml
dimensions:
  dimension_name_1:
    definition: "차원 정의..."
    node_definition: "노드 정의..."
  dimension_name_2:
    definition: "차원 정의..."
    node_definition: "노드 정의..."
```

## 주의사항

- 스크립트 실행 전에 파일을 백업하는 것을 권장합니다
- YAML 파일의 `dimensions` 섹션이 올바른 형식인지 확인하세요
- 자동 생성되는 코드는 기존 파일 내용을 덮어씁니다
