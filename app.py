from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
import requests
import json
import io
import base64
from PIL import Image
from io import BytesIO
import requests
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib import rcParams
from datetime import datetime, timezone
import pycorrector  # 拼写校正工具
import langid
from dotenv import load_dotenv
import os

# 加载 .env 文件中的环境变量
load_dotenv()

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# ===========================
# 智能问答模块
# ===========================
def get_access_token():
    """获取百度AI平台 Access Token"""
    url = os.getenv("url")
    response = requests.post(url, headers={'Content-Type': 'application/json'})
    return response.json().get("access_token")


@app.route('/ask', methods=['POST'])
def ask_question():
    """智能问答接口"""
    data = request.get_json()
    question = data.get("question")
    access_token = get_access_token()
    url_ask = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie_speed?access_token={access_token}"
    payload = json.dumps({"messages": [{"role": "user", "content": question}]})
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url_ask, headers=headers, data=payload)
    result = response.json()

    if 'result' in result:
        return jsonify({"answer": result['result']})
    else:
        return jsonify({"error": "请求失败", "details": result}), 500

@app.route('/generate_related_suggestions', methods=['POST'])
def generate_related_suggestions():
    """根据用户问题动态生成相关问题"""
    data = request.get_json()
    question = data.get("question")
    access_token = get_access_token()
    url_ask = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie_speed?access_token={access_token}"
    payload = json.dumps({
        "messages": [
            {"role": "user", "content": f"根据问题 '{question}'，请生成3个相关的问题。"}
        ]
    })
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url_ask, headers=headers, data=payload)
    result = response.json()
    print(result)
    # 直接获取 'result' 字典中的 'result' 字段
    result_content = result.get('result', '')
    lines = result_content.strip().split('\n')
    questions = [line.strip() for line in lines if line.strip()]
    # 去掉列表的第一个元素
    questions = questions[1:]
    print(questions)

    return jsonify({"suggestions": questions})


@app.route('/ask', methods=['GET'])
def ask_page():
    return render_template('ask.html')


@app.route('/get_welcome', methods=['GET'])
def get_welcome():
    return jsonify({"welcome": "你好！我是你的智能导师，随时欢迎向我提问！"})




GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = os.getenv("REPO_OWNER")
REPO_NAME = os.getenv("REPO_NAME")

# GitHub API URL for commits and issues
url_commits = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits"
url_issues = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"
url_pull_requests = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls"  # 用于获取 PR 信息

# 设置请求头
headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# 获取提交记录
def fetch_commits():
    try:
        response = requests.get(url_commits, headers=headers)
        response.raise_for_status()
        commits = response.json()
        commit_data = []
        for commit in commits:
            author = commit['commit']['author']['name']
            message = commit['commit']['message']
            timestamp = commit['commit']['author']['date']
            commit_data.append({
                "author": author,
                "message": message,
                "timestamp": timestamp
            })
        return commit_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching commits: {e}")
        return {"error": "无法获取提交信息", "details": str(e)}

# 获取 Issues 信息
def fetch_issues():
    try:
        response = requests.get(url_issues, headers=headers)
        response.raise_for_status()
        issues = response.json()
        issue_data = []
        for issue in issues:
            title = issue['title']
            state = issue['state']
            created_at = issue['created_at']
            issue_data.append({
                "title": title,
                "state": state,
                "created_at": created_at,
                "id": issue['id']  # Add the issue id for later comment fetching
            })
        return issue_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching issues: {e}")
        return {"error": "无法获取问题信息", "details": str(e)}

# 获取 PR 信息
def fetch_pull_requests():
    try:
        response = requests.get(url_pull_requests, headers=headers)
        response.raise_for_status()
        pr_data = response.json()
        pr_reviews = []
        for pr in pr_data:
            # 获取 PR 审阅信息
            if 'requested_reviewers' in pr and pr['requested_reviewers']:
                for reviewer in pr['requested_reviewers']:
                    pr_reviews.append({
                        'reviewer': reviewer['login']
                    })
        return pr_reviews
    except requests.exceptions.RequestException as e:
        print(f"Error fetching pull requests: {e}")
        return {"error": "无法获取 PR 信息", "details": str(e)}

# 获取团队成员和贡献数据
def get_team_contributions():
    commits = fetch_commits()
    pr_reviews = fetch_pull_requests()

    team_performance = {}

    # 处理提交数据
    for commit in commits:
        author = commit['author']
        if author not in team_performance:
            team_performance[author] = {
                "commits": 0,
                "last_commit": None,
                "pr_reviews": 0,  # 添加 PR 审阅次数
                "activity": 0,  # 添加提交活跃度
                "score": 0  # 最终得分
            }
        team_performance[author]["commits"] += 1
        team_performance[author]["last_commit"] = commit["timestamp"]

    # 计算每个成员的 PR 审阅次数
    for pr in pr_reviews:
        reviewer = pr['reviewer']
        if reviewer not in team_performance:
            team_performance[reviewer] = {
                "commits": 0,
                "last_commit": None,
                "pr_reviews": 0,
                "activity": 0,
                "score": 0
            }
        team_performance[reviewer]["pr_reviews"] += 1

    # 计算提交活跃度（例如：如果最新提交在过去 7 天内，活跃度 +2，否则活跃度 -2）
    for member, data in team_performance.items():
        # 提交次数评分
        score = min(data["commits"] * 2, 10)

        # 计算提交活跃度
        last_commit_time = datetime.fromisoformat(data["last_commit"].replace("Z", "+00:00"))
        last_commit_time = last_commit_time.astimezone(timezone.utc)  # 确保时间是 offset-aware
        delta_days = (datetime.now(timezone.utc) - last_commit_time).days

        # 活跃度加分
        if delta_days <= 7:
            activity_score = 2
        elif delta_days > 10:
            activity_score = -2
        else:
            activity_score = 0

        # 总分
        total_score = score + activity_score + data["pr_reviews"]
        total_score = min(total_score, 10)  # 限制最大得分为 10

        # 更新最终得分
        team_performance[member]["score"] = total_score
        team_performance[member]["activity"] = activity_score

    return team_performance

@app.route('/project_tracking_data', methods=['GET'])
def track_project_data():
    commits = fetch_commits()
    issues = fetch_issues()
    team_contributions = get_team_contributions()

    return jsonify({
        "commits": commits,
        "issues": issues,
        "team_contributions": team_contributions
    })

@app.route('/project-tracking', methods=['GET'])
def track_project():
    commits = fetch_commits()
    issues = fetch_issues()
    team_contributions = get_team_contributions()
    return render_template('project_tracking.html', commits=commits, issues=issues,
                           team_contributions=team_contributions)

# ===========================
# 团队协作模块
# ===========================
@app.route('/team-collaboration', methods=['GET'])
def quilleditor():
    return render_template('team_collaboration.html')

@app.route('/save', methods=['POST'])
def save():
    content = request.json.get('content')
    # 处理编辑器内容，可以将内容保存到数据库或文件
    print("Received content:", content)
    # 假设这里直接打印并返回成功
    return jsonify({'status': 'success', 'message': 'Content saved successfully'})

@app.route('/spellcheck', methods=['POST'])
def spellcheck():
    text = request.json.get('text')

    if not text:
        return jsonify({'status': 'error', 'message': 'No text provided'}), 400

    # 先使用 pycorrector 进行拼写校正
    corrected_text, corrections = pycorrector.correct(text)
    print(f"Corrected text: {corrected_text}")
    print(f"Corrections: {corrections}")

    # 使用 langid 库检测文本语言
    detected_lang = langid.classify(corrected_text)[0]
    print(f"Detected language: {detected_lang}")

    # 根据检测的语言设置 LanguageTool 检查语言
    if detected_lang == 'en':
        language_code = 'en-US'
    elif detected_lang.startswith('zh'):
        language_code = 'zh-CN'
    else:
        language_code = 'zh-CN'  # 默认使用中文

    # 调用 LanguageTool API 进行语法检查
    url = 'https://api.languagetool.org/v2/check'
    data = {
        'text': corrected_text,
        'language': language_code
    }

    response = requests.post(url, data=data)
    if response.status_code != 200:
        return jsonify({'status': 'error', 'message': 'Error calling LanguageTool API'}), 500

    result = response.json()

    # 返回拼写校正和语法检查结果
    return jsonify({
        'original_text': text,
        'corrected_text': corrected_text,
        'corrections': corrections,
        'grammar_check': result
    })



# ===========================
# 知识图谱模块
# ===========================
rcParams['font.sans-serif'] = ['SimHei']
rcParams['axes.unicode_minus'] = False

def get_entities(concept):
    """获取与输入概念相关的实体列表"""
    url = f"http://shuyantech.com/api/cndbpedia/ment2ent?q={concept}"
    try:
        response = requests.get(url).json()
        if response['status'] == 'ok':
            return response['ret']
    except Exception as e:
        print(f"Error fetching entities for concept '{concept}': {e}")
    return []

def get_avpairs(entity):
    """获取某实体的属性-值对列表"""
    url = f"http://shuyantech.com/api/cndbpedia/avpair?q={entity}"
    try:
        response = requests.get(url).json()
        if response['status'] == 'ok':
            return response['ret']
    except Exception as e:
        print(f"Error fetching attributes for entity '{entity}': {e}")
    return []
def build_knowledge_graph(concept, max_entities=3, max_pairs=6):
    """构建知识图谱"""
    entities = get_entities(concept)[:max_entities]
    graph = nx.DiGraph()

    for entity in entities:
        avpairs = get_avpairs(entity)[:max_pairs]
        for attribute, value in avpairs:
            graph.add_edge(entity, value, label=attribute)
    return graph
@app.route('/generate-knowledge-graph', methods=['POST'])
def generate_knowledge_graph():
    """生成知识图谱并返回图像的 Base64 编码"""
    data = request.get_json()
    concept = data.get("concept", "机器学习")
    max_entities = data.get("max_entities", 3)
    max_pairs = data.get("max_pairs", 6)

    # 构建知识图谱
    graph = build_knowledge_graph(concept, max_entities, max_pairs)

    # 绘制图并保存为内存文件
    pos = nx.spring_layout(graph, k=1.5, iterations=100)
    plt.figure(figsize=(16, 10))
    nx.draw(
        graph, pos, with_labels=True, node_size=1500, node_color='skyblue', font_size=8, font_family='SimHei'
    )
    edge_labels = nx.get_edge_attributes(graph, 'label')
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=8, font_family='SimHei')
    nx.draw_networkx_edges(graph, pos, alpha=0.5, edge_color='gray')
    plt.title("技术领域知识图谱", fontsize=14)

    # 转为 Base64 编码
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
    buffer.close()
    plt.close()

    return jsonify({"graph_image": encoded_image})


@app.route('/knowledge-graph')
def knowledge_graph():
    return render_template('knowledge_graph.html')


# ===========================
# 应用入口
# ===========================
@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
