# ====== 1. API 기본 설정 ======
import pandas as pd
import json
import os
import httpx
from openai import OpenAI

# OpenAI API Key 설정 (환경변수 또는 직접 입력)
API_KEY = "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"
MODEL_NAME = "gpt-4o-mini"

# 회사 네트워크 SSL 인증서 검증 우회
client = OpenAI(
    api_key=API_KEY,
    http_client=httpx.Client(verify=False)
)

print("✅ OpenAI API 설정 완료")

excel_path = "clipboard_data_20260211_154457.xlsx"
df = pd.read_excel(excel_path)
df_copy = df.copy()

df_copy.columns


# ====== 2. GPT 응답 추출 함수 ======
def extract_gpt_answer(prompt):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Your role is to draft detailed and precise technology classification definitions."},
                {"role": "user", "content": prompt}
            ],
            timeout=60
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"API 오류: {e}")
        return None

output_format = """{
  "Dimension_Name": "lithium",  
  "Dimension_Definitions": "Lithium: Lithium resource extraction and manufacturing is the process of producing lithium compounds from various lithium-bearing sources, including lithium ores (such as spodumene and lepidolite), brines (continental, geothermal, and oilfield brines), and clay-type resources. The primary objective of this process is to convert lithium into compounds such as lithium carbonate (Li₂CO₃), lithium hydroxide (LiOH), lithium chloride (LiCl), and lithium metal to meet the high demand in the electric vehicle and battery industries. Lithium classification encompasses innovations in lithium resource extraction and battery material manufacturing, but it excludes the production of finished lithium-ion batteries or the non-commercial use of lithium resources.",
  "Node_Dimension_Definitions": "Related patents focus on methods for efficiently extracting lithium through various processes such as physical and chemical sorting, evaporation, leaching, and electrochemical separation. For example, these include methods of mixing organic extractants to extract lithium from brine, the production of lithium eluate solutions using ion-exchange reactors, and lithium hydroxide manufacturing processes through multi-stage filtration systems. Additionally, technologies for crushing mixtures and surface modification to manufacture cathode active materials for lithium secondary batteries are included. Such technologies maximize the purity and efficiency of lithium and contribute to improving productivity through customized processes based on resource characteristics."
}"""



# ====== 3. Definition 분리 및 재구성 ======
import json
import time

# 데이터프레임 컬럼 확인

# 멈춘 지점부터 다시 시작하려면 이 변수들을 수정하세요
RESUME_FROM_LEVEL = 0  # 0=Level1, 1=Level2, 2=Level3, 3=Level4
RESUME_FROM_ROW = 0    # 해당 레벨에서 몇 번째 행부터 시작할지

level_steps = ['Level1', 'Level2', 'Level3', 'Level4']

for s, preset_level in enumerate(level_steps):
    if s < RESUME_FROM_LEVEL:
        print(f"{preset_level} 건너뛰기 (이미 처리됨)")
        continue
        
    selected_level = level_steps[:s+1]
    
    # 중복 제거하여 고유한 조합 가져오기
    unique_level_set = df_copy[selected_level].drop_duplicates()
    
    for row_num, (idx, row) in enumerate(unique_level_set.iterrows()):
        if s == RESUME_FROM_LEVEL and row_num < RESUME_FROM_ROW:
            print(f"행 {row_num} 건너뛰기 (이미 처리됨)")
            continue
            
        # NaN 값이 있는 행은 건너뛰기
        if row[selected_level].isna().any():
            print(f"NaN 값 있음, 건너뛰기: {row[selected_level].to_dict()}")
            continue
            
        # 현재 레벨 조합과 일치하는 모든 행 찾기
        mask = True
        for col in selected_level:
            mask = mask & (df_copy[col] == row[col])
        idxs = df_copy[mask].index
        
        # 일치하는 행이 없으면 건너뛰기
        if len(idxs) == 0:
            print(f"일치하는 행 없음, 건너뛰기: {row[selected_level].to_dict()}")
            continue
        
        # Level_Name 생성
        Level_Name = "-".join([str(row[col]) for col in selected_level])
        
        # Description 컬럼명 확인 및 가져오기
        desc_col = f'{preset_level}_Description'
        if desc_col not in df_copy.columns:
            print(f"Warning: {desc_col} 컬럼이 없습니다.")
            continue
            
        # Description을 df_copy에서 직접 가져오기 (해당 조합의 첫 번째 행에서)
        Description = df_copy.loc[idxs[0], desc_col]
        
        print(f"처리 중: {Level_Name} (행 {row_num})")

        prompt = f"""<입력 정보>를 참고해서, [기술]에 대한 [Description]을 읽고, 이를 [Two Definitions] 성격에 따라 재구성해줘. <출력 예시>를 참고해서 결과를 json 형태로 생성해.

        ---
        <입력 정보>
        [기술]
        {Level_Name}

        [Description]
        {Description}

        [Two Definitions]
        1) dimension_definitions: Dimension에 대해서 LLM이 알 수 있도록 Dimension의 정의 작성 
        2) node_dimension_definitions: 해당 Dimension에 포함될 특허는 어떤 내용(기술) 또는 방식들이 포함되는지 예시 내포 작성     
        </입력 정보>
        ---

        Output your result ONLY in the following JSON format.
        Do not include explanations outside the JSON.

        ---
        <출력 예시>
        {output_format}
        </출력 예시>
        ---

        CRITICAL JSON RULES:
        - Output MUST be valid JSON.
        - Do NOT include comments (// or /* */).
        - DO NOT wrap the output in ``` or ```json. Output raw JSON only.
        - Do NOT include explanations, apologies, or notes.
        - If a suitable rationale sentence cannot be found, use an empty string "" instead.
        - Every value in JSON must be a valid JSON type (string or array).
        """

        response = extract_gpt_answer(prompt)
        
        try:
            result_json = json.loads(response)

            name = result_json.get("Dimension_Name", "")
            definitions = result_json.get("Dimension_Definitions", "")
            node_definitions = result_json.get("Node_Dimension_Definitions", "")

            df_copy.loc[idxs, f"{preset_level}_Dimension_Name"] = name
            df_copy.loc[idxs, f"{preset_level}_Dimension_Definitions"] = definitions
            df_copy.loc[idxs, f"{preset_level}_Node_Dimension_Definitions"] = node_definitions

        except Exception as e:
            print(f"[{idx+1}] JSON 파싱 오류: {e}")
            print(response)
            continue
        
        time.sleep(1)
        print(row[selected_level].to_dict())
    print(preset_level)

['Level1_Description', 'Level2_Description', 'Level3_Description', 'Level4_Description']

# ====== 3.5 Description 번역 ======
def translate_text(text, target_language="English"):
    """텍스트를 지정된 언어로 번역하는 함수"""
    if pd.isna(text) or text == "":
        return ""
    
    try:
        prompt = f"""Translate the following Korean text to {target_language}. 
        Keep technical terms accurate and maintain the original meaning.
        Only output the translated text without any explanations or additional comments.

        Text to translate:
        {text}"""
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a professional technical translator."},
                {"role": "user", "content": prompt}
            ],
            timeout=60
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"번역 오류: {e}")
        return text  # 오류 시 원본 텍스트 반환

def translate_descriptions():
    """레벨별로 중복 제거하여 Description을 번역하는 함수"""
    level_steps = ['Level1', 'Level2', 'Level3', 'Level4']
    
    for s, preset_level in enumerate(level_steps):
        print(f"\n=== {preset_level} 번역 시작 ===")
        
        desc_col = f'{preset_level}_Description'
        english_col_name = f'{preset_level}_Description_EN'
        
        # 컬럼 확인
        if desc_col not in df_copy.columns:
            print(f"Warning: {desc_col} 컬럼이 없습니다.")
            continue
        
        # 영어 번역 컬럼 생성
        if english_col_name not in df_copy.columns:
            df_copy[english_col_name] = ""
        
        selected_level = level_steps[:s+1]
        
        # 중복 제거하여 고유한 조합 가져오기
        unique_level_set = df_copy[selected_level].drop_duplicates()
        
        translated_count = 0
        for row_num, (idx, row) in enumerate(unique_level_set.iterrows()):
            # NaN 값이 있는 행은 건너뛰기
            if row[selected_level].isna().any():
                print(f"NaN 값 있음, 건너뛰기: {row[selected_level].to_dict()}")
                continue
            
            # 현재 레벨 조합과 일치하는 모든 행 찾기
            mask = True
            for col in selected_level:
                mask = mask & (df_copy[col] == row[col])
            idxs = df_copy[mask].index
            
            # 일치하는 행이 없으면 건너뛰기
            if len(idxs) == 0:
                continue
            
            # Description 가져오기 (해당 조합의 첫 번째 행에서)
            description = df_copy.loc[idxs[0], desc_col]
            
            # Description이 비어있거나 이미 번역된 경우 건너뛰기
            if pd.isna(description) or description == "":
                continue
                
            # 이미 번역되어 있으면 건너뛰기
            existing_translation = df_copy.loc[idxs[0], english_col_name]
            if pd.notna(existing_translation) and existing_translation != "":
                continue
            
            # Level_Name 생성 (로그용)
            Level_Name = "-".join([str(row[col]) for col in selected_level])
            
            print(f"번역 중 ({row_num+1}/{len(unique_level_set)}): {Level_Name}")
            print(f"  Description: {description[:50]}...")
            
            # 번역 실행
            translated = translate_text(description)
            
            # 같은 조합을 가진 모든 행에 번역 결과 적용
            df_copy.loc[idxs, english_col_name] = translated
            translated_count += 1
            
            time.sleep(0.5)  # API 제한 방지
        
        print(f"✅ {preset_level} 번역 완료 ({translated_count}개 항목 번역)")

print("\n번역 함수가 준비되었습니다!")
print("translate_descriptions()를 실행하면 모든 Description 컬럼이 영어로 번역됩니다.")

# 번역 실행 (필요시 주석 해제)
# translate_descriptions()

# ====== 4. 깨진 값들 재처리 ======
def fix_chemical_formula(text):
    """깨진 화학식을 복구하는 함수 - 유니코드 안전 버전"""
    if pd.isna(text) or text == "":
        return text
    
    text_str = str(text)
    
    # 유니코드 기반 복구 매핑 (더 안전함)
    replacements = [
        # 아래첨자들 (UTF-8 깨짐 패턴)
        ("\u00e2\u0082\u0080", "\u2080"),  # ₀
        ("\u00e2\u0082\u0081", "\u2081"),  # ₁
        ("\u00e2\u0082\u0082", "\u2082"),  # ₂
        ("\u00e2\u0082\u0083", "\u2083"),  # ₃
        ("\u00e2\u0082\u0084", "\u2084"),  # ₄
        ("\u00e2\u0082\u0085", "\u2085"),  # ₅
        ("\u00e2\u0082\u0086", "\u2086"),  # ₆
        ("\u00e2\u0082\u0087", "\u2087"),  # ₇
        ("\u00e2\u0082\u0088", "\u2088"),  # ₈
        ("\u00e2\u0082\u0089", "\u2089"),  # ₉
        
        # 위첨자들  
        ("\u00e2\u0081\u00b0", "\u2070"),  # ⁰
        ("\u00c2\u00b9", "\u00b9"),        # ¹
        ("\u00c2\u00b2", "\u00b2"),        # ²
        ("\u00c2\u00b3", "\u00b3"),        # ³
        ("\u00e2\u0081\u00b4", "\u2074"),  # ⁴
        ("\u00e2\u0081\u00b5", "\u2075"),  # ⁵
        ("\u00e2\u0081\u00b6", "\u2076"),  # ⁶
        ("\u00e2\u0081\u00b7", "\u2077"),  # ⁷
        ("\u00e2\u0081\u00b8", "\u2078"),  # ⁸
        ("\u00e2\u0081\u00b9", "\u2079"),  # ⁹
        
        # 기타 특수문자
        ("\u00c2\u00b7", "\u00b7"),        # · (middle dot)
        ("\u00c2\u00b1", "\u00b1"),        # ± (plus-minus)
        ("\u00c2\u00b0", "\u00b0"),        # ° (degree)
        
        # 그리스 문자
        ("\u00ce\u00b1", "\u03b1"),        # α (alpha)
        ("\u00ce\u00b2", "\u03b2"),        # β (beta)
        ("\u00ce\u00b3", "\u03b3"),        # γ (gamma)
        ("\u00ce\u00b4", "\u03b4"),        # δ (delta)
        
        # 이온 기호
        ("\u00e2\u0081\u00ba", "\u207a"),  # ⁺
        ("\u00e2\u0081\u00bb", "\u207b"),  # ⁻
        
        # 기타 화학 기호
        ("\u00e2\u0086\u0092", "\u2192"),  # → (arrow)
        ("\u00e2\u0087\u008c", "\u21cc"),  # ⇌ (equilibrium)
    ]
    
    # 모든 패턴 적용
    for broken, fixed in replacements:
        text_str = text_str.replace(broken, fixed)
    
    return text_str

def is_corrupted_text(text):
    """텍스트가 깨졌는지 확인하는 함수"""
    if pd.isna(text) or text == "":
        return False
    # 깨진 패턴만 감지 (정상적인 유니코드 문자는 제외)
    corrupted_patterns = [
        'ê´ë', 'í¹í', 'ë¤ì', 'ë¬¼ë¦¬', 'ííì',  # 한글 깨짐
        r'\u00c2\u00b7', r'\u00e2\u0082', r'\u00e2\u0081',  # raw string으로 깨진 패턴
        r'\u00c2\u00b²', r'\u00c2\u00b³', r'\u00ce\u00b1',
        '\u00c2\u00b7', '\u00c2\u00b2', '\u00c2\u00b3', '\u00ce\u00b1',  # 실제 깨진 바이트 시퀀스
        'Â·', 'Â²', 'Â³', 'Î±', 'Î²', 'Î³'  # 깨진 특수문자 패턴만
    ]
    # 참고: '·', '²', '³', 'α' 등은 정상적인 화학식 문자이므로 제외
    return any(pattern in str(text) for pattern in corrupted_patterns)

def find_and_reprocess_corrupted():
    """깨진 값들을 찾아서 다시 처리"""
    corrupted_rows = []
    
    for level_step in ['Level1', 'Level2', 'Level3', 'Level4']:
        dim_def_col = f'{level_step}_Dimension_Definitions'
        node_def_col = f'{level_step}_Node_Dimension_Definitions'
        
        if dim_def_col in df_copy.columns:
            corrupted_mask = df_copy[dim_def_col].apply(is_corrupted_text)
            corrupted_rows.extend(df_copy[corrupted_mask].index.tolist())
        
        if node_def_col in df_copy.columns:
            corrupted_mask = df_copy[node_def_col].apply(is_corrupted_text)
            corrupted_rows.extend(df_copy[corrupted_mask].index.tolist())
    
    corrupted_rows = list(set(corrupted_rows))  # 중복 제거
    print(f"깨진 값이 발견된 행들: {corrupted_rows}")
    
    return corrupted_rows



# ====== 화학식 및 특수문자 복구 ======
print("\n=== 화학식 및 특수문자 복구 시작 ===")

# 모든 Definition 컬럼에서 깨진 화학식 복구
definition_columns = []
for level in ['Level1', 'Level2', 'Level3', 'Level4']:
    for col_type in ['Dimension_Name', 'Dimension_Definitions', 'Node_Dimension_Definitions']:
        col_name = f'{level}_{col_type}'
        if col_name in df_copy.columns:
            definition_columns.append(col_name)

fixed_count = 0
for col_name in definition_columns:
    for idx in df_copy.index:
        original_text = df_copy.loc[idx, col_name]  
        if pd.notna(original_text) and original_text != "":
            fixed_text = fix_chemical_formula(original_text)
            if fixed_text != original_text:
                df_copy.loc[idx, col_name] = fixed_text
                fixed_count += 1
                print(f"행 {idx}, {col_name}: 화학식 복구")
                print(f"  이전: {repr(original_text[:100])}...")
                print(f"  이후: {repr(fixed_text[:100])}...")

print(f"총 {fixed_count}개 항목의 화학식/특수문자가 복구되었습니다.")

# 복구 후 테스트
print("\n=== 복구 결과 테스트 ===")

# 테스트할 깨진 화학식들을 유니코드로 안전하게 생성
def create_test_chemicals():
    """테스트용 깨진 화학식을 생성하는 함수"""
    tests = []
    
    # Li₂CO₃ (탄산리튬)
    li2co3_broken = "Li\u00e2\u0082\u0082CO\u00e2\u0082\u0083"
    li2co3_fixed = "Li₂CO₃"
    tests.append((li2co3_broken, li2co3_fixed, "탄산리튬"))
    
    # H₂SO₄ (황산)  
    h2so4_broken = "H\u00e2\u0082\u0082SO\u00e2\u0082\u0084"
    h2so4_fixed = "H₂SO₄"
    tests.append((h2so4_broken, h2so4_fixed, "황산"))
    
    # Ca²⁺ (칼슘 이온)
    ca2_broken = "Ca\u00c2\u00b2\u00e2\u0081\u00ba"
    ca2_fixed = "Ca²⁺"
    tests.append((ca2_broken, ca2_fixed, "칼슘 이온"))
    
    # 25°C (온도)
    temp_broken = "25\u00c2\u00b0C"  
    temp_fixed = "25°C"
    tests.append((temp_broken, temp_fixed, "온도"))
    
    # α-Fe (알파 철)
    alpha_broken = "\u00ce\u00b1-Fe"
    alpha_fixed = "α-Fe"
    tests.append((alpha_broken, alpha_fixed, "알파 철"))
    
    return tests

test_cases = create_test_chemicals()

print("화학식 복구 테스트:")
for i, (broken, expected, name) in enumerate(test_cases, 1):
    try:
        result = fix_chemical_formula(broken)
        success = result == expected
        status = "✅ 성공" if success else "❌ 실패"
        
        print(f"{i}. {name}: {status}")
        print(f"   길이: {len(broken)} → {len(result)}")
        if not success:
            print(f"   예상: {expected}")
            print(f"   실제: {result}")
    except Exception as e:
        print(f"{i}. {name}: ❌ 오류 - {e}")

print("\n화학식 복구 함수가 준비되었습니다!")






# 올바른 pandas 문법: 여러 컬럼 선택
df_copy[['Level1_Dimension_Name','Level1_Dimension_Definitions','Level1_Node_Dimension_Definitions']].head()

# ====== 11. Dimension 컬럼들 번역 ======

def translate_dimension_columns():
    """모든 Dimension 관련 컬럼들을 번역하는 함수"""
    level_steps = ['Level1', 'Level2', 'Level3', 'Level4']
    dimension_types = ['Dimension_Name', 'Dimension_Definitions', 'Node_Dimension_Definitions']
    
    for preset_level in level_steps:
        print(f"\n=== {preset_level} Dimension 컬럼 번역 시작 ===")
        
        selected_level = level_steps[:level_steps.index(preset_level)+1]
        
        # 중복 제거하여 고유한 조합 가져오기
        unique_level_set = df_copy[selected_level].drop_duplicates()
        
        for dim_type in dimension_types:
            col_name = f'{preset_level}_{dim_type}'
            english_col_name = f'{preset_level}_{dim_type}_EN'
            
            # 컬럼 확인
            if col_name not in df_copy.columns:
                print(f"Warning: {col_name} 컬럼이 없습니다.")
                continue
            
            # 영어 번역 컬럼 생성
            if english_col_name not in df_copy.columns:
                df_copy[english_col_name] = ""
            
            print(f"  {col_name} 번역 중...")
            translated_count = 0
            
            for row_num, (idx, row) in enumerate(unique_level_set.iterrows()):
                # NaN 값이 있는 행은 건너뛰기
                if row[selected_level].isna().any():
                    continue
                
                # 현재 레벨 조합과 일치하는 모든 행 찾기
                mask = True
                for col in selected_level:
                    mask = mask & (df_copy[col] == row[col])
                idxs = df_copy[mask].index
                
                if len(idxs) == 0:
                    continue
                
                # 번역할 텍스트 가져오기 (해당 조합의 첫 번째 행에서)
                text_to_translate = df_copy.loc[idxs[0], col_name]
                
                # 텍스트가 비어있거나 이미 번역된 경우 건너뛰기
                if pd.isna(text_to_translate) or text_to_translate == "":
                    continue
                    
                # 이미 번역되어 있으면 건너뛰기
                existing_translation = df_copy.loc[idxs[0], english_col_name]
                if pd.notna(existing_translation) and existing_translation != "":
                    continue
                
                # 영어인지 확인 (대부분 영어 문자로 구성된 경우 번역하지 않음)
                if is_mostly_english(text_to_translate):
                    df_copy.loc[idxs, english_col_name] = text_to_translate
                    continue
                
                # Level_Name 생성 (로그용)
                Level_Name = "-".join([str(row[col]) for col in selected_level])
                
                print(f"    번역: {Level_Name} - {text_to_translate[:30]}...")
                
                # 번역 실행
                translated = translate_text(text_to_translate)
                
                # 같은 조합을 가진 모든 행에 번역 결과 적용
                df_copy.loc[idxs, english_col_name] = translated
                translated_count += 1
                
                time.sleep(0.3)  # API 제한 방지
            
            print(f"  ✅ {col_name} 번역 완료 ({translated_count}개 항목)")

def is_mostly_english(text):
    """텍스트가 대부분 영어로 구성되어 있는지 확인하는 함수"""
    if pd.isna(text) or text == "":
        return True
    
    text_str = str(text).strip()
    if len(text_str) == 0:
        return True
    
    # 영어 문자, 숫자, 공백, 기본 특수문자 개수 계산
    english_chars = sum(1 for c in text_str if c.isascii() and (c.isalnum() or c.isspace() or c in '.,;:()-_/'))
    total_chars = len(text_str)
    
    # 80% 이상이 영어 문자면 영어로 간주
    return (english_chars / total_chars) >= 0.8

print("\n=== Dimension 컬럼 번역 함수가 준비되었습니다! ===")
print("translate_dimension_columns()를 실행하면 모든 Dimension 관련 컬럼이 영어로 번역됩니다.")

# 번역 실행 (필요시 주석 해제)
translate_dimension_columns()


df_copy.to_excel("final_taxonomy_with_definitions.xlsx", index=False)

selected_columns = [[level,f'{level}_Description_EN',f'{level}_Dimension_Name_EN',f'{level}_Dimension_Definitions_EN',
                     f'{level}_Node_Dimension_Definitions_EN'] for level in level_steps]

import itertools
import re

df_copy_en = df_copy[list(itertools.chain.from_iterable(selected_columns))]
df_copy_en.columns = [re.sub("_EN$","",col) for col in df_copy_en.columns]

df_copy_en[[f'{level}_Dimension_Name' for level in level_steps]] = df_copy_en[[f'{level}_Dimension_Name' for level in level_steps]].apply(lambda x: x.str.lower())
df_copy_en[[f'{level}_Dimension_Name' for level in level_steps]] = df_copy_en[[f'{level}_Dimension_Name' for level in level_steps]].apply(lambda x: x.apply(lambda y: re.sub(r'\s|-', '_', y) if isinstance(y, str) else y))
df_copy_en.to_excel("final_taxonomy_with_definitions_en.xlsx", index=False)






# ====== 8. DAG Taxonomy 변환 (중첩 JSON 트리 구조) ======
def build_taxonomy_tree(df, level_columns=None):
    """
    df_copy에서 Level1~Level4 계층 정보와 Definition을 읽어
    중첩 JSON 트리(DAG) 구조로 변환하는 함수.
    
    Level 번호는 1씩 줄여서 Level1→Level0, Level2→Level1, ... 으로 변환.
    
    Returns:
        dict: 중첩 트리 구조의 Taxonomy
    """
    if level_columns is None:
        level_columns = ['Level1', 'Level2', 'Level3', 'Level4']
    
    # 루트 노드 생성
    taxonomy = {
        "dimension_name": "root",
        "level": -1,
        "dimension_definitions": "",
        "node_dimension_definitions": "",
        "children": []
    }
    
    def get_definition_info(df_subset, level_col):
        """해당 레벨의 Definition 정보를 가져오는 함수"""
        dim_name_col = f'{level_col}_Dimension_Name'
        dim_def_col = f'{level_col}_Dimension_Definitions'
        node_def_col = f'{level_col}_Node_Dimension_Definitions'
        desc_en_col = f'{level_col}_Description'
        
        info = {
            "dimension_name": "",
            "dimension_definitions": "",
            "node_dimension_definitions": "",
            "description": ""
        }
        
        # 첫 번째 유효한 값 가져오기
        if dim_name_col in df_subset.columns:
            vals = df_subset[dim_name_col].dropna()
            if len(vals) > 0:
                info["dimension_name"] = str(vals.iloc[0])
        
        if dim_def_col in df_subset.columns:
            vals = df_subset[dim_def_col].dropna()
            if len(vals) > 0:
                info["dimension_definitions"] = str(vals.iloc[0])
        
        if node_def_col in df_subset.columns:
            vals = df_subset[node_def_col].dropna()
            if len(vals) > 0:
                info["node_dimension_definitions"] = str(vals.iloc[0])
        
        if desc_en_col in df_subset.columns:
            vals = df_subset[desc_en_col].dropna()
            if len(vals) > 0:
                info["description"] = str(vals.iloc[0])
        
        return info
    
    def build_subtree(df_subset, level_idx):
        """재귀적으로 서브트리를 구성하는 함수"""
        if level_idx >= len(level_columns):
            return []
        
        current_level_col = level_columns[level_idx]
        new_level_num = level_idx  # Level1→Level0, Level2→Level1, ...
        
        # 현재 레벨에서 NaN이 아닌 고유 값들
        if current_level_col not in df_subset.columns:
            return []
            
        unique_values = df_subset[current_level_col].dropna().unique()
        
        children = []
        for value in unique_values:
            # 해당 값에 해당하는 행들 필터링
            mask = df_subset[current_level_col] == value
            subset = df_subset[mask]
            
            if len(subset) == 0:
                continue
            
            # Definition 정보 가져오기
            def_info = get_definition_info(subset, current_level_col)
            
            # 노드 생성
            node = {
                "dimension_name": def_info["dimension_name"] if def_info["dimension_name"] else str(value),
                "original_value": str(value),
                "level": new_level_num,
                "description": def_info["description"],
                "dimension_definitions": def_info["dimension_definitions"],
                "node_dimension_definitions": def_info["node_dimension_definitions"],
                "children": build_subtree(subset, level_idx + 1)
            }
            
            children.append(node)
        
        return children
    
    # 트리 구축
    taxonomy["children"] = build_subtree(df, 0)
    
    return taxonomy


# Taxonomy 트리 생성
taxonomy_tree = build_taxonomy_tree(df_copy_en)

# JSON으로 저장
import json
taxonomy_json = json.dumps(taxonomy_tree, ensure_ascii=False, indent=2)

with open("taxonomy_tree.json", "w", encoding="utf-8") as f:
    f.write(taxonomy_json)

print("Taxonomy DAG 트리가 taxonomy_tree.json으로 저장되었습니다.")

# 트리 구조 요약 출력
def print_tree_summary(node, indent=0):
    """트리 구조를 시각적으로 출력하는 함수"""
    prefix = "  " * indent
    connector = "|-- " if indent > 0 else ""
    
    name = node.get("original_value", node.get("dimension_name", "root"))
    level = node.get("level", -1)
    n_children = len(node.get("children", []))
    has_def = "O" if node.get("dimension_definitions", "") else "X"
    
    if level >= 0:
        print(f"{prefix}{connector}[Level{level}] {name} (definitions: {has_def}, children: {n_children})")
    else:
        print(f"{prefix}[ROOT] (children: {n_children})")
    
    for child in node.get("children", []):
        print_tree_summary(child, indent + 1)

print("\n=== Taxonomy 트리 구조 ===")
print_tree_summary(taxonomy_tree)


# ====== 9. DAG 텍스트 형식으로 변환 및 TXT 저장 ======
def node_to_dag_text(node, indent=0):
    """노드를 DAG 텍스트 형식으로 변환하는 함수"""
    prefix = "     " * indent
    sep = prefix + "-" * 40
    lines = []
    
    label = node.get("dimension_name", node.get("original_value", "root"))
    # dimension_name이 비어있으면 original_value 사용
    if not label or label == "":
        label = node.get("original_value", "root")
    level = node.get("level", -1)
    dim_def = node.get("description", "") or "None"
    children = node.get("children", [])
    
    lines.append(f"{prefix}Label: {label}")
    lines.append(f"{prefix}Dimension: technology_classification")
    lines.append(f"{prefix}Description: {dim_def}")
    lines.append(f"{prefix}Level: {level}")
    lines.append(f"{prefix}Source: Initial")
    lines.append(sep)
    
    if children:
        lines.append(f"{prefix}Children:")
        for child in children:
            lines.extend(node_to_dag_text(child, indent + 1))
        lines.append(sep)
    
    return lines


def taxonomy_to_dag_text(taxonomy_tree):
    """전체 Taxonomy 트리를 DAG 텍스트 형식으로 변환"""
    all_lines = []
    
    # 루트의 children을 최상위 노드로 출력
    for root_child in taxonomy_tree.get("children", []):
        all_lines.extend(node_to_dag_text(root_child, indent=0))
        all_lines.append("")  # 최상위 노드 간 빈 줄
    
    return "\n".join(all_lines)

# DAG 텍스트 생성 및 저장
dag_text = taxonomy_to_dag_text(taxonomy_tree)

with open("taxonomy_dag.txt", "w", encoding="utf-8") as f:
    f.write(dag_text)

print("Taxonomy DAG 텍스트가 taxonomy_dag.txt로 저장되었습니다.")

# ====== 10. Level 0별로 DAG 텍스트 분리 저장 ======
def save_dag_by_level0(taxonomy_tree):
    """Level 0별로 DAG 텍스트를 분리해서 저장하는 함수"""
    
    for root_child in taxonomy_tree.get("children", []):
        # Level 0 노드의 label 이름 가져오기
        label0_name = root_child.get("dimension_name", root_child.get("original_value", "unknown"))
        
        # 파일명에 사용할 수 없는 문자들을 안전하게 변환
        safe_filename = label0_name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
        
        # 개별 노드의 DAG 텍스트 생성
        individual_dag_text = "\n".join(node_to_dag_text(root_child, indent=0))
        
        # 파일명 생성
        filename = f"initial_taxo_{safe_filename}.txt"
        
        # 파일 저장
        with open(filename, "w", encoding="utf-8") as f:
            f.write(individual_dag_text)
        
        print(f"✅ Level 0 '{label0_name}' DAG 텍스트가 {filename}으로 저장되었습니다.")

# Level 0별 분리 저장 실행
save_dag_by_level0(taxonomy_tree)

print("\n=== DAG 텍스트 미리보기 (처음 2000자) ===")
print(dag_text[:2000])
