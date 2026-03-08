"""
Web Interface 자동 핫픽스 적용 스크립트
session_state 보존 로직을 web_interface.py에 자동으로 추가합니다.
"""
import re

def apply_hotfix():
    web_interface_path = "web_interface.py"
    
    # 백업 생성
    import shutil
    shutil.copy(web_interface_path, f"{web_interface_path}.backup")
    print(f"✅ 백업 생성: {web_interface_path}.backup")
    
    # 파일 읽기
    with open(web_interface_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 핫픽스 코드
    hotfix_code = '''
# 중요: 이미 dimensions가 로드되어 있으면 config_loaded도 True로 설정 (rerun 시 보존)
if st.session_state.dimensions and not st.session_state.config_loaded:
    print(f"[DEBUG] Preserving existing dimensions after rerun: {list(st.session_state.dimensions.keys())}")
    st.session_state.config_loaded = True
    # Config 객체도 복구
    if not st.session_state.config:
        st.session_state.config = DimensionConfig(config_path=None)
        st.session_state.config.dimensions = st.session_state.dimensions.copy()
    st.info(f"🔄 차원 정보 복구됨: {len(st.session_state.dimensions)}개 차원")
'''
    
    # load_user_config() 호출 이후에 삽입
    pattern = r'(if st\.session_state\.get\(\'logged_in\', False\):\s*\n\s*load_user_config\(\))'
    
    if re.search(pattern, content):
        # 핫픽스가 이미 적용되었는지 확인
        if "Preserving existing dimensions after rerun" in content:
            print("⚡ 핫픽스가 이미 적용되어 있습니다.")
            return True
        
        # 핫픽스 적용
        new_content = re.sub(pattern, r'\1' + hotfix_code, content)
        
        # 파일 저장
        with open(web_interface_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ 핫픽스 적용 완료!")
        print("🔄 Streamlit을 재시작하세요: Ctrl+C 후 streamlit run web_interface.py")
        return True
    else:
        print("❌ 적용 지점을 찾을 수 없습니다.")
        return False

if __name__ == "__main__":
    print("🔧 Web Interface 핫픽스 적용 중...")
    success = apply_hotfix()
    
    if success:
        print("\n💡 사용 방법:")
        print("1. Streamlit 재시작 (Ctrl+C 후 streamlit run web_interface.py)")
        print("2. YAML 파일 업로드")
        print("3. 엑셀 데이터 업로드")
        print("4. 차원 정보가 유지되는지 확인")
    else:
        print("\n🛠️ 수동 적용 방법:")
        print("web_interface.py의 line 304 이후에 hotfix_session_state.py 내용을 복사하여 추가하세요.")