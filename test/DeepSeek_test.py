import requests
import json

# self.headers {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-7fbfac05d6314d779d70da5702583576'}
# 生成的header: {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-7fbfac05d6314d779d70da5702583576'}
class DeepSeekClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        print("api_key",api_key)
        print("self.headers",self.headers)
    def chat_completion(self, messages, model="deepseek-chat", **kwargs):
        """
        调用 DeepSeek Chat Completion API

        Args:
            messages (list): 消息列表，格式如 [{"role": "user", "content": "Hello"}]
            model (str): 模型名称，默认为 "deepseek-chat"
            **kwargs: 其他可选参数，如 temperature, max_tokens 等

        Returns:
            dict: API 响应结果
        """
        url = f"{self.base_url}/chat/completions"
        print("url",url)
        # 构建请求数据
        data = {
            "model": model,
            "messages": messages,
            "stream": False
        }

        # 添加其他可选参数
        data.update(kwargs)

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"API 调用错误: {e}")
            if hasattr(e.response, 'text'):
                print(f"错误详情: {e.response.text}")
            raise
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            raise

    def simple_chat(self, user_message, system_message="You are a helpful assistant."):
        """
        简单的聊天接口

        Args:
            user_message (str): 用户消息
            system_message (str): 系统消息

        Returns:
            str: AI 回复内容
        """
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]

        response = self.chat_completion(messages)
        return response['choices'][0]['message']['content']


# 使用示例
if __name__ == "__main__":
    # 初始化客户端
    api_key = "sk-7fbfac05d6314d779d70da5702583576"
    client = DeepSeekClient(api_key)

    # 方法1: 使用完整接口
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]

    try:
        response = client.chat_completion(messages)
        print("完整响应:")
        print(json.dumps(response, indent=2, ensure_ascii=False))

        # 提取回复内容
        reply = response['choices'][0]['message']['content']
        print(f"\nAI 回复: {reply}")

    except Exception as e:
        print(f"调用失败: {e}")

    print("\n" + "=" * 50 + "\n")

    # 方法2: 使用简单接口
    try:
        reply = client.simple_chat("你好，介绍一下你自己")
        print(f"简单聊天回复: {reply}")
    except Exception as e:
        print(f"调用失败: {e}")
