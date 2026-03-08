"""
YAML 파일에서 차원 정의를 읽어서 prompts.py와 main2.py를 자동으로 업데이트하는 스크립트
사용법: python update_dimensions.py <yaml_file_path>
예시: python update_dimensions.py configs/example_battery.yaml
"""

import yaml
import re
import sys
import os


def load_yaml_dimensions(yaml_path):
    """YAML 파일에서 차원 정의를 로드"""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data['dimensions']


def generate_dimension_definitions(dimensions):
    """dimension_definitions 딕셔너리 생성"""
    lines = ["# Auto-generated from YAML\ndimension_definitions = {"]
    for dim_name, dim_data in dimensions.items():
        definition = dim_data['definition'].replace('"', '\\"').replace("'", "\\'")
        lines.append(f'    \'{dim_name}\': """{dim_data["definition"]}""",')
    lines.append("}")
    return '\n'.join(lines)


def generate_node_dimension_definitions(dimensions):
    """node_dimension_definitions 딕셔너리 생성"""
    lines = ["# Auto-generated from YAML\nnode_dimension_definitions = {"]
    for dim_name, dim_data in dimensions.items():
        lines.append(f'    \'{dim_name}\': """{dim_data["node_definition"]}""",')
    lines.append("}")
    return '\n'.join(lines)


def generate_type_cls_system_instruction(dimensions):
    """type_cls_system_instruction 문자열 생성"""
    lines = ['type_cls_system_instruction = """You are a helpful multi-label classification assistant which helps me label papers based on their paper type. They may be more than one.\n\nPaper types (type:definition):\n']
    
    for idx, (dim_name, dim_data) in enumerate(dimensions.items(), 1):
        # 정의의 첫 문장만 추출 (간결하게)
        full_def = dim_data['definition']
        # 첫 번째 문장 추출 (첫 번째 마침표까지)
        first_sentence = full_def.split('.')[0] + '.'
        lines.append(f'{idx}. {dim_name}: {first_sentence}')
    
    lines.append('"""')
    return '\n'.join(lines)


def generate_type_cls_schema(dimensions):
    """TypeClsSchema 클래스 생성"""
    lines = ["class TypeClsSchema(BaseModel):"]
    for dim_name in dimensions.keys():
        lines.append(f"  {dim_name}: bool")
    return '\n'.join(lines)


def generate_type_cls_main_prompt(dimensions):
    """type_cls_main_prompt 함수 생성"""
    lines = ['def type_cls_main_prompt(paper):\n   out = f"""Given the following paper title and abstract, can you output a Pythonic list of all paper type labels relevant to this paper. \n\n"Title": "{paper.title}"\n"Abstract": "{paper.abstract}"\n\nYour output should be in the following JSON format:\n{{']
    
    for dim_name, dim_data in dimensions.items():
        # 간단한 설명 생성
        short_desc = dim_data['definition'].split(':')[0] if ':' in dim_data['definition'] else dim_name.replace('_', ' ')
        lines.append(f'  "{dim_name}": <return True if the paper focuses on {short_desc.lower()} technologies, False otherwise>,')
    
    lines.append('}}\n"""\n   return out')
    return '\n'.join(lines)


def update_prompts_py(dimensions, prompts_path='prompts.py'):
    """prompts.py 파일 업데이트"""
    with open(prompts_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. dimension_definitions 업데이트
    new_dim_def = generate_dimension_definitions(dimensions)
    content = re.sub(
        r'# .*\ndimension_definitions = \{[^}]*\}',
        new_dim_def,
        content,
        flags=re.DOTALL
    )
    
    # 2. node_dimension_definitions 업데이트
    new_node_dim_def = generate_node_dimension_definitions(dimensions)
    content = re.sub(
        r'# .*\nnode_dimension_definitions = \{[^}]*\}',
        new_node_dim_def,
        content,
        flags=re.DOTALL
    )
    
    # 3. type_cls_system_instruction 업데이트
    new_type_cls_sys = generate_type_cls_system_instruction(dimensions)
    content = re.sub(
        r'type_cls_system_instruction = """.*?"""',
        new_type_cls_sys,
        content,
        flags=re.DOTALL
    )
    
    # 4. TypeClsSchema 업데이트
    new_schema = generate_type_cls_schema(dimensions)
    content = re.sub(
        r'class TypeClsSchema\(BaseModel\):.*?(?=\n\n|\nclass |\ndef |# )',
        new_schema,
        content,
        flags=re.DOTALL
    )
    
    # 5. type_cls_main_prompt 업데이트
    new_prompt_func = generate_type_cls_main_prompt(dimensions)
    content = re.sub(
        r'def type_cls_main_prompt\(paper\):.*?return out',
        new_prompt_func,
        content,
        flags=re.DOTALL
    )
    
    with open(prompts_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Updated {prompts_path}")


def update_main2_py(dimensions, main_path='main2.py'):
    """main2.py 파일 업데이트"""
    with open(main_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # args.dimensions 업데이트
    dim_list = ', '.join([f'"{dim}"' for dim in dimensions.keys()])
    new_dimensions_line = f'    args.dimensions = [{dim_list}]'
    
    content = re.sub(
        r'    args\.dimensions = \[.*?\]',
        new_dimensions_line,
        content,
        flags=re.DOTALL
    )
    
    with open(main_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Updated {main_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python update_dimensions.py <yaml_file_path>")
        print("Example: python update_dimensions.py configs/example_battery.yaml")
        sys.exit(1)
    
    yaml_path = sys.argv[1]
    
    if not os.path.exists(yaml_path):
        print(f"Error: YAML file not found: {yaml_path}")
        sys.exit(1)
    
    print(f"Loading dimensions from {yaml_path}...")
    dimensions = load_yaml_dimensions(yaml_path)
    
    print(f"Found {len(dimensions)} dimensions: {', '.join(dimensions.keys())}")
    print("\nUpdating code files...")
    
    # 현재 스크립트의 디렉토리 기준으로 파일 경로 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompts_path = os.path.join(script_dir, 'prompts.py')
    main_path = os.path.join(script_dir, 'main2.py')
    
    update_prompts_py(dimensions, prompts_path)
    update_main2_py(dimensions, main_path)
    
    print("\n✅ All files updated successfully!")
    print("\nUpdated dimensions:")
    for idx, dim_name in enumerate(dimensions.keys(), 1):
        print(f"  {idx}. {dim_name}")


if __name__ == "__main__":
    main()
