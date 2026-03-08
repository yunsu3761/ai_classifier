"""
WIPS 데이터에서 랜덤으로 500개 샘플 추출하고 저장하는 스크립트
"""
import pandas as pd
import os
import random

# 파일 경로 설정
input_file = r"d:\TAXOADAPT\user_data\yuingo\datasets\web_custom_data\wips_converted_data.xlsx"
output_file = r"d:\TAXOADAPT\user_data\yuingo\datasets\web_custom_data\wips_sample_500.xlsx"

print("WIPS 데이터 샘플링 시작...")

# Excel 파일 읽기
try:
    print(f"원본 파일 읽는 중: {input_file}")
    df = pd.read_excel(input_file)
    print()
    print(f"원본 데이터 크기: {len(df)} rows, {len(df.columns)} columns")
    
    # 데이터 정보 출력
    print("\n컬럼 정보:")
    for i, col in enumerate(df.columns):
        print(f"  {i+1}. {col}")
    
    # 500개보다 적은 경우 전체 데이터 사용
    if len(df) <= 500:
        print(f"\n원본 데이터가 500개 이하입니다. 전체 {len(df)}개 데이터를 저장합니다.")
        sampled_df = df
    else:
        # 랜덤 시드 설정 (재현 가능한 결과를 위해)
        random.seed(42)
        
        # 랜덤 샘플링
        print(f"\n{len(df)}개 중 500개를 랜덤 샘플링합니다...")
        sampled_df = df.sample(n=500, random_state=42)
        print(f"샘플링 완료: {len(sampled_df)} rows")
    
    # 샘플 데이터 미리보기
    print("\n샘플 데이터 미리보기 (첫 3행):")
    print(sampled_df.head(3).to_string())
    
    # 새 파일로 저장
    print(f"\n저장 중: {output_file}")
    sampled_df.to_excel(output_file, index=False)
    
    print(f"✅ 샘플링 완료!")
    print(f"   입력: {input_file}")
    print(f"   출력: {output_file}")
    print(f"   샘플 count: {len(sampled_df)} rows")
    
except FileNotFoundError:
    print(f"❌ 파일을 찾을 수 없습니다: {input_file}")
except Exception as e:
    print(f"❌ 오류 발생: {e}")