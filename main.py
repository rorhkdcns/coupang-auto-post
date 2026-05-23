name: Coupang Auto Blogger CI

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout repository code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'

    # 📦 필수 라이브러리들을 깃허브 서버에 먼저 설치하는 꿀단지 단계입니다!
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install requests google-auth-oauthlib google-auth-httplib2 google-api-python-client google-genai

    - name: Run Auto Post Script
      env:
        API_KEY: ${{ secrets.API_KEY }}
        TOKEN_PICKLE_BASE64: ${{ secrets.TOKEN_PICKLE_BASE64 }}
        COUPANG_ACCESS_KEY: ${{ secrets.COUPANG_ACCESS_KEY }}
        COUPANG_SECRET_KEY: ${{ secrets.COUPANG_SECRET_KEY }}
      run: python auto_post.py
