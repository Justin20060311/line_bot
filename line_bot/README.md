---
title: 健康顧問 Line Bot (Docker)
emoji: 🤖
color_map: blue
models: []
sdk: docker # 這裡指定為 docker
---

# 健康顧問 Line Bot (Docker)

這是一個基於 Flask 開發的健康顧問 Line Bot，使用 Docker 部署在 Hugging Face Spaces 上。

**功能：**
- 收集用戶的性別、年齡、身高、體重和運動量
- 計算 BMI、BMR 和 TDEE
- 根據用戶的增肌/減脂/維持體重目標提供個性化飲食和運動建議

**如何使用：**
1. 在 Line Developers Console 中獲取您的 Channel Access Token 和 Channel Secret。
2. 在 Hugging Face Spaces 中，進入您的專案設定，配置環境變數 `LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_CHANNEL_SECRET`。
3. 將 Hugging Face Spaces 提供的公開 URL 設定為您的 Line Bot Webhook URL。
4. 開始與 Line Bot 互動！

**注意：**
為了讓 Line Bot 正常運作，您必須在 Line Developers Console 中啟用 Webhook，並將此 Spaces 的公開 URL 配置為 Webhook URL。