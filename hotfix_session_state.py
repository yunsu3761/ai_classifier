"""
Web Interface 핫픽스 - session_state 보존 로직 추가
이 파일의 내용을 web_interface.py의 line 304 이후에 추가하세요.
"""

# 중요: 이미 dimensions가 로드되어 있으면 config_loaded도 True로 설정 (rerun 시 보존)
if st.session_state.dimensions and not st.session_state.config_loaded:
    print(f"[DEBUG] Preserving existing dimensions after rerun: {list(st.session_state.dimensions.keys())}")
    st.session_state.config_loaded = True
    # Config 객체도 복구
    if not st.session_state.config:
        st.session_state.config = DimensionConfig(config_path=None)
        st.session_state.config.dimensions = st.session_state.dimensions.copy()
    st.info(f"🔄 차원 정보 복구됨: {len(st.session_state.dimensions)}개 차원")