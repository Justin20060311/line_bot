from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage, QuickReply, QuickReplyButton, MessageAction, PostbackEvent, FlexSendMessage
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi # 新增 v3 相關引入
import tempfile
import os
import logging
import google.generativeai as genai

static_tmp_path = tempfile.gettempdir()
os.makedirs(static_tmp_path, exist_ok=True)
base_url = os.getenv("SPACE_HOST")

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
app.logger.setLevel(logging.INFO)

channel_secret = os.environ.get("LINE_CHANNEL_SECRET")
channel_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

# 初始化 LineBotApi 和 WebhookHandler
configuration = Configuration(access_token=channel_access_token)
line_bot_api = LineBotApi(channel_access_token) # <-- 這裡新增了 line_bot_api 的實例化
handler = WebhookHandler(channel_secret)

# 用於儲存使用者資料的字典 (實際應用可能需要使用資料庫)
user_data = {} # {user_id: {'gender': '', 'age': '', ...}}

# 定義 BMI, BMR, TDEE 計算函式
def calculate_bmi(height, weight):
    # BMI = 體重 (kg) / (身高 (m))^2
    return round(weight / ((height / 100) ** 2), 2)

def calculate_bmr(gender, age, height, weight):
    # Mifflin-St Jeor Equation
    if gender == '男':
        return round((10 * weight) + (6.25 * height) - (5 * age) + 5, 2)
    elif gender == '女':
        return round((10 * weight) + (6.25 * height) - (5 * age) - 161, 2)
    return 0

def calculate_tdee(bmr, activity_level):
    # 運動量係數 (僅為範例，可自行調整)
    activity_factors = {
        '久坐': 1.2,
        '輕度活動': 1.375,
        '中度活動': 1.55,
        '高度活動': 1.725,
        '非常高度活動': 1.9
    }
    return round(bmr * activity_factors.get(activity_level, 1.2), 2)

# ==================== 重要：路由定義應該在頂層，不縮排 ====================
@app.route("/")
def home():
    return {"message": "Line Webhook Server"}

@app.route("/", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.warning("Invalid signature. Please check channel credentials.")
        abort(400)

    return "OK"
# =========================================================================

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text

    # 初始化使用者資料
    if user_id not in user_data:
        user_data[user_id] = {}
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='哈囉！我是你的健康顧問，讓我們開始吧！請問您的性別是？ (男/女)')
        )
        return

    # 處理使用者輸入流程
    if 'gender' not in user_data[user_id]:
        if text in ['男', '女']:
            user_data[user_id]['gender'] = text
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='好的，請問您的年齡是？')
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請輸入「男」或「女」。')
            )
    elif 'age' not in user_data[user_id]:
        try:
            age = int(text)
            if 0 < age < 120: # 簡單的驗證
                user_data[user_id]['age'] = age
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='請問您的身高是幾公分？ (例如：170)')
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='請輸入一個合理的年齡。')
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請輸入數字作為年齡。')
            )
    elif 'height' not in user_data[user_id]:
        try:
            height = float(text)
            if 50 < height < 250:
                user_data[user_id]['height'] = height
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='請問您的體重是幾公斤？ (例如：65.5)')
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='請輸入一個合理的身高 (公分)。')
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請輸入數字作為身高。')
            )
    elif 'weight' not in user_data[user_id]:
        try:
            weight = float(text)
            if 20 < weight < 300:
                user_data[user_id]['weight'] = weight
                                                
                # 提示運動量
                quick_reply_buttons = [
                    QuickReplyButton(action=MessageAction(label="久坐", text="久坐")),
                    QuickReplyButton(action=MessageAction(label="輕度活動 (1-3天/週運動)", text="輕度活動")),
                    QuickReplyButton(action=MessageAction(label="中度活動 (3-5天/週運動)", text="中度活動")),
                    QuickReplyButton(action=MessageAction(label="高度活動 (6-7天/週運動)", text="高度活動")),
                    QuickReplyButton(action=MessageAction(label="非常高度活動 (運動員/勞力工作者)", text="非常高度活動")),
                ]
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='太棒了！最後，請問您的運動量是？',
                                    quick_reply=QuickReply(items=quick_reply_buttons))
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='請輸入一個合理的體重 (公斤)。')
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請輸入數字作為體重。')
            )
    elif 'activity_level' not in user_data[user_id]:
        valid_activities = ['久坐', '輕度活動', '中度活動', '高度活動', '非常高度活動']
        if text in valid_activities:
            user_data[user_id]['activity_level'] = text

            # 計算 BMI, BMR, TDEE
            gender = user_data[user_id]['gender']
            age = user_data[user_id]['age']
            height = user_data[user_id]['height']
            weight = user_data[user_id]['weight']
            activity_level = user_data[user_id]['activity_level']

            bmi = calculate_bmi(height, weight)
            bmr = calculate_bmr(gender, age, height, weight)
            tdee = calculate_tdee(bmr, activity_level)

            user_data[user_id]['bmi'] = bmi
            user_data[user_id]['bmr'] = bmr
            user_data[user_id]['tdee'] = tdee

            # 回覆計算結果並詢問目標
            result_message = (
                f"您的基本資料已收集完畢！\n"
                f"🌟 計算結果：\n"
                f"  - BMI: {bmi}\n"
                f"  - BMR: {bmr} 大卡\n"
                f"  - TDEE: {tdee} 大卡\n\n"
                f"請問您的目標是？"
            )
            
            target_buttons = [
                QuickReplyButton(action=MessageAction(label="增肌", text="增肌")),
                QuickReplyButton(action=MessageAction(label="減脂", text="減脂")),
                QuickReplyButton(action=MessageAction(label="維持體重", text="維持體重")),
            ]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=result_message,
                                quick_reply=QuickReply(items=target_buttons))
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請從提供的選項中選擇您的運動量。')
            )
    elif 'goal' not in user_data[user_id]:
        if text in ['增肌', '減脂', '維持體重']:
            user_data[user_id]['goal'] = text
            
            # 根據目標提供建議
            advice_message = generate_advice(user_data[user_id])
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=advice_message)
            )
            # 完成後清除使用者資料，以便下次重新開始 (實際應用會更複雜)
            del user_data[user_id] 
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請選擇「增肌」、「減脂」或「維持體重」。')
            )
    else:
        # 如果已經有所有資料，但使用者又輸入了其他訊息，可以回覆一些預設訊息或重啟流程
        if text == '開始':
            if user_id in user_data: # Ensure user_id exists before deleting
                del user_data[user_id] # 重啟流程
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='哈囉！我是你的健康顧問，讓我們重新開始吧！請問您的性別是？ (男/女)')
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='您好！請問有什麼我可以協助您的嗎？如果您想重新計算，請輸入「開始」。')
            )
            

# 生成建議的函式
def generate_advice(data):
    bmi = data.get('bmi', 0)
    bmr = data.get('bmr', 0)
    tdee = data.get('tdee', 0)
    goal = data.get('goal', '')
    gender = data.get('gender', '')
    age = data.get('age', '')
    height = data.get('height', '')
    weight = data.get('weight', '')
    activity_level = data.get('activity_level', '')

    app.logger.info(f"嘗試調用 Gemini API，用戶目標: {goal}")

    # 設定 Google Gemini API 金鑰
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        app.logger.error("GOOGLE_API_KEY 環境變數未設定！")
        return "抱歉，目前無法提供建議。請稍後再試或聯繫管理員。"

    genai.configure(api_key=api_key)

    prompt = (
        f"請根據以下使用者資訊，給予個人化且具體的健康建議，內容要包含飲食、運動與注意事項，語氣親切且條列式，並用繁體中文回答：\n"
        f"性別：{gender}\n"
        f"年齡：{age}\n"
        f"身高：{height} 公分\n"
        f"體重：{weight} 公斤\n"
        f"BMI：{bmi}\n"
        f"BMR：{bmr} 大卡\n"
        f"TDEE：{tdee} 大卡\n"
        f"運動量：{activity_level}\n"
        f"目標：{goal}\n"
    )
    app.logger.info(f"發送給 Gemini 的 prompt: {prompt[:200]}...") # 記錄部分 prompt

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)

        if response and hasattr(response, 'text'):
            app.logger.info(f"從 Gemini 獲得回應: {response.text[:200]}...") # 記錄部分回應
            return response.text.strip()
        else:
            app.logger.error(f"Gemini API 回應格式異常或為空: {response}")
            return "抱歉，無法生成建議，請稍後再試。"
    except Exception as e:
        app.logger.error(f"調用 Google Gemini API 時發生錯誤: {e}")
        return "很抱歉，生成建議時發生了問題，請稍後再試。"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)