# 引入必要的函式庫
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

def generate_step_advice(user_data, step):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None
    genai.configure(api_key=api_key)

    system_instruction = (
        "你是一位親切且專業的健康顧問，請針對使用者剛輸入的資料，"
        "給予一句簡短的鼓勵、肯定或健康提醒，語氣正向且溫暖，並用繁體中文回答。"
        "請勿重複詢問問題，只需針對該步驟給予回饋。"
    )
    info = []
    if 'gender' in user_data: info.append(f"性別：{user_data['gender']}")
    if 'age' in user_data: info.append(f"年齡：{user_data['age']}")
    if 'height' in user_data: info.append(f"身高：{user_data['height']} 公分")
    if 'weight' in user_data: info.append(f"體重：{user_data['weight']} 公斤")
    if 'activity_level' in user_data: info.append(f"運動量：{user_data['activity_level']}")
    info_str = "，".join(info)
    user_query = f"使用者剛輸入了{step}，目前資料：{info_str}。請給一句鼓勵或健康提醒。"

    prompt = f"{system_instruction}\n\n{user_query}"

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        if response and hasattr(response, 'text'):
            return response.text.strip()
    except Exception:
        return None
    return None

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
            ai_msg = generate_step_advice(user_data[user_id], '性別')
            msgs = []
            if ai_msg:
                msgs.append(TextSendMessage(text=ai_msg))
            msgs.append(TextSendMessage(text='好的，請問您的年齡是？'))
            line_bot_api.reply_message(event.reply_token, msgs)
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請輸入「男」或「女」。')
            )
    elif 'age' not in user_data[user_id]:
        try:
            age = int(text)
            if 0 < age < 120:
                user_data[user_id]['age'] = age
                ai_msg = generate_step_advice(user_data[user_id], '年齡')
                msgs = []
                if ai_msg:
                    msgs.append(TextSendMessage(text=ai_msg))
                msgs.append(TextSendMessage(text='請問您的身高是幾公分？ (例如：170)'))
                line_bot_api.reply_message(event.reply_token, msgs)
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
                ai_msg = generate_step_advice(user_data[user_id], '身高')
                msgs = []
                if ai_msg:
                    msgs.append(TextSendMessage(text=ai_msg))
                msgs.append(TextSendMessage(text='請問您的體重是幾公斤？ (例如：65.5)'))
                line_bot_api.reply_message(event.reply_token, msgs)
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
                ai_msg = generate_step_advice(user_data[user_id], '體重')
                msgs = []
                if ai_msg:
                    msgs.append(TextSendMessage(text=ai_msg))
                # 提示運動量
                quick_reply_buttons = [
                    QuickReplyButton(action=MessageAction(label="久坐", text="久坐")),
                    QuickReplyButton(action=MessageAction(label="輕度活動 (1-3天/週運動)", text="輕度活動")),
                    QuickReplyButton(action=MessageAction(label="中度活動 (3-5天/週運動)", text="中度活動")),
                    QuickReplyButton(action=MessageAction(label="高度活動 (6-7天/週運動)", text="高度活動")),
                    QuickReplyButton(action=MessageAction(label="非常高度活動 (運動員/勞力工作者)", text="非常高度活動")),
                ]
                msgs.append(TextSendMessage(
                    text='太棒了！最後，請問您的運動量是？',
                    quick_reply=QuickReply(items=quick_reply_buttons)
                ))
                line_bot_api.reply_message(event.reply_token, msgs)
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
            ai_msg = generate_step_advice(user_data[user_id], '運動量')
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
            msgs = []
            if ai_msg:
                msgs.append(TextSendMessage(text=ai_msg))
            msgs.append(TextSendMessage(
                text=result_message,
                quick_reply=QuickReply(items=target_buttons)
            ))
            line_bot_api.reply_message(event.reply_token, msgs)
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

    system_instruction = (
        "你現在是一名專業的健康顧問，你的任務是根據使用者提供的個人健康數據和目標，"
        "提供個人化、具體且實用的飲食、運動和注意事項建議。請保持語氣親切、專業且條列式呈現，所有回覆都需使用繁體中文。"
        "確保建議是基於科學原理，但以易於理解的方式呈現。"
        "目標為增肌時，請強調足夠蛋白質攝取和力量訓練的重要性，並提供相關建議。目標為減脂時，請強調熱量赤字和有氧運動的策略。目標為維持體重時，請強調均衡飲食和規律運動的必要性。"
        "**請在飲食建議中，為使用者生成一個根據TDEE計算的每日熱量與三大營養素（碳水化合物、蛋白質、脂肪）的建議攝取量表格，表格請使用markdown格式，包含「營養素」、「攝取量（大卡）」和「攝取量（公克）」三列。**"
        "請避免提供醫療診斷或處方，並在建議中明確指出：『這些建議僅供參考，如有特殊健康狀況或疑慮，請務必諮詢專業醫師或營養師。』"
    )

    user_query = (
        f"請根據以下資訊，為我生成健康建議：\n"
        f"性別：{gender}\n"
        f"年齡：{age}\n"
        f"身高：{height} 公分\n"
        f"體重：{weight} 公斤\n"
        f"BMI：{bmi}\n"
        f"BMR：{bmr} 大卡\n"
        f"TDEE：{tdee} 大卡\n"
        f"運動量：{activity_level}\n"
        f"我的目標是：{goal}\n"
        f"請根據我的TDEE {tdee} 大卡，以及目標 {goal}，建議我每日的碳水化合物、蛋白質和脂肪攝取量（大卡與公克）。"
    )

    # 將 system_instruction 和 user_query 組合成最終 prompt
    prompt = f"{system_instruction}\n\n{user_query}"
    
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